"""The library and document endpoints.

These go through authentication, so they are also the only tests that prove the
scoping helpers and the request path fit together: a client signed in as one
Supabase user must not see another user's rows.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from api.models import Document, DocumentStage, Library

pytestmark = pytest.mark.django_db


def test_libraries_requires_authentication():
    response = APIClient().get("/api/v1/libraries")

    assert response.status_code == 401


def test_documents_requires_authentication():
    response = APIClient().get("/api/v1/documents")

    assert response.status_code == 401


def test_the_first_request_provisions_a_default_library(auth_client):
    response = auth_client().get("/api/v1/libraries")

    assert response.status_code == 200
    libraries = response.json()["libraries"]
    assert len(libraries) == 1
    assert libraries[0]["is_default"] is True
    assert libraries[0]["document_count"] == 0


def test_the_default_library_is_not_recreated_on_every_request(auth_client):
    client = auth_client()

    first = client.get("/api/v1/libraries").json()["libraries"]
    second = client.get("/api/v1/libraries").json()["libraries"]

    assert [library["id"] for library in first] == [library["id"] for library in second]
    assert Library.objects.filter(is_default=True).count() == 1


def test_a_second_library_is_listed_alongside_the_default(auth_client):
    client = auth_client()
    client.get("/api/v1/libraries")
    Library.objects.create(owner_id=client.owner_id, name="Papers")

    libraries = client.get("/api/v1/libraries").json()["libraries"]

    # The default comes first, so the frontend can render it as selected without
    # sorting the list itself.
    assert [library["name"] for library in libraries] == ["My library", "Papers"]


def test_a_document_appears_in_the_listing_with_its_stage(auth_client):
    client = auth_client()
    library = client.get("/api/v1/libraries").json()["libraries"][0]
    Document.objects.create(
        owner_id=client.owner_id,
        library_id=library["id"],
        filename="paper.pdf",
        storage_path="paper.pdf",
    )

    payload = client.get("/api/v1/documents").json()

    assert [document["filename"] for document in payload["documents"]] == ["paper.pdf"]
    assert payload["documents"][0]["extension"] == ".pdf"
    assert payload["documents"][0]["stage"] == DocumentStage.QUEUED.value
    assert payload["documents"][0]["stage_label"] == "Queued"
    assert payload["stage_counts"][DocumentStage.QUEUED.value] == 1


def test_documents_can_be_narrowed_to_one_library(auth_client):
    client = auth_client()
    default_library = client.get("/api/v1/libraries").json()["libraries"][0]
    other = Library.objects.create(owner_id=client.owner_id, name="Papers")
    Document.objects.create(
        owner_id=client.owner_id, library_id=default_library["id"], filename="a.pdf"
    )
    Document.objects.create(owner_id=client.owner_id, library=other, filename="b.pdf")

    payload = client.get(f"/api/v1/documents?library={other.id}").json()

    assert [document["filename"] for document in payload["documents"]] == ["b.pdf"]


def test_another_accounts_library_is_a_404_rather_than_an_empty_list(auth_client):
    """A 200 with an empty list would confirm the library exists."""
    their_library = auth_client().get("/api/v1/libraries").json()["libraries"][0]

    response = auth_client().get(f"/api/v1/documents?library={their_library['id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_another_accounts_documents_are_never_listed(auth_client):
    their_client = auth_client()
    their_library = their_client.get("/api/v1/libraries").json()["libraries"][0]
    Document.objects.create(
        owner_id=their_client.owner_id, library_id=their_library["id"], filename="secret.pdf"
    )

    payload = auth_client().get("/api/v1/documents").json()

    assert payload["documents"] == []
    assert all(total == 0 for total in payload["stage_counts"].values())


def test_a_library_count_reflects_the_documents_in_it(auth_client):
    client = auth_client()
    library = client.get("/api/v1/libraries").json()["libraries"][0]
    Document.objects.create(owner_id=client.owner_id, library_id=library["id"], filename="a.pdf")
    Document.objects.create(owner_id=client.owner_id, library_id=library["id"], filename="b.pdf")

    libraries = client.get("/api/v1/libraries").json()["libraries"]

    assert libraries[0]["document_count"] == 2
