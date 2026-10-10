"""Boru hattı testleri — dış servis çağırmaz (mock veri + sahte sağlayıcılar)."""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

import main
from agents import data_agent, dispatch_agent, html_agent, video_agent
from agents.data_agent import RawNews
from agents.video_agent import MediaResult, count_words
from config import Settings

RUN_DATE = date(2026, 10, 9)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.output_dir = tmp_path / "output"
    s.subscribers = ["a@example.com", "b@example.com"]
    s.anthropic_api_key = ""   # testlerde LLM çağrısı yok
    s.video_provider = "none"
    return s


@pytest.fixture
def briefing_path(settings: Settings) -> Path:
    return data_agent.run(settings, RUN_DATE, mock=True)


# --- Ajan 1 ---------------------------------------------------------------
def test_tier1_filter_drops_untrusted_and_duplicates():
    items = [
        RawNews("Fed faizi sabit tuttu", "", "Reuters", None, None),
        RawNews("Fed faizi sabit tuttu", "", "Bloomberg", None, None),   # tekrar
        RawNews("Söylenti: X şirketi satılıyor", "", "RandomBlog", None, None),
    ]
    out = data_agent.filter_tier1(items)
    assert [n.source for n in out] == ["Reuters"]


def test_rule_based_curation_splits_turkey_and_global(settings):
    news = [
        RawNews("TCMB rezervleri arttı", "", "TCMB", None, datetime.now(timezone.utc)),
        RawNews("ECB faiz kararı", "Avrupa", "Reuters", None, None),
    ]
    content = data_agent.curate(news, [], settings)
    assert content.turkey_agenda[0].source == "TCMB"
    assert content.global_developments[0].source == "Reuters"
    assert content.executive_summary


def test_live_mode_with_injected_fetchers(settings):
    path = data_agent.run(settings, RUN_DATE, market_fetcher=lambda s: [],
                          news_fetcher=lambda s: [RawNews("BIST rekor", "", "Foreks", None, None)])
    b = data_agent.load_briefing(path)
    assert b.turkey_agenda[0].headline == "BIST rekor"


# --- Ajan 2 ---------------------------------------------------------------
def test_html_render_is_email_safe(briefing_path, settings):
    html = html_agent.render(data_agent.load_briefing(briefing_path), settings,
                             media_box={"speed": "1.25x", "duration": "0:54", "audio_url": "http://localhost:8765/a.mp3"})
    assert "#0B0E14" in html and "#151A23" in html
    assert "#10B981" in html and "#EF4444" in html          # yükseliş + düşüş renkleri
    assert "<!--[if mso]>" in html and "v:roundrect" in html  # Outlook uyumluluğu
    assert "<script" not in html.lower()
    assert "10.842,37" in html                                # TR sayı biçimi


def test_number_formatting():
    assert html_agent.fmt_number(41.9725, 4) == "41,9725"
    assert html_agent.fmt_number(None) == "—"
    assert html_agent.fmt_change(-2.15).startswith("▼")


# --- Ajan 3 ---------------------------------------------------------------
def test_rule_based_script_length(briefing_path):
    script = video_agent.compose_script_rule_based(data_agent.load_briefing(briefing_path))
    assert count_words(script) <= video_agent.MAX_WORDS
    assert script.startswith("Günaydın")


