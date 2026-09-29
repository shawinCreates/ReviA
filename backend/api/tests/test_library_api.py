"""
Library endpoint tests.

These are the first screen of the product, so the properties that matter are
authorization and counting: a user must never see another user's library, and
the counts the list returns are what the UI uses to decide whether an upload is
even allowed.
"""

from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from api.models import Document, Library, Profile

pytestmark = pytest.mark.django_db


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
    return Profile.objects.create(id=uuid.uuid4(), email="lib@example.com")


@pytest.fixture
def other(db):
    return Profile.objects.create(id=uuid.uuid4(), email="other@example.com")


class TestList:
    def test_empty_list_for_a_new_user(self, authed, profile):
        response = authed(profile).get("/api/libraries")
        assert response.status_code == 200
        assert response.data == []

    def test_lists_only_the_callers_libraries(self, authed, profile, other):
        Library.objects.create(owner=profile, title="Mine")
        Library.objects.create(owner=other, title="Theirs")

        response = authed(profile).get("/api/libraries")
        assert [lib["title"] for lib in response.data] == ["Mine"]

    def test_counts_documents_and_ready_documents(self, authed, profile):
        library = Library.objects.create(owner=profile, title="Mine")
        for status in [
            Document.STATUS_READY,
            Document.STATUS_READY,
            Document.STATUS_INDEXING,
            Document.STATUS_FAILED,
        ]:
            Document.objects.create(
                library=library,
                filename="a.pdf",
                storage_path="k",
                mime="application/pdf",
                size_bytes=1,
                status=status,
            )

        (row,) = authed(profile).get("/api/libraries").data
        assert row["document_count"] == 4
        assert row["ready_count"] == 2

    def test_oldest_first_so_the_first_created_is_the_default(self, authed, profile):
        Library.objects.create(owner=profile, title="First")
        Library.objects.create(owner=profile, title="Second")
        titles = [lib["title"] for lib in authed(profile).get("/api/libraries").data]
        assert titles == ["First", "Second"]


class TestCreate:
    def test_creates_and_returns_the_library(self, authed, profile):
        response = authed(profile).post(
            "/api/libraries", {"title": "  Cell biology  "}, format="json"
        )
        assert response.status_code == 201, response.data
        assert response.data["title"] == "Cell biology"  # trimmed
        assert response.data["document_count"] == 0
        assert response.data["ready_count"] == 0

        library = Library.objects.get(id=response.data["id"])
        assert library.owner_id == profile.id

    def test_missing_title_is_rejected(self, authed, profile):
        response = authed(profile).post("/api/libraries", {}, format="json")
        assert response.status_code == 400
        assert response.data["error"]["code"] == "bad_request"

    def test_whitespace_only_title_is_rejected(self, authed, profile):
        response = authed(profile).post(
            "/api/libraries", {"title": "   "}, format="json"
        )
        assert response.status_code == 400

    def test_overlong_title_is_rejected(self, authed, profile):
        response = authed(profile).post(
            "/api/libraries", {"title": "x" * 201}, format="json"
        )
        assert response.status_code == 400
        assert not Library.objects.filter(owner=profile).exists()


class TestDetail:
    def test_returns_the_library_with_its_documents(self, authed, profile):
        library = Library.objects.create(owner=profile, title="Mine")
        Document.objects.create(
            library=library,
            filename="paper.pdf",
            storage_path="k",
            mime="application/pdf",
            size_bytes=10,
        )

        response = authed(profile).get(f"/api/libraries/{library.id}")
        assert response.status_code == 200
        assert response.data["title"] == "Mine"
        assert [d["filename"] for d in response.data["documents"]] == ["paper.pdf"]

    def test_another_users_library_is_not_found(self, authed, profile, other):
        library = Library.objects.create(owner=other, title="Theirs")
        response = authed(profile).get(f"/api/libraries/{library.id}")
        assert response.status_code == 404
        assert response.data["error"]["code"] == "not_found"


class TestAuth:
    def test_list_requires_a_token(self, client):
        assert client.get("/api/libraries").status_code == 401

    def test_create_requires_a_token(self, client):
        response = client.post("/api/libraries", {"title": "X"}, format="json")
        assert response.status_code == 401
        assert not Library.objects.exists()
