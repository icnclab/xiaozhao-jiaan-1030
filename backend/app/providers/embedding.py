
"""Google Gemma Embedding providers，768 dimensions。"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx
import numpy as np

from app.config import get_settings
from app.services.text import normalize


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]: ...

    def embed(
        self, texts: list[str]
    ) -> list[list[float]]: ...


class HashEmbedding:
    """測試用 Hash Embedding，不取代正式語意檢索。"""

    name = "hash"

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.model = f"hash-ngram-{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)

        chars = [
            c for c in normalize(text)
            if not c.isspace()
        ]

        for n, weight in (
            (1, 0.5),
            (2, 1.0),
            (3, 0.7),
        ):
            for i in range(len(chars) - n + 1):
                gram = "".join(chars[i:i + n])

                digest = hashlib.blake2b(
                    gram.encode("utf-8"),
                    digest_size=8,
                ).digest()

                index = (
                    int.from_bytes(
                        digest[:4], "little"
                    ) % self.dim
                )

                sign = (
                    1.0 if digest[4] & 1 else -1.0
                )

                vec[index] += sign * weight

        norm = float(np.linalg.norm(vec))

        if norm > 0:
            return (vec / norm).tolist()

        return vec.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed(
        self, texts: list[str]
    ) -> list[list[float]]:
        return self.embed_documents(texts)


class OllamaEmbedding:
    """本機 Ollama Embedding，逐批驗證維度。"""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        dim: int,
        timeout: float,
        batch_size: int = 8,
    ) -> None:

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.timeout = timeout
        self.batch_size = batch_size

    def _batch(
        self, prompts: list[str]
    ) -> list[list[float]]:

        try:
            response = httpx.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": prompts,
                    "dimensions": self.dim,
                    "truncate": False,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()

            vectors = response.json().get(
                "embeddings"
            )

        except (
            httpx.HTTPError,
            ValueError,
            AttributeError,
        ) as exc:

            raise RuntimeError(
                "本機 Ollama embedding 失敗；"
                "請確認服務已啟動、模型已下載，"
                "且輸入未超過模型上限"
            ) from exc

        if (
            not isinstance(vectors, list)
            or len(vectors) != len(prompts)
        ):
            raise RuntimeError(
                "Ollama 回傳向量筆數不一致"
            )

        valid: list[list[float]] = []

        for i, vector in enumerate(vectors):

            if (
                not isinstance(vector, list)
                or len(vector) != self.dim
            ):
                actual = (
                    len(vector)
                    if isinstance(vector, list)
                    else "非陣列"
                )

                raise RuntimeError(
                    f"第 {i + 1} 筆向量維度不符："
                    f"預期 {self.dim}，實際 {actual}"
                )

            if any(
                not isinstance(x, (int, float))
                or not math.isfinite(x)
                for x in vector
            ):
                raise RuntimeError(
                    "Embedding 含 NaN、Infinity 或非法數值"
                )

            valid.append([
                float(x) for x in vector
            ])

        return valid

    def _encode(
        self, prompts: list[str]
    ) -> list[list[float]]:

        if not prompts:
            return []

        result: list[list[float]] = []

        for start in range(
            0, len(prompts), self.batch_size
        ):
            batch = prompts[
                start:start + self.batch_size
            ]

            result.extend(
                self._batch(batch)
            )

        return result

    def embed_query(
        self, text: str
    ) -> list[float]:

        prompt = (
            f"task: search result | query: {text}"
        )

        return self._encode([prompt])[0]

    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]:

        prompts = [
            f"title: none | text: {text}"
            for text in texts
        ]

        return self._encode(prompts)

    def embed(
        self, texts: list[str]
    ) -> list[list[float]]:

        return self.embed_documents(texts)


def get_embedding_provider() -> EmbeddingProvider:
    """建立提供者，檢查設定和 ORM 維度一致。"""

    from app.models import EMBEDDING_DIM

    settings = get_settings()

    if settings.embedding_dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"設定維度 {settings.embedding_dim} "
            f"與資料模型 {EMBEDDING_DIM} 不符；"
            "請先執行資料庫 Migration"
        )

    if settings.embedding_provider == "ollama":
        return OllamaEmbedding(
            settings.ollama_base_url,
            settings.embedding_model,
            settings.embedding_dim,
            settings.embedding_timeout_sec,
            settings.embedding_batch_size,
        )

    if settings.embedding_provider == "hash":
        return HashEmbedding(
            settings.embedding_dim
        )

    raise RuntimeError(
        "未知的 EMBEDDING_PROVIDER："
        + settings.embedding_provider
    )
