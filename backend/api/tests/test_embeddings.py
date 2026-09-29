"""
Local embedding tests.

The dimension assertion is the load-bearing part. A wrong-dimension vector is
rejected by pgvector at INSERT time, long after the model was swapped, so the
guarantee has to hold at the embedder boundary instead. See risks.md R-8.
"""

from __future__ import annotations

import numpy as np
import pytest
from django.conf import settings

from api.embeddings import assert_dimensions, embed_query, embed_texts


@pytest.fixture(scope="module")
def vectors():
    return embed_texts(
        [
            "the mitochondria is the powerhouse of the cell",
            "a passage describing a rotated figure caption",
            "left column text on the first page",
        ]
    )


class TestShape:
    def test_batch_shape_matches_configured_dimension(self, vectors):
        assert vectors.shape == (3, settings.EMBEDDING_DIM)

    def test_dtype_is_float32(self, vectors):
        """float64 doubles the storage of every vector and slows the HNSW build."""
        assert vectors.dtype == np.float32

    def test_query_is_one_dimensional(self):
        assert embed_query("anything").shape == (settings.EMBEDDING_DIM,)

    def test_empty_batch_is_handled_without_loading_anything(self):
        empty = embed_texts([])
        assert empty.shape == (0, settings.EMBEDDING_DIM)


class TestNormalisation:
    def test_vectors_are_unit_length(self, vectors):
        """Cosine similarity is a plain dot product only if vectors are unit."""
        norms = np.linalg.norm(vectors, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)


class TestRetrievalSanity:
    def test_matching_text_scores_higher_than_unrelated(self, vectors):
        query = embed_query("powerhouse of the cell")
        similarities = query @ vectors.T
        assert int(np.argmax(similarities)) == 0
        assert similarities[0] > similarities[1]
        assert similarities[0] > similarities[2]

    def test_embedding_is_deterministic(self, vectors):
        """Re-embedding the same text must give the same vector, or the index
        drifts and identical content stops being findable."""
        again = embed_texts(
            [
                "the mitochondria is the powerhouse of the cell",
                "a passage describing a rotated figure caption",
                "left column text on the first page",
            ]
        )
        assert np.allclose(vectors, again, atol=1e-5)


class TestDimensionAssertion:
    def test_matching_dimension_passes(self):
        assert_dimensions(np.zeros((2, settings.EMBEDDING_DIM), dtype=np.float32))

    def test_wrong_dimension_raises_with_an_actionable_message(self):
        with pytest.raises(ValueError) as excinfo:
            assert_dimensions(np.zeros((2, 1024), dtype=np.float32))
        message = str(excinfo.value)
        assert str(settings.EMBEDDING_DIM) in message
        # A 1024-dim vector is the old Cloudflare bge-m3 shape, so the error
        # must say what actually changed and what has to happen to stored data.
        assert "re-embedding" in message.lower()

    def test_one_dimensional_input_raises(self):
        with pytest.raises(ValueError):
            assert_dimensions(np.zeros(settings.EMBEDDING_DIM, dtype=np.float32))
