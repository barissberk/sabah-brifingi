"""Görsel ajan veri aktarımı: pivot, kategori/etiket, akış birleştirme, eski ses koruması, uçtan uca."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

import main
from agents import data_agent, terminal_export
from agents.data_agent import RawNews
from config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.output_dir = tmp_path / "output"
    s.subscribers = ["a@example.com"]
    s.anthropic_api_key = ""
    s.video_provider = "none"
    s.kap_enabled = False
    s.bank_news_enabled = False
    return s


def fake_history(symbol):
    if symbol in ("XULAS.IS",):
        raise ValueError("veri yok")
    return pd.DataFrame({"High": [101.0, 110.0], "Low": [95.0, 100.0], "Close": [100.0, 105.0]},
                        index=pd.to_datetime(["2026-10-08", "2026-10-09"]))


def test_classic_pivot():
    p = terminal_export.compute_pivot(high=110, low=100, close=105)
    assert p["pivot"] == pytest.approx(105)
    assert p["r1"] == pytest.approx(110) and p["s1"] == pytest.approx(100)
    assert p["r2"] == pytest.approx(115) and p["s2"] == pytest.approx(95)


def test_tickers_rates_in_bp_and_missing_source():
    ticks = {t["symbol"]: t for t in terminal_export.fetch_tickers(fake_history)}
    assert ticks["XU100"]["change"] == pytest.approx(5.0) and ticks["XU100"]["change_unit"] == "%"
    assert ticks["US10Y"]["change_unit"] == "bp" and ticks["US10Y"]["change"] == pytest.approx(500.0)
    assert ticks["TR2Y"]["value"] is None and "Lisanslı" in ticks["TR2Y"]["source"]


def test_categorize_and_detect_tickers():
    assert terminal_export.categorize("KAP", "x") == "kap"
    assert terminal_export.categorize("Foreks", "Brent petrol geriledi") == "emtia"
    assert terminal_export.categorize("Foreks", "TCMB faiz kararı") == "makro"
    assert terminal_export.categorize("QNB", "eurobond") == "bist"
    assert terminal_export.detect_tickers("Türk Hava Yolları ve Akbank") == ["AKBNK", "THYAO"] or \
        set(terminal_export.detect_tickers("Türk Hava Yolları ve Akbank")) == {"AKBNK", "THYAO"}


def test_wire_merges_curated_and_raw(settings):
    path = data_agent.run(settings, mock=True)
    b = data_agent.load_briefing(path)
    curated_url = b.turkey_agenda[0].url
    raw = [RawNews("Ham başlık", "ham özet", "TCMB", curated_url, datetime.now(timezone.utc)),
           RawNews("Yeni haber", "özet", "Foreks", "https://x.test/new", datetime.now(timezone.utc))]
    wire = terminal_export.build_wire(b, raw)
    by_url = {w["url"]: w for w in wire}
    assert by_url[curated_url]["headline"] == b.turkey_agenda[0].headline      # bültendeki sürüm tercih edilir
    assert by_url[curated_url]["in_briefing"] is True
    assert "https://x.test/new" in by_url
    assert len({w["id"] for w in wire}) == len(wire)


def test_stale_audio_not_exported(settings, tmp_path):
    path = data_agent.run(settings, mock=True)
    out = path.parent
    (out / "teleprompter.txt").write_text("eski metin", encoding="utf-8")
    old = time.time() - 3600
    os.utime(out / "teleprompter.txt", (old, old))
    assert terminal_export.export_audio(None, out, tmp_path / "data") is None


def test_pipeline_writes_terminal_json(settings, tmp_path, monkeypatch):
    report = main.run_pipeline(settings, mock=True, dry_run=True, wait_for_dispatch=False)
    data = json.loads(Path(report["terminal"]).read_text(encoding="utf-8"))
    assert data["is_demo"] is True
    assert data["analyst_desk"]["is_sample"] is True
    assert data["wire"] and data["pillars"]
    assert report["dispatch"]["sent"]


def test_terminal_failure_does_not_block_newsletter(settings, monkeypatch):
    monkeypatch.setattr(terminal_export, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    report = main.run_pipeline(settings, mock=True, dry_run=True, wait_for_dispatch=False)
    assert report["terminal"] is None and report["dispatch"]["sent"]
