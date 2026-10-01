"""Turning a question and some retrieved passages into a cited answer.

The contract with the model is the whole design here: the model is given
numbered passages and asked to cite them by number, and the citation list on the
answer is built from the numbers it actually used. Nothing is inferred from
prose afterwards, and a citation is never produced for a passage that was not
provided.

Three things that are easy to get wrong and are handled explicitly.

**The model may cite a number that was never offered.** A model asked to cite
will occasionally produce `[7]` when five passages were given. That citation is
dropped rather than shown, because a citation pointing at nothing is worse than
one fewer citation: it makes the whole list untrustworthy.

**A model may cite nothing at all.** That is allowed, and is the correct output
when it declines to answer. The answer is kept, un-cited, rather than discarded.

**The transcript is bounded.** Replaying a whole conversation eventually exceeds
the context window, and a request that does is a 400 from the provider. Turns are
taken from the most recent end backwards until the token budget is spent, which
keeps a long chat cheap and predictable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache

import httpx
from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from api import access
from api.models import (
    ChatMessage,
    ChatSession,
    Library,
    MessageRole,
)
from api.retrieval import RetrievalError, RetrievalResult, retrieve

logger = logging.getLogger(__name__)

#: Attempts for a rate-limited or failing generation, including the first.
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 0.5
RETRY_MAX_SECONDS = 8.0

#: A citation marker in the model's output. Tolerates `][2]` and `[2, 3]`,
#: because models are not consistent about the exact form and rejecting a
#: well-formed answer over punctuation is not a trade worth making.
CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

#: What the model is told, once, every time.
SYSTEM_PROMPT = """\
You answer questions using only the source passages you are given.

Rules:
- Cite every claim with the bracketed number of the passage it came from, like \
[2] or [1][3]. Put the citation at the end of the sentence it supports.
- If the passages do not contain the answer, say so plainly. Do not use \
background knowledge, and do not guess.
- If the passages only partly answer the question, answer the part they cover \
and say what is missing.
- Be concise. No preamble, no restating the question, no summary of the \
passages.
- Never invent a passage number. Only numbers given to you exist.
"""

#: Used when a library has nothing to search, so retrieval returns no passages.
#: Still asked to be honest, because the model has to produce something.
NO_CONTEXT_SYSTEM_PROMPT = """\
You are answering a question from a library that contains no documents yet, or \
none that could be read.

