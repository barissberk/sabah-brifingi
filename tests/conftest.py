import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest


@pytest.fixture(autouse=True)
def _isolate_terminal_data(tmp_path, monkeypatch):
    """Testler gerçek terminal/public/data dizinine asla yazmasın."""
    from agents import terminal_export

    monkeypatch.setattr(terminal_export, "TERMINAL_DATA_DIR", tmp_path / "terminal-data")


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """Testler gerçek yapay zekâ API'lerini asla çağırmasın (maliyet + belirsizlik)."""
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")


@pytest.fixture(autouse=True)
def _no_live_sources(monkeypatch):
    """Testler banka/KAP sitelerine gerçek istek atmasın; banka sayfa önbelleği testler arasında sızmasın."""
    from agents import bank_news

    monkeypatch.setenv("BANK_NEWS_ENABLED", "false")
    monkeypatch.setenv("KAP_ENABLED", "false")
    bank_news._PAGE_CACHE.clear()
    yield
    bank_news._PAGE_CACHE.clear()
