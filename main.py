"""Orkestratör — 4 Ajanlı Sabah Finans Brifingi.

Akış (hafta içi, Europe/Istanbul):
  07:30  Ajan 1  veri toplama & küratörlük  → briefing.json   (kritik)
         Ajan 2  HTML bülten               → briefing.html   (kritik)
         Ajan 3  script + ses/video        → paralel, VIDEO_DEADLINE'a kadar beklenir (kritik DEĞİL)
         Görsel  AURA TERMINAL verisi      → terminal/public/data/terminal.json (kritik DEĞİL)
  08:15  Ajan 4  gönderim                  → video hazır değilse bülten videosuz gider

Kullanım:
  python main.py --mock --dry-run --no-wait   # sahte veriyle uçtan uca test
  python main.py --now                        # şimdi çalıştır, 08:15'i bekleyip gönder
  python main.py --schedule                   # zamanlayıcı (hafta içi 07:30)
"""
from __future__ import annotations

import argparse
import json
import logging
import secrets
import shutil
import subprocess
import sys
import time as _time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from agents import data_agent, dispatch_agent, html_agent, video_agent
from agents.video_agent import MediaResult
from config import Settings, get_settings

log = logging.getLogger("orchestrator")


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    try:
        import holidays

        return d not in holidays.Turkey(years=d.year)
    except ImportError:
        return True


