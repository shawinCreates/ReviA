from __future__ import annotations

import numpy as np


def as_query_vector(embedding) -> list[float]:
    array = np.asarray(embedding, dtype=np.float32).reshape(-1)
    return array.tolist()
