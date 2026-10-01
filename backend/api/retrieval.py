"""Finding the passages an answer should be based on.

The job is not "return the most similar chunks". It is "return enough relevant
context to answer, without so much that the model gets distracted, and with each
passage attributable to a page a user can check".

Four decisions follow from that.

**A floor, not just a top-k.** Returning the five nearest chunks unconditionally
means a question nothing in the library answers still produces five confident
passages, and the model writes something plausible on top of them. Below the
floor, the honest answer is that the documents do not say.

**MMR, not plain similarity.** The five nearest neighbours to a query about one
topic are often five restatements of the same paragraph. Maximal marginal
relevance trades a little raw similarity for passages that cover different ground.

**One passage per document first.** A single long document would otherwise fill
the whole budget with its own text and crowd out every other library.

**Grouping for the prompt.** The retrieved chunks are numbered and returned as a
list, because the answer has to reference them by number to cite them, and a
model asked to cite "the source" without identifiers invents them.
"""

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

#: Candidates pulled from Postgres before reranking. Reranking is a pure-Python
#: pass, so this is cheap; the HNSW index does the expensive part.
CANDIDATE_MULTIPLIER = 4

#: Passages finally returned.
TOP_K = 6

#: Candidates pulled per document, before MMR. One paragraph should not fill the
#: whole context, but the right two or three from one document often should.
PER_DOCUMENT_LIMIT = 3

#: How far a passage may be from the question, as a cosine distance, and still
#: be considered on topic. 0 is identical, 1 is orthogonal.
#:
#: Measured with the default local model, which is why it is a number rather than
#: a guess. Embedding four unrelated passages and asking about three topics
#: produced: a good match at 0.18 to 0.34, the nearest miss at 0.48, and
#: everything genuinely unrelated at 0.52 and above. 0.45 sits in the gap with
#: room on both sides — loose enough to keep a partial match that a person would
#: call relevant, tight enough that a question nothing answers returns no
#: passages at all.
#:
#: Configurable because the number is a property of the model, and a different
#: model has a different scale.
MAX_COSINE_DISTANCE = float(settings.RETRIEVAL_MAX_DISTANCE)

#: Trade-off between matching the query and covering new ground. 0 is pure
#: relevance, 1 is pure diversity. Retrieval on a personal document library
#: rewards diversity more than it rewards the single best passage, because the
#: failure mode is quoting one paragraph five times.
MMR_LAMBDA = 0.7