def _at(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def _retry(fn: Callable, attempts: int = 3, delay: float = 20, name: str = "") -> object:
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            log.error("%s deneme %d/%d başarısız: %s", name, i, attempts, exc)
            if i == attempts:
                raise
            _time.sleep(delay)


def publish_media(media: MediaResult, settings: Settings, run_date: date) -> MediaResult:
    """Sesi yayın klasörüne (GitHub Pages) tahmin edilemeyen bir adla kopyalar, eski dosyaları temizler."""
    if not (settings.media_publish_dir and media.status == "ready" and media.audio_path
            and Path(media.audio_path).exists()):
        return media
    site = Path(settings.media_publish_dir)
    folder = site / "a"
    folder.mkdir(parents=True, exist_ok=True)
    (site / ".nojekyll").touch()
    index = site / "index.html"
    if not index.exists():
        index.write_text("<!doctype html><meta charset=utf-8><title>Sabah Brifingi</title>", encoding="utf-8")
    name = f"{run_date.isoformat()}-{secrets.token_hex(8)}{Path(media.audio_path).suffix}"
    shutil.copy(media.audio_path, folder / name)
    cutoff = run_date - timedelta(days=settings.media_retention_days)
    for old in folder.iterdir():
        try:
            if date.fromisoformat(old.name[:10]) < cutoff:
                old.unlink()
        except ValueError:
            continue
    media.audio_url = f"{settings.media_public_base_url.rstrip('/')}/a/{name}"
    log.info("Ses yayımlandı → %s", media.audio_url)
    return media


def dispatch_prepared(settings: Optional[Settings] = None, run_date: Optional[date] = None, dry_run: bool = False,
                      wait_for_dispatch: bool = True) -> dict:
    """İkinci aşama: `--prepare-only` ile hazırlanan bülteni 08:15'i bekleyip gönderir."""
    settings = settings or get_settings()
    tz = ZoneInfo(settings.timezone)
    run_date = run_date or datetime.now(tz).date()
    out_dir = settings.output_dir / run_date.isoformat()
    briefing_path = out_dir / "briefing.json"
    report = json.loads((out_dir / "run_report.json").read_text(encoding="utf-8"))
    media = MediaResult(**report["media"]) if report.get("media") else None
    wait_s = (_at(run_date, settings.dispatch_time, tz) - datetime.now(tz)).total_seconds()
    if wait_for_dispatch and wait_s > 0:
        log.info("Gönderim için %s bekleniyor (%.0f sn)", settings.dispatch_time.strftime("%H:%M"), wait_s)
        _time.sleep(wait_s)
    result = _retry(lambda: dispatch_agent.run(briefing_path, media, settings, dry_run=dry_run),
                    attempts=3, delay=10, name="Ajan 4")
    report["dispatch"] = asdict(result)
    report["finished_at"] = datetime.now(tz).isoformat(timespec="seconds")
    (out_dir / "run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Gönderim tamamlandı: %d alıcı", len(result.sent))
    return report


def run_pipeline(settings: Optional[Settings] = None, run_date: Optional[date] = None, mock: bool = False,
                 dry_run: bool = False, wait_for_dispatch: bool = True,
                 video_runner: Callable[..., MediaResult] = video_agent.run, prepare_only: bool = False) -> dict:
    """Tüm boru hattını çalıştırır ve bir çalışma raporu döndürür.

    `prepare_only=True`: bülten + medya + yayın hazırlanır, gönderim yapılmaz (bulutta iki aşamalı çalışma).
    """
    settings = settings or get_settings()
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    run_date = run_date or now.date()
    report: dict = {"date": run_date.isoformat(), "started_at": now.isoformat(timespec="seconds"),
                    "mock": mock, "dry_run": dry_run}

    if wait_for_dispatch:
        dispatch_at = _at(run_date, settings.dispatch_time, tz)
        video_deadline = min(_at(run_date, settings.video_deadline, tz), dispatch_at)
    else:  # test/manuel mod: saat beklenmez, videoya kısa bir pencere tanınır
        dispatch_at = now
        # Yapay zekâ metni (~40 sn) + seslendirme (~25 sn) için gerçekçi pay
        video_deadline = now + timedelta(seconds=180 if not mock else 15)

    # --- Ajan 1 (kritik) ---
    briefing_path = _retry(lambda: data_agent.run(settings, run_date, mock=mock),
                           attempts=1 if mock else 3, name="Ajan 1")
    report["briefing_json"] = str(briefing_path)

    # --- Ajan 3'ü paralel başlat (bülteni bloklamamalı) ---
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent3")
    provider = "mock" if mock else None
    video_future = executor.submit(video_runner, briefing_path, settings, video_deadline, provider)

    # --- Ajan 2 (kritik) ---
    html_path = _retry(lambda: html_agent.run(briefing_path, settings), attempts=2, delay=2, name="Ajan 2")
    report["briefing_html"] = str(html_path)

    # --- Ajan 3'ü son teslim saatine kadar bekle ---
    remaining = max(0.0, (video_deadline - datetime.now(tz)).total_seconds())
    try:
        media: MediaResult = video_future.result(timeout=remaining)
    except FutureTimeout:
        media = MediaResult(status="timeout", detail=f"{video_deadline:%H:%M:%S} itibarıyla hazır değil")
        log.warning("Video yetişmedi — bülten videosuz gönderilecek")
    except Exception as exc:  # noqa: BLE001
        media = MediaResult(status="failed", detail=str(exc))
        log.error("Ajan 3 beklenmedik hata — bülten videosuz gönderilecek: %s", exc)
    executor.shutdown(wait=False)
    media = publish_media(media, settings, run_date)
    report["media"] = asdict(media)

    # --- Görsel ajan: AURA TERMINAL verisi (kritik DEĞİL; bülteni asla durdurmaz) ---
    try:
        from agents import terminal_export

        report["terminal"] = str(terminal_export.run(briefing_path, settings, mock=mock))
    except Exception as exc:  # noqa: BLE001
        log.error("Terminal verisi üretilemedi (bülten etkilenmez): %s", exc)
        report["terminal"] = None

    if prepare_only:
        report_path = Path(briefing_path).parent / "run_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Hazırlık tamamlandı (gönderim ayrı aşamada) → %s", report_path)
        return report

    # --- 08:15'e kadar bekle ---
    wait_s = (dispatch_at - datetime.now(tz)).total_seconds()
    if wait_for_dispatch and wait_s > 0:
        log.info("Gönderim için %s bekleniyor (%.0f sn)", dispatch_at.strftime("%H:%M"), wait_s)
        _time.sleep(wait_s)

    # --- Ajan 4 ---
    result = _retry(lambda: dispatch_agent.run(briefing_path, media, settings, dry_run=dry_run),
                    attempts=3, delay=10, name="Ajan 4")
    report["dispatch"] = asdict(result)
    report["finished_at"] = datetime.now(tz).isoformat(timespec="seconds")

    report_path = Path(briefing_path).parent / "run_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Boru hattı tamamlandı → %s", report_path)
    return report


