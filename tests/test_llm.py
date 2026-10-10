"""Ortak yapay zekâ katmanı: Gemini şema dönüşümü, yanıt ayrıştırma, sağlayıcı seçimi (API taklit edilir)."""
from __future__ import annotations

import json

import pytest

from agents import llm
from config import Settings
from models import CuratedContent


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_gemini_schema_is_flat_and_strict():
    schema = llm.gemini_schema(CuratedContent)
    nodes = list(walk(schema))
    assert not any("$ref" in n or "$defs" in n or "default" in n for n in nodes)
    item = schema["properties"]["global_developments"]["items"]
    assert item["properties"]["url"]["type"] == ["string", "null"]          # Optional → nullable
    assert set(item["required"]) == set(item["properties"])                  # tüm alanlar zorunlu
    assert item["properties"]["impact"]["enum"] == ["high", "medium", "low"]  # Literal → enum
    assert item["additionalProperties"] is False


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self._p


def gemini_reply(text):
    return FakeResp({"status": "completed", "usage": {}, "steps": [
        {"type": "thought", "signature": "x"},
        {"type": "model_output", "content": [{"type": "text", "text": text}]}]})


@pytest.fixture
def settings():
    s = Settings()
    s.llm_provider, s.gemini_api_key, s.gemini_text_model = "gemini", "test", "gemini-3.8-flash"
    return s


def test_generate_json_parses_and_validates(settings, monkeypatch):
    content = {"executive_summary": ["Özet"], "global_developments": [], "turkey_agenda": [],
               "economic_calendar": [], "banking_agenda": []}
    sent = {}

    def fake_post(url, timeout, json, headers):
        sent.update(json)
        return gemini_reply(__import__("json").dumps(content))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    out = llm.generate_json(settings, "SİSTEM", "veri", CuratedContent)
    assert out.executive_summary == ["Özet"]
    assert sent["model"] == "gemini-3.8-flash" and sent["input"].startswith("SİSTEM")
    assert sent["response_format"]["mime_type"] == "application/json"


def test_generate_json_rejects_invalid_output(settings, monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: gemini_reply('{"executive_summary": 5}'))
    with pytest.raises(llm.LLMError):
        llm.generate_json(settings, "s", "p", CuratedContent)


def test_http_error_raises(settings, monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp({"error": "quota"}, status=429))
    with pytest.raises(llm.LLMError, match="429"):
        llm.generate_text(settings, "s", "p")


def test_provider_selection():
    s = Settings()
    s.llm_provider, s.anthropic_api_key, s.gemini_api_key = "", "", "g"
    assert llm.provider(s) == "gemini" and llm.available(s)
    s.anthropic_api_key = "a"
    assert llm.provider(s) == "anthropic"
    s.llm_provider = "none"
    assert not llm.available(s)


def test_curation_falls_back_when_llm_fails(settings, monkeypatch):
    from agents import data_agent
    from agents.data_agent import RawNews

    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp({"error": "x"}, status=500))
    content = data_agent.curate([RawNews("TCMB rezervleri", "", "TCMB", None, None)], [], settings)
    assert content.turkey_agenda[0].source == "TCMB"                          # kural tabanlı yedek devrede


def test_verify_content_flags_invented_figures_and_links():
    from agents import data_agent
    from agents.data_agent import RawNews
    from models import NewsItem

    news = [RawNews("Motorine 6,40 TL zam", "Zam 10 Ekim'de yürürlüğe girdi", "Foreks", "https://k.test/1", None)]
    content = CuratedContent(
        executive_summary=["Motorine 6,40 TL zam geldi; enflasyon %3,5 artabilir."],
        global_developments=[], economic_calendar=[], banking_agenda=[],
        turkey_agenda=[NewsItem(headline="Zam", summary="6,40 TL", source="Foreks", url="https://uydurma.test/x")])
    unverified = data_agent.verify_content(content, news, [])
    assert "3,5" in unverified and "6,40" not in unverified
    assert content.turkey_agenda[0].url is None                       # kaynakta olmayan link silindi


def test_unverified_not_in_llm_schema():
    assert "_unverified" not in llm.gemini_schema(CuratedContent)["properties"]
