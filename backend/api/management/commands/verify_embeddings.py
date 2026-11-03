from __future__ import annotations

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from api.embedding_client import EmbeddingError, embed_query, embed_texts

#: Chunk-length samples; few enough tokens to spare the free allocation.
SAMPLES = [
    "The electron transport chain is a series of protein complexes embedded in "
    "the inner mitochondrial membrane, and it converts energy from redox "
    "reactions into a proton gradient across that membrane.",
    "Bayes' theorem describes the probability of an event, based on prior "
    "knowledge of conditions that might be related to the event, and it is the "
    "foundation of Bayesian statistics.",
    "Photosynthesis converts light energy into chemical energy that is stored "
    "in carbohydrates, using water and carbon dioxide, and oxygen is released "
    "as a by-product.",
]

#: What a query carries in production; sending it exercises the prefixed path.
QUERY = "how does the electron transport chain store energy?"


class Command(BaseCommand):
    help = "Embeds sample text through the production path and reports what came back."

    def handle(self, *args, **options) -> None:
        from django.conf import settings

        self.stdout.write(
            f"EMBED_MODEL={settings.EMBED_MODEL} EMBEDDING_DIM={settings.EMBEDDING_DIM}"
        )

        try:
            passages = embed_texts(SAMPLES)
            enquiry = embed_query(QUERY)
        except EmbeddingError as exc:
            raise CommandError(exc.reason) from exc

        norms = [float(np.linalg.norm(vector)) for vector in passages]
        self.stdout.write(
            f"{len(passages)} passage vector(s) of {len(passages[0])} dimension(s), "
            f"unit-norm [{min(norms):.4f} .. {max(norms):.4f}], "
            f"query vector {len(enquiry)} dimension(s)"
        )
        self.stdout.write(self.style.SUCCESS("The embedding path returned usable vectors."))
