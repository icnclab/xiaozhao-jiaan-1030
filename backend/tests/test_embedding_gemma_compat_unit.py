"""Pure-logic / mock tests for the Gemma embedding-model switch
(config.py + models.py + embedding.py + documents.py/retrieval.py call
sites + the 0007 migration file's static shape). No database connection,
no network call, no Ollama call -- this only checks internal consistency
of code already in the working tree, as prep for a later, explicitly
approved Migration execution.

`_env_file=None` is passed to Settings() throughout so these tests never
read the real .env file (avoids touching real credentials even in memory).
"""
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models import EMBEDDING_DIM
from app.providers.embedding import HashEmbedding, OllamaEmbedding, get_embedding_provider

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_DB_URL = "postgresql+psycopg://placeholder:placeholder@127.0.0.1:1/placeholder"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, database_url=PLACEHOLDER_DB_URL, **overrides)


def test_settings_defaults_match_gemma_decision_and_models_constant():
    settings = _settings()
    assert settings.embedding_model == "embeddinggemma-2:270m"
    assert settings.embedding_dim == 768
    assert settings.embedding_dim == EMBEDDING_DIM
    assert settings.llm_model == "gemma4:e4b"


def test_settings_rejects_non_gemma_llm_model():
    with pytest.raises(ValidationError):
        _settings(llm_model="bge-m3")


def test_settings_rejects_non_gemma_embedding_model():
    with pytest.raises(ValidationError):
        _settings(embedding_model="bge-m3")


def test_settings_rejects_wrong_embedding_dim():
    with pytest.raises(ValidationError):
        _settings(embedding_dim=1024)


def test_get_embedding_provider_raises_if_settings_dim_drifts_from_models_constant(monkeypatch):
    import app.providers.embedding as embedding_module

    monkeypatch.setattr(embedding_module, "get_settings", lambda: _settings())
    monkeypatch.setattr("app.models.EMBEDDING_DIM", 1024)
    with pytest.raises(RuntimeError, match="與資料模型"):
        get_embedding_provider()


def test_get_embedding_provider_builds_ollama_with_settings_batch_and_timeout(monkeypatch):
    import app.providers.embedding as embedding_module

    settings = _settings(embedding_timeout_sec=99.0, embedding_batch_size=4)
    monkeypatch.setattr(embedding_module, "get_settings", lambda: settings)
    provider = get_embedding_provider()
    assert isinstance(provider, OllamaEmbedding)
    assert provider.model == "embeddinggemma-2:270m"
    assert provider.dim == 768
    assert provider.timeout == 99.0
    assert provider.batch_size == 4


def test_hash_embedding_embed_query_and_embed_documents_consistent_with_embed():
    provider = HashEmbedding(dim=768)
    text = "居家服務紀錄要保存多久"
    assert provider.embed_query(text) == provider.embed([text])[0]
    assert provider.embed_documents([text, text]) == provider.embed([text, text])
    assert len(provider.embed_query(text)) == 768


def test_ollama_embedding_uses_task_prefixed_prompts_for_query_vs_documents(monkeypatch):
    provider = OllamaEmbedding(
        base_url="http://127.0.0.1:11434", model="embeddinggemma-2:270m",
        dim=4, timeout=5.0, batch_size=8,
    )
    captured: list[list[str]] = []

    def fake_batch(prompts):
        captured.append(prompts)
        return [[0.1, 0.2, 0.3, 0.4] for _ in prompts]

    monkeypatch.setattr(provider, "_batch", fake_batch)
    provider.embed_query("保存期限")
    provider.embed_documents(["內容A"])
    assert captured[0] == ["task: search result | query: 保存期限"]
    assert captured[1] == ["title: none | text: 內容A"]


def test_migration_0007_chains_after_0006_and_targets_vector_768():
    migration_path = (
        REPO_ROOT / "backend" / "migrations" / "versions" / "0007_embedding_gemma_768.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    assert re.search(r'down_revision\s*=\s*"0006_jiaan1030_emergency"', source)
    assert "vector(768)" in source
    assert "vector(1024)" in source  # present only in downgrade()
    # Deliberately NOT chained to by any committed/draft migration this round,
    # so applying it never silently pulls in unrelated unconfirmed work.
    other_versions = (REPO_ROOT / "backend" / "migrations" / "versions").glob("*.py*")
    chained_after_0007 = [
        p for p in other_versions
        if p.name != "0007_embedding_gemma_768.py"
        and 'down_revision = "0007_embedding_gemma_768"' in p.read_text(encoding="utf-8")
    ]
    assert chained_after_0007 == []
