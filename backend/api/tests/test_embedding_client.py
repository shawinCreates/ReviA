from __future__ import annotations

import json
import math

import httpx
import pytest
from django.conf import settings

from api import embedding_client
from api.embedding_client import EmbeddingError, embed_query, embed_texts


@pytest.fixture
def cloudflare_ready(monkeypatch):
    # Pin every value the provider reads; the developer's .env would leak in.
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "test-account-id")
    monkeypatch.setattr(settings, "CLOUDFLARE_API_TOKEN", "test-token")
    monkeypatch.setattr(settings, "EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    monkeypatch.setattr(settings, "EMBEDDING_DIM", 384)
    monkeypatch.setattr(settings, "EMBEDDING_QUERY_PREFIX", "Q: ")


class _Scripted:
    """Plays responses in order and records every request seen, body included."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the client sent more requests than the script allows")
        if callable(self.responses[0]):
            return self.responses[0](request)
        step = self.responses.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content.decode())


@pytest.fixture
def cloudflare_api(monkeypatch, cloudflare_ready):
    def _install(*responses) -> _Scripted:
        scripted = _Scripted(responses)
        client = httpx.Client(transport=httpx.MockTransport(scripted))
        monkeypatch.setattr(embedding_client, "_cloudflare_client", lambda: client)
        # Real waits would add ~2.5s to the suite; zero them out here.
        monkeypatch.setattr(embedding_client, "_backoff", lambda attempt: 0.0)
        return scripted

    return _install


def _row(head: float, second: float = 0.0) -> list[float]:
    return [head, second] + [0.0] * 382


def _success(rows: list[list[float]]) -> httpx.Response:
    return httpx.Response(200, json={"result": {"data": rows}, "success": True})


def _quota_response() -> httpx.Response:
    return httpx.Response(
        400,
        json={
            "result": None,
            "success": False,
            "errors": [
                {
                    "code": 4006,
                    "message": "you have used up your daily free allocation "
                    "of 10,000 neurons",
                }
            ],
        },
    )


def _model_failure() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "result": None,
            "success": False,
            "errors": [{"code": 3041, "message": "model inference failed"}],
        },
    )


# --- request shape ---------------------------------------------------------------


def test_a_query_is_sent_with_the_prefix_and_cls_pooling(cloudflare_api):
    scripted = cloudflare_api(_success([_row(1.0)]))

    embed_query("how do gradients flow?")

    request = scripted.requests[0]
    body = scripted.body()
    assert body["pooling"] == "cls"
    assert body["text"] == [settings.EMBEDDING_QUERY_PREFIX + "how do gradients flow?"]
    assert "https://api.cloudflare.com/client/v4/accounts/test-account-id/ai/run/" in str(
        request.url
    )
    assert "bge-small-en-v1.5" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-token"


def test_a_passage_is_sent_raw(cloudflare_api):
    scripted = cloudflare_api(_success([_row(1.0)]))

    embed_texts(["plain passage text"])

    body = scripted.body()
    assert body["text"] == ["plain passage text"]
    assert body["pooling"] == "cls"


def test_a_large_document_splits_into_batches_without_losing_order(cloudflare_api):
    texts = [f"chunk {index}" for index in range(70)]
    counts: list[int] = []

    def _respond(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content.decode())["text"]
        position = sum(counts)
        counts.append(len(batch))
        rows = [[1.0, float(position + offset)] + [0.0] * 382 for offset in range(len(batch))]
        return _success(rows)

    cloudflare_api(_respond)

    vectors = embed_texts(texts)

    assert counts == [embedding_client.BATCH_SIZE, embedding_client.BATCH_SIZE, 70 - 64]
    assert len(vectors) == 70
    for index, vector in enumerate(vectors):
        scale = math.sqrt(1.0 + index * index)
        assert vector[1] == pytest.approx(index / scale)
        assert vector[0] == pytest.approx(1.0 / scale)


# --- response handling ------------------------------------------------------------


def test_vectors_come_back_unit_normalised(cloudflare_api):
    cloudflare_api(_success([_row(1.0, 2.0)]))

    vectors = embed_texts(["anything"])

    assert vectors[0][0] == pytest.approx(1.0 / math.sqrt(5.0))
    assert vectors[0][1] == pytest.approx(2.0 / math.sqrt(5.0))
    assert all(component == 0.0 for component in vectors[0][2:])


def test_normalisation_survives_an_all_zero_row(cloudflare_api):
    cloudflare_api(_success([_row(0.0), _row(1.0)]))

    vectors = embed_texts(["empty", "one"])

    assert vectors[0] == [0.0] * 384


def test_missing_data_row_is_a_contract_error(cloudflare_api):
    cloudflare_api(httpx.Response(200, json={"result": {}, "success": True}))

    with pytest.raises(EmbeddingError) as raised:
        embed_texts(["anything"])

    assert raised.value.retryable is True
    assert "no data array" in raised.value.reason


def test_the_wrong_row_count_is_reported(cloudflare_api):
    cloudflare_api(_success([_row(1.0), _row(2.0)]))

    with pytest.raises(EmbeddingError) as raised:
        embed_texts(["only one text"])

    assert raised.value.retryable is True
    assert "2 vectors for 1 inputs" in raised.value.reason


# --- failure handling --------------------------------------------------------------


def test_the_daily_quota_is_reported_once_with_the_reset_time(cloudflare_api):
    scripted = cloudflare_api(_quota_response())

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert len(scripted.requests) == 1
    assert raised.value.retryable is False
    assert "00:00 UTC" in raised.value.reason


def test_the_daily_quota_is_caught_inside_a_200(cloudflare_api):
    depleted = httpx.Response(
        200,
        json={
            "result": None,
            "success": False,
            "errors": [
                {"code": 4006, "message": "daily free allocation spent"},
            ],
        },
    )
    scripted = cloudflare_api(depleted)

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert len(scripted.requests) == 1
    assert raised.value.retryable is False


def test_a_model_failure_inside_a_200_is_retried(cloudflare_api):
    scripted = cloudflare_api(_model_failure(), _success([_row(1.0)]))

    vector = embed_query("anything")

    assert len(scripted.requests) == 2
    assert len(vector) == 384


def test_a_rate_limit_is_retried(cloudflare_api):
    scripted = cloudflare_api(
        httpx.Response(429, json={"errors": [{"code": 5, "message": "rate"}]}),
        _success([_row(1.0)]),
    )

    vector = embed_query("anything")

    assert len(scripted.requests) == 2
    assert len(vector) == 384


def test_a_transport_failure_is_retried(cloudflare_api):
    scripted = cloudflare_api(httpx.ConnectError("connection reset"), _success([_row(1.0)]))

    vector = embed_query("anything")

    assert len(scripted.requests) == 2
    assert len(vector) == 384


def test_persistent_failures_run_out_of_attempts_and_stay_retryable(cloudflare_api):
    scripted = cloudflare_api(
        *([httpx.Response(500, json={"errors": []})] * embedding_client.MAX_ATTEMPTS)
    )

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert len(scripted.requests) == embedding_client.MAX_ATTEMPTS
    assert raised.value.retryable is True
    assert "500" in raised.value.reason


def test_rejected_credentials_are_fatal_and_name_the_variable(cloudflare_api):
    scripted = cloudflare_api(
        httpx.Response(
            403,
            json={
                "result": None,
                "success": False,
                "errors": [{"code": 9109, "message": "Unauthorized"}],
            },
        )
    )

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert len(scripted.requests) == 1
    assert raised.value.retryable is False
    assert "CLOUDFLARE_API_TOKEN" in raised.value.reason


def test_a_rejected_request_names_what_to_check(cloudflare_api):
    scripted = cloudflare_api(
        httpx.Response(
            400,
            json={
                "result": None,
                "success": False,
                "errors": [{"code": 7503, "message": "invalid request"}],
            },
        )
    )

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert len(scripted.requests) == 1
    assert raised.value.retryable is False
    assert "7503" in raised.value.reason
    assert "CLOUDFLARE_ACCOUNT_ID" in raised.value.reason


def test_missing_configuration_fails_before_any_request(monkeypatch):
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "CLOUDFLARE_API_TOKEN", "")

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert raised.value.retryable is False
    assert "not configured" in raised.value.reason


def test_an_unsupported_model_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "EMBED_MODEL", "BAAI/bge-base-en-v1.5")

    with pytest.raises(EmbeddingError) as raised:
        embed_query("anything")

    assert raised.value.retryable is False
    assert "BAAI/bge-small-en-v1.5" in raised.value.reason
