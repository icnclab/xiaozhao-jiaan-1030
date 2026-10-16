"""Embedding provider adapters。

- `hash`：字元 n-gram 雜湊向量（決定性、零下載、語意弱）。用來讓系統在沒有中文
  embedding 模型時仍能運作；混合檢索的全文部分負責主要的詞彙比對。
- `ollama`：呼叫本機 Ollama `/api/embed`（例如 bge-m3）。

向量維度固定為 `EMBEDDING_DIM`（1024），與資料庫欄位一致；換模型需重新嵌入。
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import httpx
import numpy as np

from app.config import get_settings
from app.services.text import normalize


class EmbeddingProvider(Protocol):
    """Embedding adapter 介面。"""

    name: str
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """把文字轉成等長向量。"""
        ...


class HashEmbedding:
    """字元 1～3-gram 的有號雜湊向量（signed feature hashing），L2 正規化。"""

    name = "hash"

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.model = f"hash-ngram-{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        chars = [c for c in normalize(text) if not c.isspace()]
        for n, weight in ((1, 0.5), (2, 1.0), (3, 0.7)):
            for i in range(len(chars) - n + 1):
                gram = "".join(chars[i : i + n])
                digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                vec[index] += sign * weight
        norm = float(np.linalg.norm(vec))
        return (vec / norm).tolist() if norm > 0 else vec.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """見 `EmbeddingProvider.embed`。"""
        return [self._vector(t) for t in texts]


class OllamaEmbedding:
    """本機 Ollama embedding。"""

    name = "ollama"

    def __init__(self, base_url: str, model: str, dim: int, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        """見 `EmbeddingProvider.embed`。

        Raises:
            RuntimeError: 回傳維度與設定不符。
        """
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        if vectors and len(vectors[0]) != self.dim:
            raise RuntimeError(
                f"embedding 維度 {len(vectors[0])} 與 EMBEDDING_DIM={self.dim} 不符，請改設定並重新嵌入"
            )
        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    """依設定建立 embedding provider。"""
    settings = get_settings()
    if settings.embedding_provider == "ollama":
        return OllamaEmbedding(
            settings.ollama_base_url, settings.embedding_model, settings.embedding_dim, settings.llm_timeout_sec
        )
    if settings.embedding_provider == "hash":
        return HashEmbedding(settings.embedding_dim)
    raise RuntimeError(f"未知的 EMBEDDING_PROVIDER：{settings.embedding_provider}")
