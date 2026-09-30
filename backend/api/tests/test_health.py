from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_reports_ok_when_database_is_reachable():
    response = APIClient().get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


@pytest.mark.django_db
def test_health_reports_degraded_without_raising(monkeypatch):
    """A probe must report an unreachable database, not 500 on it."""
    from django.db import connection

    class Boom:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            raise RuntimeError("connection refused")

        def fetchone(self):
            return None

    monkeypatch.setattr(connection, "cursor", lambda *a, **k: Boom())

    response = APIClient().get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unreachable"
    assert body["database_error"] == "RuntimeError"


def test_health_needs_no_authentication():
    """No cookie, no credentials, still answers."""
    response = APIClient().get("/api/v1/health")
    assert response.status_code == 200
