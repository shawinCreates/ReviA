"""Scoping queries to the authenticated user.

RLS is enabled on these tables, but it does not apply to this service: it
connects as the database owner, and the owner bypasses RLS by design. Supabase
policies here would look like protection in the dashboard while every query ran
straight past them. So ownership is enforced in this module instead, in one
place, and the rest of the code is expected to go through these helpers rather
than reaching for a model manager directly.

`test_access.py` asserts that the scoping actually holds, because a helper that
looks right and filters on the wrong column is the exact failure this design
risks.
"""

from __future__ import annotations

from django.db.models import QuerySet

from api.auth import SupabasePrincipal
from api.models import (
    ChatSession,
    Chunk,
    Document,
    DocumentStage,
    Library,
    Profile,
)


def owner_id(principal: SupabasePrincipal) -> str:
    """The caller's id as the string every owner filter is written against.

    `Profile.id` and `Document.owner_id` are `UUIDField`s, so Django hands back
    `uuid.UUID` objects. A principal carries a string. Comparing one to the other
    directly is always unequal and always wrong, so every owner comparison goes
    through `str()` on both sides — which is what the query filters here do
    implicitly, and what a `WHERE owner_id = ?` check has to do explicitly.
    """
    return str(principal.id)


def libraries_for(principal: SupabasePrincipal) -> QuerySet[Library]:
    return Library.objects.filter(owner_id=owner_id(principal))


def documents_for(
    principal: SupabasePrincipal, *, library: Library | None = None
) -> QuerySet[Document]:
    """Documents belonging to the caller, optionally narrowed to one library.

    Filtering on `owner` and not on `library__owner` is deliberate: it is the
    column the database can index directly, and the two are kept consistent by
    the service layer that creates documents.
    """
    queryset = Document.objects.filter(owner_id=owner_id(principal))
    if library is not None:
        queryset = queryset.filter(library=library)
    return queryset


def chunks_for(
    principal: SupabasePrincipal, *, document: Document | None = None
) -> QuerySet[Chunk]:
    queryset = Chunk.objects.filter(owner_id=owner_id(principal))
    if document is not None:
        queryset = queryset.filter(document=document)
    return queryset


def searchable_chunks(
    principal: SupabasePrincipal, *, library: Library
) -> QuerySet[Chunk]:
    """The chunks retrieval is allowed to search.

    Three filters, each for a reason that is not obvious from the column name.

    Scoped to the owner, like every other query here.
    Restricted to the session's library, because an answer that cites a document
    from a library the user is not currently reading is an answer they cannot
    follow up on.
    Restricted to ready documents, because a chunk whose document is still being
    embedded has a null or stale vector. A null vector sorts unpredictably
    rather than sorting last, so a document being ingested mid-query could supply
    the nearest neighbour to any question.

    The final `exclude(embedding=None)` is a belt to that braces: `pgvector`'s
    distance operators are undefined for null, and rather than rely on every
    caller remembering the stage filter, the rows that cannot be compared are
    excluded at the query.
    """
    return (
        Chunk.objects.filter(
            owner_id=owner_id(principal),
            document__library_id=library.id,
        )
        .filter(document__stage=DocumentStage.READY)
        .exclude(embedding=None)
        .select_related("document")
    )


def chat_sessions_for(
    principal: SupabasePrincipal, *, library: Library | None = None
) -> QuerySet[ChatSession]:
    queryset = ChatSession.objects.filter(owner_id=owner_id(principal))
    if library is not None:
        queryset = queryset.filter(library=library)
    return queryset


def profile_for(principal: SupabasePrincipal) -> Profile | None:
    return Profile.objects.filter(pk=owner_id(principal)).first()
