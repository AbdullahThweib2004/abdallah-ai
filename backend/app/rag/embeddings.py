"""Text embeddings for retrieval.

`FastEmbedEmbedder` runs a multilingual ONNX model locally (no API cost, no PyTorch); model
files are cached in `backend/.models/`. `FakeEmbedder` is deterministic and offline, for tests.
"""

import hashlib
import logging
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

# Models that expect instruction prefixes (e5 family: "query: " / "passage: ").
PREFIXES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}


class Embedder(Protocol):
    name: str

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str, cache_dir: Path, threads: int | None = None) -> None:
        from fastembed import TextEmbedding  # heavy import: only when really used

        self.name = model_name
        self._query_prefix, self._passage_prefix = PREFIXES.get(model_name, ("", ""))
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(
            model_name=model_name, cache_dir=str(cache_dir), threads=threads
        )

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [self._passage_prefix + text for text in texts]
        return [vector.tolist() for vector in self._model.embed(prefixed, batch_size=16)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([self._query_prefix + text]))).tolist()


_TOKEN = re.compile(r"[^\W_]+")


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder: similar wording → similar vectors."""

    name = "fake-hashing-256"
    dim = 256

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            bucket = int.from_bytes(hashlib.sha1(token.encode()).digest()[:4], "big") % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def download_model(model_name: str, cache_dir: Path) -> None:
    """Fetch the model files into the cache (for deployment images / first start)."""
    FastEmbedEmbedder(model_name, cache_dir)
    logger.info("Model %s is cached in %s", model_name, cache_dir)