class RetrievalError(Exception):
    """Chunks could not be searched for."""

    def __init__(self, reason: str, *, code: str = "retrieval_failed"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class RetrievedPassage:
    """One passage, with the provenance needed to cite it."""

    #: 1-based, matching the `[n]` markers used in the prompt.
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

    def citation(self) -> dict:
        """The citation as stored on the message and shown in the UI.

        `chunk_id` is included so the UI can offer "open this passage", and
        `snippet` so the citation list can show what was quoted without a second
        request. Both are snapshots, not joins, so later re-ingestion cannot
        change what an old answer claims it cited.
        """
        return {
            "reference": self.reference,
            "chunk_id": self.chunk.pk,
            "document_id": self.document_id,
            "filename": self.filename,
            "page_number": self.page_number,
            "ordinal": self.chunk.ordinal,
            "snippet": self.chunk.content[:400],
        }


@dataclass(frozen=True)
class RetrievalResult:
    """What a search found, and why it might have found nothing."""

    passages: list[RetrievedPassage]
    query_vector: list[float]

    @property
    def has_context(self) -> bool:
        return bool(self.passages)

    def as_prompt_block(self) -> str:
        """The passages, formatted for the model.

        Every passage carries its document, page and ordinal because an answer
        that cites "[3]" is only useful if the reader can find [3]. The
        instruction to cite or say so is part of this block rather than the
        system prompt, so the two cannot be reordered into a state where the
        passages are present but the instruction is not.
        """
        if not self.passages:
            return ""

        blocks = []
        for passage in self.passages:
            location = passage.filename
            if passage.page_number is not None:
                location += f", page {passage.page_number}"
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
    """Search a library for the passages that bear on a question."""
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
    """The nearest chunks, capped per document.

    Ordered by cosine distance, so `distance` is populated on each row; the
    rerank step reads it. The HNSW index is used by the database when the filter
    is selective enough, and falls back to a scan when it is not, which is the
    behaviour pgvector documents.
    """
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
    """Confirm the stored vectors match the configured width.

    Cheaper to check here than to let Postgres raise on a cosine distance
    between a 384- and a 768-element vector, which arrives as a generic database
    error with no indication of what is actually wrong.
    """
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
    """Take at most `PER_DOCUMENT_LIMIT` chunks from each document.

    Done in Python rather than SQL because the cap is per distinct document and
    the number of distinct documents is not known until the rows arrive. The
    candidate set is bounded, so this is a small pass.

    Ordering by distance first means the passages kept from a document are its
    best ones, not whichever ones happened to come back first.
    """
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
    """Greedy MMR: pick the passage that is relevant but least like those picked.

    A candidate's score is its similarity to the query, minus a penalty for
    being similar to what has already been selected. The first pick is the plain
    nearest neighbour, since there is nothing to be redundant with yet.

    Candidates beyond `MAX_COSINE_DISTANCE` are discarded before reranking, so
    the context window is not spent on text that only looked similar.
    """
    on_topic = [c for c in candidates if c.distance <= MAX_COSINE_DISTANCE]
    if not on_topic:
        # Everything is off topic. Returning the nearest anyway would hand the
        # model something to quote that has nothing to do with the question, and
        # an answer built on it would be confidently wrong.
        logger.info("No candidate was within the relevance threshold")
        return []

    if len(on_topic) == 1:
        return on_topic[:top_k]

    # Cosine distance runs 0 (identical) to 2 (opposite), so this is a true
    # similarity in 0..1 for anything on topic. Clamped because a distance
    # slightly below 0 — possible with float error on a self-match — would
    # otherwise exceed 1.
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
    """How much this chunk overlaps something already selected.

    The dot product of two unit vectors is their cosine similarity. Vectors here
    come out of the same model and are L2-normalised, so no normalisation is
    needed at this point — and doing it again would cost a pass over every
    candidate for no change in the result.

    `strict=True` is the point at which a stale index is caught. If the library
    contains vectors written by a different model, the lengths differ, and a
    non-strict zip would silently compare the overlapping prefix and return a
    plausible-looking number for two unrelated vectors.
    """
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
    """How many tokens of retrieved text fit in the prompt.

    Derived from the model's context window minus room for the question, the
    transcript and the answer. A quarter is spent on retrieved passages: enough
    for six or seven of them, not so much that the answer has nowhere to go.
    """
    reserve = settings.ANSWER_MAX_TOKENS
    available = settings.CHAT_CONTEXT_WINDOW - reserve
    return max(1000, int(available * 0.25))


def _fits_budget(chunks: list[Chunk]) -> list[Chunk]:
    """Drop the lowest-ranked passages that do not fit the context budget.

    MMR already caps the count, but the count is not the constraint — the size is.
    A document with unusually long paragraphs, or a top_k raised by a caller,
    can produce passages that fill the window and leave no room for the answer.
    The best passage is always kept even if it alone exceeds the budget: it is
    the one most worth answering from, and truncating it here would be worse than
    an over-long prompt.
    """
    budget = context_token_budget()
    kept: list[Chunk] = []
    spent = 0

    for chunk in chunks:
        # Four characters per token, the same estimate `chunking` stores, so the
        # budget and the stored counts agree.
        estimate = (len(chunk.content) // 4) + 20  # plus the location header
        if kept and spent + estimate > budget:
            logger.info(
                "Dropped %d passage(s) that would not fit the context budget",
                len(chunks) - len(kept),
            )
            break
        spent += estimate
        kept.append(chunk)

    return kept