Say, in one or two sentences, that there is nothing in the library to answer \
from, and suggest uploading a document. Do not answer from your own knowledge.
"""


class AnswerError(Exception):
    """An answer could not be produced, with a reason meant for the user."""

    def __init__(self, reason: str, *, code: str = "answer_failed", retryable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.retryable = retryable


@dataclass
class Answer:
    """A generated answer, with the citations that back it."""

    text: str
    citations: list[dict] = field(default_factory=list)
    #: The passages the search considered, whether or not they were cited. Kept
    #: for the response so the UI can show "searched 6 passages".
    retrieved: list[dict] = field(default_factory=list)

    @property
    def used_context(self) -> bool:
        return bool(self.citations)


def answer_question(
    principal,
    *,
    session: ChatSession,
    question: str,
) -> tuple[Answer, RetrievalResult]:
    """Answer one question in one session, and persist the exchange.

    Returns the answer alongside the retrieval result, because the caller
    reports both and a caller that has to retrieve twice would embed the
    question twice.
    """
    question = _clean_question(question)

    library = session.library
    try:
        result = retrieve(principal, library=library, question=question)
    except RetrievalError as exc:
        raise AnswerError(exc.reason, code=exc.code) from exc

    answer = _generate(session, question, result)

    _persist(session, question, answer)
    return answer, result


def _clean_question(question: str) -> str:
    question = (question or "").strip()
    if not question:
        raise AnswerError("Ask a question first.", code="empty_question")
    if len(question) > settings.MAX_QUESTION_CHARS:
        raise AnswerError(
            f"That question is too long; keep it under "
            f"{settings.MAX_QUESTION_CHARS} characters.",
            code="question_too_long",
        )
    return question


def _generate(
    session: ChatSession, question: str, result: RetrievalResult
) -> Answer:
    system = SYSTEM_PROMPT if result.has_context else NO_CONTEXT_SYSTEM_PROMPT
    messages = [{"role": "system", "content": system}]

    history = _history_for(session)
    if history:
        messages.extend(history)

    # The question is added after the transcript rather than inside it, so the
    # model always sees the current question last, immediately before it has to
    # answer. Prepending it is the kind of thing that works until the chat grows
    # past the history window.
    user_turn = result.as_prompt_block()
    messages.append(
        {
            "role": "user",
            "content": f"{user_turn}\n\nQuestion: {question}" if user_turn else question,
        }
    )

    text = _complete(messages)
    return Answer(
        text=text,
        citations=_citations_for(text, result),
        retrieved=[passage.citation() for passage in result.passages],
    )


def _history_for(session: ChatSession) -> list[dict]:
    """Recent turns, newest-first truncated to fit the history budget.

    Fetched newest-first because the limit is on the most recent turns, then
    reversed back into order for the prompt. Only assistant messages that carry
    citations repeat their sources, so a transcript of a chat where most answers
    declined does not fill the window with empty citation lists.
    """
    messages = list(
        ChatMessage.objects.filter(session=session)
        .order_by("-created_at", "-id")
        .values("role", "content")[: settings.CHAT_HISTORY_TURNS * 2]
    )

    kept: list[dict] = []
    spent = 0
    budget = settings.CHAT_HISTORY_MAX_TOKENS

    for message in messages:
        estimate = len(message["content"]) // 4
        if spent + estimate > budget:
            break
        spent += estimate
        kept.append(
            {
                "role": MessageRole(message["role"]).value,
                "content": message["content"],
            }
        )

    kept.reverse()
    return kept


def _citations_for(text: str, result: RetrievalResult) -> list[dict]:
    """The citations the answer actually used, in order of first appearance.

    Built from the numbers the model wrote, looked up against the passages that
    were offered. A number with no matching passage is discarded, and so is a
    repeated one, so the list is a set of distinct sources rather than a
    transcript of the model's punctuation.
    """
    by_reference = {passage.reference: passage for passage in result.passages}

    seen: set[int] = set()
    citations: list[dict] = []

    for match in CITATION.finditer(text):
        for number in match.group(1).split(","):
            try:
                reference = int(number.strip())
            except ValueError:
                continue
            if reference in seen:
                continue
            passage = by_reference.get(reference)
            if passage is None:
                # Invented marker. Logged, because a model citing [7] out of five
                # passages is a signal the prompt needs work.
                logger.info("Model cited passage [%s], which was not offered", reference)
                continue
            seen.add(reference)
            citations.append(passage.citation())

    return citations


def open_session(
    principal,
    *,
    library: Library,
    session_id=None,
    force_new: bool = False,
) -> ChatSession:
    """The session to add a turn to, creating one if this is the first.

    Passing a `session_id` continues that conversation, and only if it belongs to
    the caller — a session belonging to someone else is reported as not found
    rather than forbidden, because whether a given id exists is itself
    information a stranger should not get.

    With no id, a session is created against `library`. Creating one per question
    would fragment the history, so the view passes the latest session in the
    library when the client did not name one.

    `force_new` overrides that fallback for an explicit "start a new
    conversation" action. Without it the button would be a lie: asking a
    question from a fresh screen would silently append to the previous
    conversation, which is the opposite of what starting a new one means.
    """
    if session_id is not None:
        session = access.chat_sessions_for(principal).filter(pk=session_id).first()
        if session is None:
            raise AnswerError("That conversation does not exist.", code="no_session")
        return session

    if not force_new:
        existing = access.chat_sessions_for(principal, library=library).first()
        if existing is not None:
            return existing

    return ChatSession.objects.create(owner_id=access.owner_id(principal), library=library)


def list_sessions(principal, *, library: Library | None = None) -> list[ChatSession]:
    """The caller's conversations, newest first, with their message counts.

    The count is annotated rather than computed per row: a sidebar showing twenty
    conversations otherwise runs twenty counts.
    """
    return list(
        access.chat_sessions_for(principal, library=library)
        .annotate(message_count=Count("messages"))
        .select_related("library")
    )


def messages_for(principal, session: ChatSession) -> list[ChatMessage]:
    """One conversation's turns, in order.

    Takes the session rather than an id, so the caller has already established
    that it belongs to the caller. Re-checking here is belt and braces against a
    view that forgets.

    Both sides are compared as strings: `owner_id` is a `UUIDField`, so the row
    carries a `uuid.UUID` while the principal carries the string from the token.
    """
    if str(session.owner_id) != access.owner_id(principal):
        raise AnswerError("That conversation does not exist.", code="no_session")
    return list(session.messages.order_by("created_at", "id"))


def _persist(session: ChatSession, question: str, answer: Answer) -> None:
    ChatMessage.objects.create(session=session, role=MessageRole.USER, content=question)
    ChatMessage.objects.create(
        session=session,
        role=MessageRole.ASSISTANT,
        content=answer.text,
        citations=answer.citations,
    )

    if session.title == "New chat":
        session.title = _title_for(question)
        session.save(update_fields=["title", "updated_at"])
    else:
        # Touching the row is what moves the session to the top of the sidebar.
        # `auto_now` does not fire on a partial save that omits the field.
        session.updated_at = timezone.now()
        session.save(update_fields=["updated_at"])


def _title_for(question: str) -> str:
    """A chat title from the first question, trimmed to something readable."""
    collapsed = " ".join(question.split())
    if len(collapsed) <= 60:
        return collapsed or "New chat"
    # Cut at a word boundary, so a title does not end mid-word.
    return collapsed[:60].rsplit(" ", 1)[0] + "..."


@lru_cache(maxsize=1)
def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))


def reset_client_cache() -> None:
    """Drop the cached client. Intended for tests and key changes."""
    _client.cache_clear()


def _complete(messages: list[dict]) -> str:
    if not settings.GROQ_API_KEY:
        raise AnswerError(
            "No language model key is configured (set GROQ_API_KEY).",
            code="not_configured",
        )

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": messages,
        "max_tokens": settings.ANSWER_MAX_TOKENS,
        "temperature": settings.ANSWER_TEMPERATURE,
    }

    last_error: str | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            import time

            time.sleep(min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_SECONDS))

        try:
            response = _client().post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            last_error = str(exc)
            logger.warning("Generation request failed to send (attempt %d): %s", attempt + 1, exc)
            continue

        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"the model returned {response.status_code}"
            logger.warning("Generation returned %d (attempt %d)", response.status_code, attempt + 1)
            continue

        if response.status_code != 200:
            raise AnswerError(
                f"the model rejected the request ({response.status_code})", code="model_error"
            )

        return _extract_text(response)

    raise AnswerError(
        f"the model could not be reached after {MAX_ATTEMPTS} attempts"
        + (f": {last_error}" if last_error else ""),
        code="model_unavailable",
        retryable=True,
    )


def _extract_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        text = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AnswerError("the model returned an unusable response", code="model_error") from exc

    if not isinstance(text, str) or not text.strip():
        # An empty completion is a provider-side stop, not a reason to store a
        # blank turn in the user's history.
        raise AnswerError("the model returned an empty answer", code="model_error")

    return text.strip()
