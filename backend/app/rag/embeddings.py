"""Text embeddings for retrieval.

`OnnxEmbedder` runs a small multilingual model (int8-quantized
paraphrase-multilingual-MiniLM-L12-v2, 118 MB) with onnxruntime + tokenizers only: no PyTorch,
small enough for a serverless function bundle, no API calls (visitor questions never leave the
server for embedding). The SAME model embeds the chunks at build time (the index artifact) and
the queries at request time. `FakeEmbedder` is deterministic and offline, for tests.

Model choice (step 10, `evals.run_retrieval`, 35 EN/AR cases, app settings top 6 / 1000
tokens): MiniLM-L12 int8 Recall@6 1.000 EN and AR at RAG_MIN_SCORE 0.25; multilingual-e5-small
int8 0.944 EN; e5-base int8 0.944 / 0.941; e5-large int8 (too big anyway) 0.944 EN.
"""

import hashlib
import logging
import math
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class OnnxModel:
    repo: str  # Hugging Face repo with ONNX exports
    file: str  # the ONNX file inside it
    revision: str  # pinned commit: reproducible builds
    max_length: int = 128
    query_prefix: str = ""
    passage_prefix: str = ""


ONNX_MODELS: dict[str, OnnxModel] = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": OnnxModel(
        "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
        "onnx/model_quantized.onnx",
        "2c4055b12046f11709e9df2c122e59ffbdc2f900",
        max_length=128,
    ),
}


def onnx_model_files(model_name: str, cache_dir: Path) -> tuple[Path, Path]:
    """(model.onnx, tokenizer.json) for `model_name`, downloaded into `cache_dir` if missing."""
    spec = ONNX_MODELS.get(model_name)
    if spec is None:
        raise ValueError(f"No ONNX export configured for {model_name!r}")
    local = cache_dir / spec.repo.replace("/", "--")
    model_path, tokenizer_path = local / spec.file, local / "tokenizer.json"
    if not (model_path.is_file() and tokenizer_path.is_file()):
        from huggingface_hub import hf_hub_download  # build time only

        for remote in (spec.file, "tokenizer.json"):  # straight into `local`: no second copy
            hf_hub_download(spec.repo, remote, revision=spec.revision, local_dir=local)
        missing = [p.name for p in (model_path, tokenizer_path) if not p.is_file()]
        if missing:
            raise RuntimeError(f"Model download incomplete for {model_name}: {missing}")
        logger.info("Model %s downloaded to %s", model_name, local)
    return model_path, tokenizer_path


class OnnxEmbedder:
    """Mean-pooled, L2-normalized sentence embeddings from an ONNX transformer."""

    def __init__(self, model_name: str, cache_dir: Path, threads: int | None = None) -> None:
        import onnxruntime as ort  # heavy imports: only when really used
        from tokenizers import Tokenizer

        model_path, tokenizer_path = onnx_model_files(model_name, cache_dir)
        spec = ONNX_MODELS[model_name]
        self.name = model_name
        self._query_prefix, self._passage_prefix = spec.query_prefix, spec.passage_prefix
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(spec.max_length)
        self._tokenizer.enable_padding()
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(model_path), options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._session.get_inputs()}

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        import numpy as np

        encodings = self._tokenizer.encode_batch(list(texts))
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = self._session.run(None, feeds)[0]  # (batch, tokens, dim)
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
        return pooled.astype(np.float32).tolist()

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [self._passage_prefix + text for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(prefixed), 16):
            vectors += self._embed(prefixed[start : start + 16])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query_prefix + text])[0]


class LazyEmbedder:
    """Loads the real embedder in a background thread, so startup (and requests that never
    search, like the content API the page calls first) does not wait for ~200 MB of model and
    runtime to be read from a cold serverless filesystem. `name` is known at once (the index
    hash check needs no model); the first query waits for the load to finish."""

    def __init__(self, name: str, factory: Callable[[], Embedder]) -> None:
        self.name = name
        self._started = time.perf_counter()
        self._future = ThreadPoolExecutor(1, thread_name_prefix="embedder").submit(
            self._load, factory
        )

    def _load(self, factory: Callable[[], Embedder]) -> Embedder:
        embedder = factory()
        logger.info("Embedder %s loaded in %.2fs", self.name, time.perf_counter() - self._started)
        return embedder

    @property
    def ready(self) -> bool:
        return self._future.done()

    def get(self) -> Embedder:
        return self._future.result()

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self.get().embed_passages(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.get().embed_query(text)


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
    """Fetch the model files into the cache (build step / first start)."""
    onnx_model_files(model_name, cache_dir)
    logger.info("Model %s is cached in %s", model_name, cache_dir)
