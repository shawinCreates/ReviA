from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db.models import QuerySet
from pgvector.django import CosineDistance

from api import access
from api.auth import SupabasePrincipal
from api.embedding_client import EmbeddingError, embed_query
from api.models import Chunk, Library

logger = logging.getLogger(__name__)

CANDIDATE_MULTIPLIER = 4

TOP_K = 6

PER_DOCUMENT_LIMIT = 3

MAX_COSINE_DISTANCE = float(settings.RETRIEVAL_MAX_DISTANCE)

MMR_LAMBDA = 0.7


class RetrievalError(Exception):
    def __init__(self, reason: str, *, code: str = "retrieval_failed"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class RetrievedPassage:
    reference: int
    chunk: Chunk

    @property
    def score(self) -> float:
        return float(self.chunk.distance)

    @property
    def document_id(self) -> str:
        return str(self.chunk.document_id)

    @property
    def filename(self) -> str:
        return self.chunk.document.filename

    @property
    def page_number(self) -> int | None:
        return self.chunk.page_number

    @property
    def heading(self) -> str:
        return self.chunk.heading_path

    def citation(self) -> dict:
        return {
            "reference": self.reference,
            "chunk_id": self.chunk.pk,
            "document_id": self.document_id,
            "filename": self.filename,
            "page_number": self.page_number,
            "heading": self.heading,
            "ordinal": self.chunk.ordinal,
            "snippet": self.chunk.content[:400],
        }


@dataclass(frozen=True)
class RetrievalResult:
    passages: list[RetrievedPassage]
    query_vector: list[float]

    @property
    def has_context(self) -> bool:
        return bool(self.passages)

    def as_prompt_block(self) -> str:
        if not self.passages:
            return ""

        blocks = []
        for passage in self.passages:
            location = passage.filename
            if passage.page_number is not None:
                location += f", page {passage.page_number}"
            if passage.heading:
                location += f', "{passage.heading}"'
            blocks.append(
                f"[{passage.reference}] {location}\n{passage.chunk.content.strip()}"
            )

        joined = "\n\n".join(blocks)
        return (
            "Source passages:\n\n"
            f"{joined}\n\n"
            "Cite the passages you use as [n]. If the passages do not answer "
            "the question, say so plainly instead of guessing."
        )


def retrieve(
    principal: SupabasePrincipal,
    *,
    library: Library,
    question: str,
    top_k: int = TOP_K,
) -> RetrievalResult:
    question = question.strip()
    if not question:
        raise RetrievalError("Ask a question first.", code="empty_query")

    try:
        vector = embed_query(question)
    except EmbeddingError as exc:
        raise RetrievalError(exc.reason, code="embedding_failed") from exc

    candidates = _candidates(principal, library, vector, top_k)
    if not candidates:
        return RetrievalResult(passages=[], query_vector=vector)

    selected = _fits_budget(_rerank(candidates, top_k))
    passages = [
        RetrievedPassage(reference=index, chunk=chunk)
        for index, chunk in enumerate(selected, start=1)
    ]

    logger.info(
        "Retrieved %d of %d candidates for a question about %r",
        len(passages),
        len(candidates),
        question[:60],
    )
    return RetrievalResult(passages=passages, query_vector=vector)


def _candidates(
    principal: SupabasePrincipal,
    library: Library,
    vector: list[float],
    top_k: int,
) -> list[Chunk]:
    queryset: QuerySet[Chunk] = (
        access.searchable_chunks(principal, library=library)
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance")
    )

    limit = max(top_k * CANDIDATE_MULTIPLIER, top_k)
    found = _per_document(queryset, limit)
    _check_dimension(found)
    return found


def _check_dimension(candidates: list[Chunk]) -> None:
    if not candidates:
        return

    stored = len(candidates[0].embedding or ())
    if stored != settings.EMBEDDING_DIM:
        raise RetrievalError(
            f"the library stores {stored}-dimension vectors but this project "
            f"expects {settings.EMBEDDING_DIM}; its documents were indexed with "
            f"a different embedding model and need to be uploaded again",
            code="incompatible_index",
        )


def _per_document(queryset: QuerySet[Chunk], limit: int) -> list[Chunk]:
    seen: dict[str, int] = {}
    kept: list[Chunk] = []

    for chunk in queryset[: limit * 4]:
        document_id = str(chunk.document_id)
        if seen.get(document_id, 0) >= PER_DOCUMENT_LIMIT:
            continue
        seen[document_id] = seen.get(document_id, 0) + 1
        kept.append(chunk)
        if len(kept) >= limit:
            break

    return kept


def _rerank(candidates: list[Chunk], top_k: int) -> list[Chunk]:
    on_topic = [c for c in candidates if c.distance <= MAX_COSINE_DISTANCE]
    if not on_topic:
        logger.info("No candidate was within the relevance threshold")
        return []

    if len(on_topic) == 1:
        return on_topic[:top_k]

    scores = [max(0.0, 1.0 - chunk.distance) for chunk in on_topic]

    selected: list[int] = [0]
    selected_vectors = [on_topic[0].embedding]

    while len(selected) < min(top_k, len(on_topic)):
        best_index = None
        best_score = None

        for index, score in enumerate(scores):
            if index in selected:
                continue

            redundancy = _max_similarity(on_topic[index], selected_vectors)
            adjusted = MMR_LAMBDA * score - (1 - MMR_LAMBDA) * max(0.0, redundancy)

            if best_score is None or adjusted > best_score:
                best_score = adjusted
                best_index = index

        if best_index is None:
            break

        selected.append(best_index)
        selected_vectors.append(on_topic[best_index].embedding)

    return [on_topic[index] for index in selected]


def _max_similarity(chunk: Chunk, selected: list) -> float:
    if not selected or chunk.embedding is None:
        return 0.0

    vector = chunk.embedding
    try:
        return max(
            sum(a * b for a, b in zip(vector, other, strict=True))
            for other in selected
            if other is not None
        )
    except ValueError as exc:
        raise RetrievalError(
            "the library contains vectors from more than one embedding model; "
            "documents need to be re-uploaded before they can be searched",
            code="incompatible_index",
        ) from exc


def context_token_budget() -> int:
    reserve = settings.ANSWER_MAX_TOKENS
    available = settings.CHAT_CONTEXT_WINDOW - reserve
    return max(1000, int(available * 0.25))


def _fits_budget(chunks: list[Chunk]) -> list[Chunk]:
    budget = context_token_budget()
    kept: list[Chunk] = []
    spent = 0

    for chunk in chunks:
        estimate = (len(chunk.content) // 4) + 20
        if kept and spent + estimate > budget:
            logger.info(
                "Dropped %d passage(s) that would not fit the context budget",
                len(chunks) - len(kept),
            )
            break
        spent += estimate
        kept.append(chunk)

    return kept
