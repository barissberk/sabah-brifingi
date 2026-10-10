"""Ajan 2 — HTML & Visualizer.

Ajan 1'in JSON çıktısını Jinja2 şablonuyla e-posta uyumlu (tablo tabanlı,
inline CSS) koyu temalı bir bültene dönüştürür.

Bağımsız çalıştırma:
    python -m agents.html_agent output/2026-10-09/briefing.json
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import Settings, get_settings
from models import Briefing

log = logging.getLogger("agent2.html")

PALETTE = {
    "bg": "#0B0E14",
    "card": "#151A23",
    "border": "#232A36",
    "text": "#E6E8EC",
    "muted": "#8B93A1",
    "up": "#10B981",
    "down": "#EF4444",
    "accent": "#3B82F6",
}

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
             "Kasım", "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def fmt_number(value: Optional[float], decimals: int = 2) -> str:
    """Türkçe sayı biçimi: 10.234,56"""
    if value is None:
        return "—"
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_change(value: Optional[float]) -> str:
    if value is None:
        return ""
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "■")
    return f"{arrow} %{fmt_number(abs(value), 2)}"


def change_color(value: Optional[float]) -> str:
    if value is None or value == 0:
        return PALETTE["muted"]
    return PALETTE["up"] if value > 0 else PALETTE["down"]


def fmt_date_tr(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {TR_MONTHS[d.month - 1]} {d.year}, {TR_DAYS[d.weekday()]}"


def fmt_date_short(iso: Optional[str]) -> str:
    """'2026-09-28' → '28 Eylül 2026'"""
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {TR_MONTHS[d.month - 1]} {d.year}"


def _env(settings: Settings) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(settings.templates_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(num=fmt_number, chg=fmt_change, chg_color=change_color, date_tr=fmt_date_tr,
                       date_short=fmt_date_short)
    return env


def render(briefing: Briefing, settings: Optional[Settings] = None, video_url: Optional[str] = None,
           video_label: str = "Brifingi 1.25x hızda izleyin / dinleyin",
           media_box: Optional[dict] = None) -> str:
    """Saf fonksiyon: Briefing → HTML string (test edilebilir)."""
    settings = settings or get_settings()
    template = _env(settings).get_template("briefing.html")
    return template.render(b=briefing, c=PALETTE, video_url=video_url, video_label=video_label,
                           media_box=media_box)


def run(briefing_path: Path, settings: Optional[Settings] = None, video_url: Optional[str] = None) -> Path:
    from agents.data_agent import load_briefing

    settings = settings or get_settings()
    briefing = load_briefing(briefing_path)
    html = render(briefing, settings, video_url=video_url)
    out = Path(briefing_path).parent / "briefing.html"
    out.write_text(html, encoding="utf-8")
    log.info("Ajan 2 tamamlandı → %s", out)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ajan 2 — HTML bülten üretimi")
    ap.add_argument("briefing_json", type=Path)
    ap.add_argument("--video-url", default=None)
    args = ap.parse_args()
    print(run(args.briefing_json, video_url=args.video_url))
