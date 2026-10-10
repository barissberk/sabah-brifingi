"""Ortak yapay zekâ katmanı: Gemini (Google AI Studio) veya Claude (Anthropic).

Ajan 1 (küratörlük) ve Ajan 3 (konuşma metni) sağlayıcıdan bağımsız olarak bu iki fonksiyonu kullanır:
  - generate_json(system, prompt, Model) → doğrulanmış pydantic nesnesi
  - generate_text(system, prompt)        → düz metin

Sağlayıcı `.env` içindeki LLM_PROVIDER ile seçilir (gemini | anthropic | none). Boşsa tanımlı anahtara
göre otomatik seçilir: önce Anthropic, sonra Gemini; ikisi de yoksa "none" (kural tabanlı yedek).
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, Optional, Type, TypeVar

import requests
from pydantic import BaseModel

from config import Settings

log = logging.getLogger("llm")

GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def provider(settings: Settings) -> str:
    chosen = (settings.llm_provider or "").lower()
    if chosen in ("gemini", "anthropic", "none"):
        return chosen
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.gemini_api_key:
        return "gemini"
    return "none"


def available(settings: Settings) -> bool:
    p = provider(settings)
    return (p == "gemini" and bool(settings.gemini_api_key)) or (p == "anthropic" and bool(settings.anthropic_api_key))


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
def gemini_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Pydantic şemasını Gemini'nin desteklediği JSON Schema alt kümesine çevirir.

    $ref/$defs satır içine alınır; Optional (anyOf X|null) → {"type": [X, "null"]};
    default/title gibi desteklenmeyen veya gereksiz anahtarlar atılır; tüm alanlar `required` olur
    (eksik alan yerine null döndürülmesi istenir, böylece çıktı her zaman doğrulanabilir).
    """
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
        if "anyOf" in node:
            variants = [walk(v) for v in node["anyOf"]]
            non_null = [v for v in variants if v.get("type") != "null"]
            if len(non_null) == 1 and len(variants) == 2:
                out = dict(non_null[0])
                out["type"] = [out.get("type", "string"), "null"]
                if "description" in node:
                    out["description"] = node["description"]
                return out
            return {"anyOf": variants}
        out = {}
        for k, v in node.items():
            if k in ("$defs", "default", "title"):
                continue
            out[k] = walk(v)
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"].keys())
            out["additionalProperties"] = False
        return out

    return walk(raw)


def _gemini_call(settings: Settings, text: str, response_format: Optional[dict] = None, timeout: int = 180) -> str:
    body: Dict[str, Any] = {"model": settings.gemini_text_model, "input": text}
    if response_format:
        body["response_format"] = response_format
    resp = requests.post(GEMINI_INTERACTIONS_URL, timeout=timeout, json=body,
                         headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"})
    if resp.status_code >= 400:
        raise LLMError(f"Gemini {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    texts = [c.get("text", "") for step in data.get("steps", []) if step.get("type") == "model_output"
             for c in step.get("content", []) or [] if c.get("type") == "text"]
    if not texts:
        raise LLMError(f"Gemini yanıtında metin yok (status={data.get('status')})")
    usage = data.get("usage", {})
    log.info("Gemini %s: girdi %s, çıktı %s, düşünme %s token", settings.gemini_text_model,
             usage.get("total_input_tokens"), usage.get("total_output_tokens"), usage.get("total_thought_tokens"))
    return "".join(texts).strip()


def _with_system(system: str, prompt: str) -> str:
    return f"{system.strip()}\n\n---\n\n{prompt}"


# ---------------------------------------------------------------------------
# Claude (Anthropic)
# ---------------------------------------------------------------------------
def _anthropic_json(settings: Settings, system: str, prompt: str, model: Type[T]) -> T:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.parse(
        model=settings.anthropic_model, max_tokens=16000, system=system,
        messages=[{"role": "user", "content": prompt}], output_format=model,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise LLMError(f"Claude yapılandırılmış çıktı üretmedi (stop_reason={response.stop_reason})")
    return response.parsed_output


def _anthropic_text(settings: Settings, system: str, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(model=settings.anthropic_model, max_tokens=4000, system=system,
                                  messages=[{"role": "user", "content": prompt}])
    if resp.stop_reason == "refusal":
        raise LLMError("Claude isteği reddetti")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# Ortak arayüz
# ---------------------------------------------------------------------------
def generate_json(settings: Settings, system: str, prompt: str, model: Type[T]) -> T:
    p = provider(settings)
    if p == "anthropic":
        return _anthropic_json(settings, system, prompt, model)
    if p == "gemini":
        raw = _gemini_call(settings, _with_system(system, prompt), {
            "type": "text", "mime_type": "application/json", "schema": gemini_schema(model)})
        try:
            return model.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError(f"Gemini çıktısı şemaya uymadı: {exc}") from exc
    raise LLMError("Yapay zekâ sağlayıcısı tanımlı değil (LLM_PROVIDER / API anahtarı)")


def generate_text(settings: Settings, system: str, prompt: str) -> str:
    p = provider(settings)
    if p == "anthropic":
        return _anthropic_text(settings, system, prompt)
    if p == "gemini":
        return _gemini_call(settings, _with_system(system, prompt))
    raise LLMError("Yapay zekâ sağlayıcısı tanımlı değil (LLM_PROVIDER / API anahtarı)")
