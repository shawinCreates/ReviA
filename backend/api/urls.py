from __future__ import annotations

from django.urls import path

from api.views import (
    AskView,
    ChatSessionDetailView,
    ChatSessionListView,
    DemoPrincipalView,
    DocumentDetailView,
    DocumentListView,
    LibraryListView,
    MeView,
    UploadDocumentView,
)

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("session", DemoPrincipalView.as_view(), name="session"),
    path("libraries", LibraryListView.as_view(), name="libraries"),
    path("documents", DocumentListView.as_view(), name="documents"),
    path("documents/upload", UploadDocumentView.as_view(), name="document-upload"),
    path("documents/<uuid:document_id>", DocumentDetailView.as_view(), name="document-detail"),
    path("chat/ask", AskView.as_view(), name="chat-ask"),
    path("chat/sessions", ChatSessionListView.as_view(), name="chat-sessions"),
    path("chat/sessions/<uuid:session_id>", ChatSessionDetailView.as_view(), name="chat-session"),
]