def scheduled_job(settings: Settings) -> None:
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    if not is_business_day(today):
        log.info("%s iş günü değil, atlanıyor", today)
        return
    # macOS: çalışma süresince (07:30 → 08:15) Mac'in boşta uykuya geçmesini engelle
    awake = None
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        awake = subprocess.Popen(["caffeinate", "-i"])
    try:
        run_pipeline(settings)
    except Exception:  # noqa: BLE001 — zamanlayıcı ayakta kalmalı
        log.exception("Günlük boru hattı başarısız")
    finally:
        if awake:
            awake.terminate()


def start_scheduler(settings: Settings) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    from agents.media_server import start_in_background

    start_in_background(settings)          # e-postadaki "Dinle" bağlantısı için (yalnızca bu Mac)
    sched = BlockingScheduler(timezone=settings.timezone)
    sched.add_job(scheduled_job, CronTrigger(day_of_week="mon-fri", hour=settings.start_time.hour,
                                             minute=settings.start_time.minute, timezone=settings.timezone),
                  args=[settings], id="morning_briefing", misfire_grace_time=600, coalesce=True)
    if settings.kap_enabled:
        from agents import kap_source

        def kap_snapshot_job() -> None:
            try:
                kap_source.snapshot(settings)
            except Exception:  # noqa: BLE001
                log.exception("KAP gece kopyası alınamadı")

        # Her gün (hafta sonu dahil): pazartesi sabahı cuma akşamı + hafta sonu bildirimleri de kapsanır
        for t in settings.kap_snapshot_times:
            sched.add_job(kap_snapshot_job, CronTrigger(hour=t.hour, minute=t.minute, timezone=settings.timezone),
                          id=f"kap_snapshot_{t:%H%M}", misfire_grace_time=3600, coalesce=True)
    log.info("Zamanlayıcı aktif: hafta içi %s (%s)", settings.start_time.strftime("%H:%M"), settings.timezone)
    sched.start()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="4 Ajanlı Sabah Finans Brifingi")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--schedule", action="store_true", help="Hafta içi 07:30 zamanlayıcısını başlat")
    mode.add_argument("--now", action="store_true", help="Boru hattını hemen çalıştır")
    ap.add_argument("--mock", action="store_true", help="Sahte veri + sahte video sağlayıcı")
    ap.add_argument("--dry-run", action="store_true", help="E-posta göndermek yerine .eml dosyası yaz")
    ap.add_argument("--send", action="store_true", help="--mock ile birlikte gerçekten e-posta gönder")
    ap.add_argument("--prepare-only", action="store_true", help="Bülten + medya hazırla, gönderme (bulut 1. aşama)")
    ap.add_argument("--dispatch-only", action="store_true", help="Hazırlanan bülteni gönder (bulut 2. aşama)")
    ap.add_argument("--if-business-day", action="store_true", help="İş günü değilse hiçbir şey yapmadan çık")
    ap.add_argument("--no-wait", action="store_true", help="08:15'i bekleme, hemen gönder")
    ap.add_argument("--date", type=date.fromisoformat, default=None, help="Çalışma tarihi (YYYY-MM-DD)")
    args = ap.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)-16s %(levelname)-7s %(message)s")

    if args.schedule:
        start_scheduler(settings)
        return 0

    if args.if_business_day and not is_business_day(datetime.now(ZoneInfo(settings.timezone)).date()):
        log.info("İş günü değil (hafta sonu/resmi tatil) — çalışma atlandı")
        return 0
    dry_run = args.dry_run or (args.mock and not args.send)  # mock varsayılan olarak asla e-posta göndermez
    if args.dispatch_only:
        report = dispatch_prepared(settings, run_date=args.date, dry_run=dry_run, wait_for_dispatch=not args.no_wait)
        return 0 if not report["dispatch"]["failed"] else 1
    if args.mock and not settings.subscribers:
        settings.subscribers = ["test@example.com"]
    report = run_pipeline(settings, run_date=args.date, mock=args.mock, dry_run=dry_run,
                          wait_for_dispatch=not args.no_wait, prepare_only=args.prepare_only)
    if args.prepare_only:
        print(json.dumps({"briefing_html": report.get("briefing_html"), "media": report.get("media")},
                         ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({k: report[k] for k in ("briefing_html", "media", "dispatch")}, ensure_ascii=False, indent=2))
    return 0 if not report["dispatch"]["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
