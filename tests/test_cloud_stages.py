"""Bulut (GitHub Actions) iki aşamalı çalışma: hazırla → yayımla → gönder."""
from __future__ import annotations

import re
from datetime import date
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

import main
from config import Settings

RUN_DATE = date(2026, 10, 9)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.output_dir = tmp_path / "output"
    s.subscribers = ["a@example.com"]
    s.media_publish_dir = str(tmp_path / "site")
    s.media_public_base_url = "https://kullanici.github.io/sabah-brifingi"
    return s


def test_prepare_then_dispatch_with_published_audio(settings, tmp_path):
    old = tmp_path / "site" / "a" / "2026-09-01-eski.mp3"                # saklama süresini aşmış
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")

    report = main.run_pipeline(settings, RUN_DATE, mock=True, dry_run=True, wait_for_dispatch=False,
                               prepare_only=True)
    assert "dispatch" not in report                                       # 1. aşama göndermez
    url = report["media"]["audio_url"]
    assert re.fullmatch(r"https://kullanici\.github\.io/sabah-brifingi/a/2026-10-09-[0-9a-f]{16}\.mp3", url)
    published = tmp_path / "site" / "a" / url.rsplit("/", 1)[1]
    assert published.exists() and not old.exists()                       # yeni yayımlandı, eski silindi
    assert (tmp_path / "site" / ".nojekyll").exists()

    report = main.dispatch_prepared(settings, RUN_DATE, dry_run=True, wait_for_dispatch=False)
    msg = BytesParser(policy=policy.default).parsebytes(Path(report["dispatch"]["eml_path"]).read_bytes())
    assert url in msg.get_body(("html",)).get_content()                   # "Dinle" → GitHub Pages


def test_no_publish_dir_means_no_public_url(settings):
    settings.media_publish_dir = ""
    report = main.run_pipeline(settings, RUN_DATE, mock=True, dry_run=True, wait_for_dispatch=False,
                               prepare_only=True)
    assert report["media"]["audio_url"] is None


def test_business_day_gate(monkeypatch, capsys):
    class FakeDT(main.datetime):
        @classmethod
        def now(cls, tz=None):
            return main.datetime(2026, 10, 10, 7, 15, tzinfo=tz)          # cumartesi
    monkeypatch.setattr(main, "datetime", FakeDT)
    monkeypatch.setattr(main, "run_pipeline", lambda *a, **k: pytest.fail("hafta sonu çalışmamalı"))
    assert main.main(["--now", "--if-business-day"]) == 0
