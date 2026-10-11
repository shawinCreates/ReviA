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
    return str(principal.id)


def libraries_for(principal: SupabasePrincipal) -> QuerySet[Library]:
    return Library.objects.filter(owner_id=owner_id(principal))


def documents_for(
    principal: SupabasePrincipal, *, library: Library | None = None
) -> QuerySet[Document]:
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