def test_video_agent_never_raises(briefing_path, settings, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("API down")
    monkeypatch.setitem(video_agent.PROVIDERS, "elevenlabs", boom)
    res = video_agent.run(briefing_path, settings, provider="elevenlabs")
    assert res.status == "failed" and res.script_path


# --- Ajan 4 ---------------------------------------------------------------
def test_dispatch_dry_run_writes_eml_with_cta(briefing_path, settings):
    html_agent.run(briefing_path, settings)
    audio = briefing_path.parent / "briefing_audio.mp3"
    audio.write_bytes(b"\x00" * 100)
    settings.media_public_base_url = "http://localhost:8765"
    media = MediaResult(status="ready", kind="audio", file_path=str(audio), audio_path=str(audio), duration=54)
    res = dispatch_agent.run(briefing_path, media, settings, dry_run=True)
    msg = BytesParser(policy=policy.default).parsebytes(Path(res.eml_path).read_bytes())
    assert "Sabah Finans Brifingi" in msg["Subject"]
    assert "a@example.com" in msg["Bcc"]
    html = msg.get_body(("html",)).get_content()
    assert f"http://localhost:8765/{briefing_path.parent.name}/briefing_audio.mp3" in html   # "Dinle" bağlantısı


# --- Orkestrasyon ---------------------------------------------------------
def test_full_mock_pipeline(settings):
    report = main.run_pipeline(settings, RUN_DATE, mock=True, dry_run=True, wait_for_dispatch=False)
    assert report["media"]["status"] == "ready"
    assert report["dispatch"]["with_media"] is True
    assert Path(report["dispatch"]["eml_path"]).exists()


def test_slow_video_does_not_block_newsletter(settings, monkeypatch):
    """Video son teslim saatini kaçırırsa bülten videosuz gitmeli."""
    monkeypatch.setattr(main, "timedelta", lambda seconds: __import__("datetime").timedelta(seconds=1))

    def slow_video(*a, **k):
        time.sleep(5)
        return MediaResult(status="ready", kind="video", url="https://late.test")

    started = time.monotonic()
    report = main.run_pipeline(settings, RUN_DATE, mock=True, dry_run=True, wait_for_dispatch=False,
                               video_runner=slow_video)
    assert time.monotonic() - started < 4
    assert report["media"]["status"] == "timeout"
    assert report["dispatch"]["sent"] == settings.subscribers
    assert report["dispatch"]["with_media"] is False


def test_business_day():
    assert main.is_business_day(date(2026, 10, 9))       # Cuma
    assert not main.is_business_day(date(2026, 10, 10))  # Cumartesi
    assert not main.is_business_day(date(2026, 10, 29))  # Cumhuriyet Bayramı


# --- Ajan 3: Gemini sağlayıcısı ---------------------------------------------
def _fake_wav(seconds: float = 2.5, rate: int = 24000) -> bytes:
    import io
    import math
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                               for i in range(int(seconds * rate))))
    return buf.getvalue()


def _stream_seconds(path: str, stream: str) -> float:
    """Akışı gerçekten çözerek süresini ölçer (konteyner başlığına güvenmez)."""
    import re
    import subprocess

    out = subprocess.run([video_agent.ffmpeg_exe(), "-i", path, "-map", f"0:{stream}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    h, m, s = re.findall(r"time=(\d+):(\d+):([\d.]+)", out)[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def test_gemini_request_shape_and_parsing(settings, monkeypatch):
    import base64

    captured = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"steps": [{"type": "model_output",
                               "content": [{"type": "audio", "data": base64.b64encode(b"RIFFxyz").decode()}]}]}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json)
        return Resp()

    settings.gemini_api_key = "test-key"
    monkeypatch.setattr(video_agent.requests, "post", fake_post)
    assert video_agent.gemini_tts("Günaydın", settings) == b"RIFFxyz"
    assert captured["url"].endswith("/v1beta/interactions")
    assert captured["headers"]["x-goog-api-key"] == "test-key"
    assert captured["body"]["generation_config"]["speech_config"][0]["voice"] == settings.gemini_voice
    assert captured["body"]["response_format"] == {"type": "audio"}


def test_gemini_produces_mp4_at_target_speed(briefing_path, settings, monkeypatch):
    settings.gemini_api_key = "test-key"
    monkeypatch.setattr(video_agent, "gemini_tts", lambda script, s: _fake_wav(20))
    res = video_agent.run(briefing_path, settings, provider="gemini")
    assert res.status == "ready" and res.kind == "video"
    assert res.file_path.endswith(".mp4") and Path(res.file_path).stat().st_size > 0
    assert (briefing_path.parent / "video_card.png").exists()
    assert abs(_stream_seconds(res.file_path, "a") - 20 / 1.25) < 0.3   # 1.25x hız uygulandı
    assert abs(_stream_seconds(res.file_path, "v") - 20 / 1.25) < 1.0   # görüntü sesi aşmıyor


def test_gemini_falls_back_to_audio_when_mux_fails(briefing_path, settings, monkeypatch):
    settings.gemini_api_key = "test-key"
    monkeypatch.setattr(video_agent, "gemini_tts", lambda script, s: _fake_wav(1.0))
    monkeypatch.setattr(video_agent, "mux_video", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    res = video_agent.run(briefing_path, settings, provider="gemini")
    assert res.status == "ready" and res.kind == "audio" and res.file_path.endswith(".mp3")  # 1.25x MP3


def test_gemini_skipped_without_key(briefing_path, settings):
    settings.gemini_api_key = ""
    assert video_agent.run(briefing_path, settings, provider="gemini").status == "skipped"


def test_turkish_feed_dates_and_undated_items():
    import types

    entry = {"published": "1 Eki 2026 14:00:00"}
    dt = data_agent.parse_entry_date(entry)
    assert dt == datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)          # 14:00 TR = 11:00 UTC
    assert data_agent.parse_entry_date({"published": "bilinmiyor"}) is None


