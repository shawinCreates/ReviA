from django.urls import path

from .library_views import LibraryDetailView, LibraryListCreateView
from .upload_views import (
    DocumentCreateView,
    DocumentDetailView,
    DocumentIngestView,
    LibraryDocumentListView,
)
from .views import HealthView, MeView

urlpatterns = [
    # Unauthenticated. Kept outside the auth middleware via PUBLIC_PATHS.
    path("health", HealthView.as_view(), name="health"),
    path("me", MeView.as_view(), name="me"),
    # Libraries. A document belongs to one, so this is the entry point to upload.
    path("libraries", LibraryListCreateView.as_view(), name="library-list-create"),
    path(
        "libraries/<uuid:library_id>",
        LibraryDetailView.as_view(),
        name="library-detail",
    ),
    # Upload flow. See upload_views.py for why it is three calls and not one.
    path("documents", DocumentCreateView.as_view(), name="document-create"),
    path(
        "documents/<uuid:document_id>",
        DocumentDetailView.as_view(),
        name="document-detail",
    ),
    path(
        "documents/<uuid:document_id>/ingest",
        DocumentIngestView.as_view(),
        name="document-ingest",
    ),
    path(
        "libraries/<uuid:library_id>/documents",
        LibraryDocumentListView.as_view(),
        name="library-documents",
    ),
]
