"""
Upload and ingest HTTP tests.

These test the API surface rather than the ingest internals already covered in
test_ingest.py: the validation rules, the ownership checks, and the error
envelope. Presigned URL generation is mocked, because signing needs live
credentials and what matters here is that the endpoint calls it and returns the
result.

Auth uses real ES256 tokens rather than `force_authenticate`, because auth runs
in middleware before DRF and `force_authenticate` never reaches it. The `sub`
claim must equal the Profile's id, since the middleware resolves the user from
the token: a mismatched id would authenticate as a stranger.
"""

from __future__ import annotations

import pathlib
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from api.models import Chunk, Document, Library, Page, Profile

pytestmark = pytest.mark.django_db

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"
SIGNED_URL = "https://storage.example.com/bucket/key?X-Amz-Signature=abc"


@pytest.fixture
def client(jwks_server):
    return APIClient()


@pytest.fixture
def authed(client, make_token):
    def _authed(profile: Profile) -> APIClient:
        token = make_token(subject=str(profile.id), email=profile.email)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return client

    return _authed


@pytest.fixture
def profile(db):
    return Profile.objects.create(id=uuid.uuid4(), email="upload@example.com")


@pytest.fixture
def other(db):
    return Profile.objects.create(id=uuid.uuid4(), email="other@example.com")


@pytest.fixture
def library(profile):
    return Library.objects.create(owner=profile, title="Mine")


def body(library, **overrides):
    payload = {
        "library_id": str(library.id),
        "filename": "paper.pdf",
        "mime": "application/pdf",
        "size_bytes": 2048,
    }
    payload.update(overrides)
    return payload