def test_monday_lookback_covers_weekend():
    monday = datetime(2026, 10, 12, 4, 30, tzinfo=timezone.utc)              # Pazartesi 07:30 TR
    tuesday = datetime(2026, 10, 13, 4, 30, tzinfo=timezone.utc)
    assert (monday - data_agent.news_cutoff(monday, 18)).total_seconds() == 66 * 3600
    assert (tuesday - data_agent.news_cutoff(tuesday, 18)).total_seconds() == 18 * 3600


def test_rule_based_balances_sources(settings):
    now = datetime.now(timezone.utc)
    news = [RawNews(f"KAP haberi {i}", "", "KAP", None, now) for i in range(5)] + \
           [RawNews(f"TCMB duyurusu {i}", "", "TCMB", None, now) for i in range(5)]
    content = data_agent.curate(news, [], settings)
    sources = [n.source for n in content.turkey_agenda]
    assert sources.count("KAP") <= 2 and sources.count("TCMB") <= 2


def test_bank_news_go_to_banking_section(settings):
    now = datetime.now(timezone.utc)
    news = [RawNews("Eurobond ihracı", "", "QNB", None, now), RawNews("Sendikasyon", "", "Akbank", None, now),
            RawNews("TCMB rezervleri arttı", "", "TCMB", None, now)]
    content = data_agent.curate(news, [], settings)
    assert {n.source for n in content.banking_agenda} == {"QNB", "Akbank"}
    assert all(n.source not in {"QNB", "Akbank"} for n in content.turkey_agenda + content.global_developments)


def test_banking_section_rendered_only_when_present(briefing_path, settings):
    b = data_agent.load_briefing(briefing_path)
    html = html_agent.render(b, settings)
    assert "4 Büyük Banka" in html and "YENİ" in html                    # mock: Yapı Kredi yeni duyuru
    assert "Banka haber sayfasına bugün ulaşılamadı" in html                     # mock: QNB sayfası okunamadı
    b.bank_watch = []
    html = html_agent.render(b, settings)
    assert "4 Büyük Banka" not in html and "Bankacılık Gündemi" in html    # yedek: yapay zekâ seçimi
    b.banking_agenda = []
    assert "Bankacılık Gündemi" not in html_agent.render(b, settings)


def test_email_attaches_media_and_shows_listen_link(briefing_path, settings, tmp_path):
    html_agent.run(briefing_path, settings)
    (tmp_path / "v.mp4").write_bytes(b"\x00" * 1000)
    (tmp_path / "a.mp3").write_bytes(b"\x00" * 800)
    (tmp_path / "t.txt").write_text("Günaydın, sabah brifingine hoş geldiniz.", encoding="utf-8")
    media = MediaResult(status="ready", kind="video", file_path=str(tmp_path / "v.mp4"),
                        audio_path=str(tmp_path / "a.mp3"), script_path=str(tmp_path / "t.txt"), duration=57.3)
    email = dispatch_agent.compose(data_agent.load_briefing(briefing_path), briefing_path.parent / "briefing.html",
                                   media, settings)
    assert sorted(a.filename.rsplit(".", 1)[1] for a in email.attachments) == ["mp3", "mp4"]
    assert "Sesli Brifing" in email.html and "Dinle" in email.html and "0:57" in email.html
    assert f"/{tmp_path.name}/a.mp3" in email.html                                   # bağlantı ses dosyasına
    assert "Günaydın, sabah brifingine" not in email.html                           # spiker metni gösterilmez


def test_same_audio_file_attached_once(briefing_path, settings, tmp_path):
    html_agent.run(briefing_path, settings)
    (tmp_path / "a.mp3").write_bytes(b"\x00" * 800)
    media = MediaResult(status="ready", kind="audio", file_path=str(tmp_path / "a.mp3"), audio_path=str(tmp_path / "a.mp3"))
    email = dispatch_agent.compose(data_agent.load_briefing(briefing_path), briefing_path.parent / "briefing.html",
                                   media, settings)
    assert len(email.attachments) == 1


def test_no_cds_in_markets(briefing_path):
    assert all(m.key != "cds" for m in data_agent.load_briefing(briefing_path).markets)
    assert "cds" not in data_agent.INDICATORS