"""Merkezi yapılandırma: .env dosyasından ayarları okur."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _parse_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


# Varsayılan Tier-1 haber akışları (.env olmayan bulut ortamında da kullanılır; NEWS_FEEDS ile değiştirilebilir)
DEFAULT_NEWS_FEEDS = ",".join([
    "Bloomberg HT|https://www.bloomberght.com/rss",
    "Foreks|https://www.foreks.com/rss",
    "TCMB|https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Bottom+Menu/Diger/RSS/Basin+Duyurulari",
])


def _parse_feeds() -> List[Tuple[str, str]]:
    feeds: List[Tuple[str, str]] = []
    for chunk in (_env("NEWS_FEEDS") or DEFAULT_NEWS_FEEDS).split(","):
        if "|" in chunk:
            name, url = chunk.split("|", 1)
            feeds.append((name.strip(), url.strip()))
    for name, key in (
        ("Bloomberg", "BLOOMBERG_FEED_URL"),
        ("Reuters", "REUTERS_FEED_URL"),
        ("Foreks", "FOREKS_FEED_URL"),
        ("KAP", "KAP_FEED_URL"),
    ):
        if _env(key):
            feeds.append((name, _env(key)))
    return feeds


@dataclass
class Settings:
    timezone: str = field(default_factory=lambda: _env("TIMEZONE", "Europe/Istanbul"))
    start_time: time = field(default_factory=lambda: _parse_time(_env("PIPELINE_START_TIME", "07:30")))
    dispatch_time: time = field(default_factory=lambda: _parse_time(_env("DISPATCH_TIME", "08:15")))
    video_deadline: time = field(default_factory=lambda: _parse_time(_env("VIDEO_DEADLINE", "08:10")))
    output_dir: Path = field(default_factory=lambda: BASE_DIR / _env("OUTPUT_DIR", "output"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # Ajan 1
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER").lower())
    gemini_text_model: str = field(default_factory=lambda: _env("GEMINI_TEXT_MODEL", "gemini-3.8-flash"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-opus-5-5"))
    news_feeds: List[Tuple[str, str]] = field(default_factory=_parse_feeds)
    news_lookback_hours: int = field(default_factory=lambda: int(_env("NEWS_LOOKBACK_HOURS", "18")))
    bank_mentions_enabled: bool = field(default_factory=lambda: _env("BANK_MENTIONS_ENABLED", "true").lower() == "true")
    bank_news_enabled: bool = field(default_factory=lambda: _env("BANK_NEWS_ENABLED", "true").lower() == "true")
    kap_enabled: bool = field(default_factory=lambda: _env("KAP_ENABLED", "true").lower() == "true")
    kap_max_items: int = field(default_factory=lambda: int(_env("KAP_MAX_ITEMS", "8")))
    kap_watchlist_path: Path = field(default_factory=lambda: BASE_DIR / _env("KAP_WATCHLIST", "kap_watchlist.txt"))
    # Birden fazla saat: Mac gece uyuyorsa akşam kopyası yine alınır ("18:30,23:50")
    kap_snapshot_times: List[time] = field(default_factory=lambda: [
        _parse_time(t.strip()) for t in _env("KAP_SNAPSHOT_TIME", "18:30,23:50").split(",") if t.strip()])

    # Ajan 3
    video_provider: str = field(default_factory=lambda: _env("VIDEO_PROVIDER", "gemini").lower())
    voice_speed: float = field(default_factory=lambda: float(_env("VOICE_SPEED", "1.25")))
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID"))
    elevenlabs_model_id: str = field(default_factory=lambda: _env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_tts_model: str = field(default_factory=lambda: _env("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"))
    gemini_voice: str = field(default_factory=lambda: _env("GEMINI_VOICE", "Kore"))
    gemini_tts_style: str = field(default_factory=lambda: _env(
        "GEMINI_TTS_STYLE",
        "Deneyimli bir kadın ekonomi spikeri sabah bültenini sunuyor; doğal, akıcı ve sıcak bir anlatım, rakamları ve birimleri net ve vurgulu okuyor, cümle aralarında doğal nefes payı bırakıyor"))
    heygen_api_key: str = field(default_factory=lambda: _env("HEYGEN_API_KEY"))
    heygen_avatar_id: str = field(default_factory=lambda: _env("HEYGEN_AVATAR_ID"))
    heygen_voice_id: str = field(default_factory=lambda: _env("HEYGEN_VOICE_ID"))
    did_api_key: str = field(default_factory=lambda: _env("DID_API_KEY"))
    did_source_url: str = field(default_factory=lambda: _env("DID_SOURCE_URL"))
    # Bulut: ses dosyalarının kopyalanacağı yayın klasörü (GitHub Pages çalışma kopyası); boşsa yayımlanmaz
    media_publish_dir: str = field(default_factory=lambda: _env("MEDIA_PUBLISH_DIR"))
    media_retention_days: int = field(default_factory=lambda: int(_env("MEDIA_RETENTION_DAYS", "14")))
    media_server_port: int = field(default_factory=lambda: int(_env("MEDIA_SERVER_PORT", "8765")))
    # E-postadaki "Dinle" bağlantısının temel adresi (varsayılan: bu Mac'teki yerel medya sunucusu)
    media_public_base_url: str = field(default_factory=lambda: _env(
        "MEDIA_PUBLIC_BASE_URL", f"http://localhost:{_env('MEDIA_SERVER_PORT', '8765')}"))

    # Ajan 4
    email_provider: str = field(default_factory=lambda: _env("EMAIL_PROVIDER", "resend").lower())
    email_from: str = field(default_factory=lambda: _env("EMAIL_FROM", "Sabah Brifingi <brifing@example.com>"))
    subscribers: List[str] = field(
        default_factory=lambda: [s.strip() for s in _env("SUBSCRIBERS").split(",") if s.strip()]
    )
    resend_api_key: str = field(default_factory=lambda: _env("RESEND_API_KEY"))
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    smtp_use_tls: bool = field(default_factory=lambda: _env("SMTP_USE_TLS", "true").lower() == "true")

    templates_dir: Path = BASE_DIR / "templates"
    fixtures_dir: Path = BASE_DIR / "fixtures"


def get_settings() -> Settings:
    return Settings()