class TestDocumentCreate:
    @patch("api.storage.presigned_upload_url", return_value=SIGNED_URL)
    def test_creates_a_queued_document_and_returns_an_upload_url(
        self, sign, authed, profile, library
    ):
        response = authed(profile).post("/api/documents", body(library), format="json")
        assert response.status_code == 201, response.data
        assert response.data["status"] == Document.STATUS_QUEUED
        assert response.data["upload_url"] == SIGNED_URL
        assert response.data["upload_headers"] == {"Content-Type": "application/pdf"}
        sign.assert_called_once()

        document = Document.objects.get(id=response.data["id"])
        assert document.storage_path == response.data["storage_path"]

    @patch("api.storage.presigned_upload_url", return_value=SIGNED_URL)
    def test_storage_keys_do_not_collide_for_identical_filenames(
        self, sign, authed, profile, library
    ):
        first = authed(profile).post("/api/documents", body(library), format="json")
        second = authed(profile).post("/api/documents", body(library), format="json")
        assert first.data["storage_path"] != second.data["storage_path"]

    def test_rejects_unsupported_mime(self, authed, profile, library):
        response = authed(profile).post(
            "/api/documents", body(library, mime="application/zip"), format="json"
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "unsupported_type"

    def test_rejects_oversized_file(self, authed, profile, library):
        response = authed(profile).post(
            "/api/documents", body(library, size_bytes=500 * 1024 * 1024), format="json"
        )
        assert response.status_code == 413
        assert response.data["error"]["code"] == "file_too_large"

    def test_rejects_empty_file(self, authed, profile, library):
        response = authed(profile).post(
            "/api/documents", body(library, size_bytes=0), format="json"
        )
        assert response.status_code == 400

    def test_rejects_missing_filename(self, authed, profile, library):
        response = authed(profile).post(
            "/api/documents", body(library, filename=""), format="json"
        )
        assert response.status_code == 400

    def test_rejects_non_numeric_size(self, authed, profile, library):
        response = authed(profile).post(
            "/api/documents", body(library, size_bytes="huge"), format="json"
        )
        assert response.status_code == 400

    def test_another_users_library_is_not_found(self, authed, other, library):
        response = authed(other).post("/api/documents", body(library), format="json")
        assert response.status_code == 404
        assert response.data["error"]["code"] == "not_found"

    def test_library_document_cap_is_enforced(
        self, authed, profile, library, settings
    ):
        settings.MAX_DOCS_PER_LIBRARY = 2
        with patch("api.storage.presigned_upload_url", return_value=SIGNED_URL):
            for _ in range(2):
                authed(profile).post("/api/documents", body(library), format="json")
        response = authed(profile).post("/api/documents", body(library), format="json")
        assert response.status_code == 409
        assert response.data["error"]["code"] == "library_full"

    def test_anonymous_request_is_rejected(self, client, library):
        response = client.post("/api/documents", body(library), format="json")
        assert response.status_code == 401

    @patch("api.storage.presigned_upload_url", side_effect=Exception("no bucket"))
    def test_signing_failure_removes_the_orphan_row(self, sign, authed, profile, library):
        response = authed(profile).post("/api/documents", body(library), format="json")
        assert response.status_code == 503
        # A row with no object and no signed URL can never be ingested, and it
        # would count against the library cap forever.
        assert Document.objects.filter(library=library).count() == 0


class TestDocumentDetail:
    def test_returns_progress_for_the_owner(self, authed, profile, library):
        document = Document.objects.create(
            library=library,
            filename="a.pdf",
            storage_path="k",
            mime="application/pdf",
            size_bytes=1,
            status=Document.STATUS_INDEXING,
            ingest_cursor=5,
        )
        response = authed(profile).get(f"/api/documents/{document.id}")
        assert response.status_code == 200
        assert response.data["ingest_cursor"] == 5
        assert response.data["status"] == Document.STATUS_INDEXING

    def test_another_user_gets_404(self, authed, other, library):
        document = Document.objects.create(
            library=library,
            filename="a.pdf",
            storage_path="k",
            mime="application/pdf",
            size_bytes=1,
        )
        assert authed(other).get(f"/api/documents/{document.id}").status_code == 404


class TestLibraryList:
    @patch("api.storage.presigned_upload_url", return_value=SIGNED_URL)
    def test_lists_documents_with_the_cap(self, sign, authed, profile, library):
        for _ in range(3):
            authed(profile).post("/api/documents", body(library), format="json")
        response = authed(profile).get(f"/api/libraries/{library.id}/documents")
        assert response.status_code == 200
        assert response.data["library"]["document_count"] == 3
        assert response.data["library"]["max_documents"] == 20
        assert len(response.data["documents"]) == 3

    def test_another_user_gets_404(self, authed, other, library):
        response = authed(other).get(f"/api/libraries/{library.id}/documents")
        assert response.status_code == 404


class TestIngestEndpoint:
    """
    Exercises the real HTTP path, mocking only the download from Storage.
    Everything after the bytes are in memory is genuine: real parse, real
    chunks, real ONNX embeddings, real rows.
    """

    def _doc(self, library, name="notes.md"):
        return Document.objects.create(
            library=library,
            filename=name,
            storage_path=f"{library.id}/{name}",
            mime="text/markdown",
            size_bytes=1024,
        )

    def test_ingest_endpoint_drives_a_document_to_ready(self, authed, profile, library):
        source = FIXTURES / "notes.md"
        document = self._doc(library)

        with patch(
            "django.core.files.storage.default_storage.size", return_value=1024
        ), patch("django.core.files.storage.default_storage.open") as opener:
            opener.return_value.__enter__.return_value.read.return_value = (
                source.read_bytes()
            )
            response = authed(profile).post(f"/api/documents/{document.id}/ingest")

        assert response.status_code == 200, response.data
        assert response.data["done"] is True
        assert Page.objects.filter(document=document).count() == 1
        assert Chunk.objects.filter(document=document).count() >= 1

    def test_missing_upload_fails_with_an_actionable_message(
        self, authed, profile, library
    ):
        document = self._doc(library)
        with patch(
            "django.core.files.storage.default_storage.size",
            side_effect=FileNotFoundError("gone"),
        ):
            response = authed(profile).post(f"/api/documents/{document.id}/ingest")
        # The HTTP call succeeded; the document did not. 200 with status=failed
        # and a message the UI can show verbatim.
        assert response.status_code == 200
        assert response.data["status"] == Document.STATUS_FAILED
        assert response.data["done"] is True
        assert "upload" in response.data["error"].lower()

    def test_ingesting_another_users_document_is_404(self, authed, other, library):
        document = self._doc(library)
        response = authed(other).post(f"/api/documents/{document.id}/ingest")
        assert response.status_code == 404

    def test_unknown_document_is_404(self, authed, profile):
        response = authed(profile).post(f"/api/documents/{uuid.uuid4()}/ingest")
        assert response.status_code == 404
