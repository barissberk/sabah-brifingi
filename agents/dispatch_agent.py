"""Ajan 4 — Dispatcher.

Ajan 2'nin HTML bültenini Ajan 3'ün medya çıktısıyla birleştirir ve abonelere
Resend API ya da SMTP üzerinden gönderir. `dry_run` modunda .eml dosyası yazar.

Bağımsız çalıştırma:
    python -m agents.dispatch_agent output/2026-10-09/briefing.json --dry-run
"""
from __future__ import annotations

import argparse
import base64
import logging
import mimetypes
import smtplib
import ssl
import time as _time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import List, Optional

import requests

from agents.html_agent import fmt_date_tr, render
from agents.video_agent import MediaResult
from config import Settings, get_settings
from models import Briefing

log = logging.getLogger("agent4.dispatch")

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime_type: str


@dataclass
class OutgoingEmail:
    subject: str
    html: str
    text: str
    attachments: List[Attachment] = field(default_factory=list)


@dataclass
class DispatchResult:
    provider: str
    sent: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    eml_path: Optional[str] = None
    with_media: bool = False


def _fmt_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def compose(briefing: Briefing, html_path: Path, media: Optional[MediaResult],
            settings: Settings) -> OutgoingEmail:
    """HTML + medya birleştirme.

    Medya hazırsa: video (MP4) ve ses (MP3) ayrı ekler olarak eklenir; bültende "Sesli Brifing" bölümü
    (süre, ek adları, link varsa düğme, spiker metni) gösterilir.
    """
    html = Path(html_path).read_text(encoding="utf-8")
    attachments: List[Attachment] = []
    media_ready = media is not None and media.status == "ready"

    audio_url = None
    if media_ready:
        for path in dict.fromkeys(p for p in (media.file_path, media.audio_path) if p):   # aynı dosya iki kez eklenmez
            p = Path(path)
            if p.exists() and p.stat().st_size <= MAX_ATTACHMENT_BYTES:
                mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                attachments.append(Attachment(f"sabah-brifingi-{briefing.date}{p.suffix}", p.read_bytes(), mime))
            else:
                log.warning("Medya dosyası eklenemedi (yok veya çok büyük): %s", p)
        audio = media.audio_path or (media.file_path if media.kind == "audio" else None)
        if media.audio_url:                                   # bulutta yayımlanmış ses (GitHub Pages)
            audio_url = media.audio_url
        elif audio and settings.media_public_base_url:        # yerel medya sunucusu (Mac)
            audio_url = f"{settings.media_public_base_url.rstrip('/')}/{Path(audio).parent.name}/{Path(audio).name}"
        media_box = {"duration": _fmt_duration(media.duration), "speed": f"{settings.voice_speed:g}x",
                     "audio_url": audio_url, "attached": bool(attachments)}
        html = render(briefing, settings, media_box=media_box)

    subject = f"Sabah Finans Brifingi | {fmt_date_tr(briefing.date)}"
    text_lines = [subject, ""] + [f"- {s}" for s in briefing.executive_summary]
    if audio_url:
        text_lines += ["", f"Sesli brifing (1.25x): {audio_url}"]
    return OutgoingEmail(subject=subject, html=html, text="\n".join(text_lines), attachments=attachments)


def _to_mime(email: OutgoingEmail, settings: Settings, recipients: List[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = email.subject
    msg["From"] = settings.email_from
    msg["To"] = settings.email_from          # alıcılar birbirini görmesin
    msg["Bcc"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(email.text)
    msg.add_alternative(email.html, subtype="html")
    for att in email.attachments:
        maintype, subtype = att.mime_type.split("/", 1)
        msg.add_attachment(att.content, maintype=maintype, subtype=subtype, filename=att.filename)
    return msg


def send_resend(email: OutgoingEmail, settings: Settings, recipients: List[str]) -> DispatchResult:
    result = DispatchResult(provider="resend")
    attachments = [{"filename": a.filename, "content": base64.b64encode(a.content).decode()}
                   for a in email.attachments]
    for rcpt in recipients:  # kişi başı gönderim: gizlilik + tek hatalı adres diğerlerini etkilemez
        payload = {"from": settings.email_from, "to": [rcpt], "subject": email.subject,
                   "html": email.html, "text": email.text}
        if attachments:
            payload["attachments"] = attachments
        for attempt in range(3):
            try:
                r = requests.post("https://api.resend.com/emails", json=payload, timeout=30,
                                  headers={"Authorization": f"Bearer {settings.resend_api_key}"})
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code} {r.text[:200]}")
                r.raise_for_status()
                result.sent.append(rcpt)
                break
            except requests.RequestException as exc:
                log.warning("Resend %s deneme %d başarısız: %s", rcpt, attempt + 1, exc)
                _time.sleep(2 ** attempt)
        else:
            result.failed.append(rcpt)
        _time.sleep(0.6)  # Resend varsayılan hız sınırı ~2 istek/sn
    return result


def send_smtp(email: OutgoingEmail, settings: Settings, recipients: List[str]) -> DispatchResult:
    msg = _to_mime(email, settings, recipients)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=60) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        refused = smtp.send_message(msg, to_addrs=recipients)
    return DispatchResult(provider="smtp", sent=[r for r in recipients if r not in refused], failed=list(refused))


def dispatch(email: OutgoingEmail, settings: Settings, recipients: Optional[List[str]] = None,
             dry_run: bool = False, out_dir: Optional[Path] = None) -> DispatchResult:
    recipients = recipients or settings.subscribers
    if not recipients:
        raise ValueError("Abone listesi boş (SUBSCRIBERS)")

    if dry_run:
        out_dir = out_dir or settings.output_dir
        eml = Path(out_dir) / "briefing.eml"
        eml.write_bytes(bytes(_to_mime(email, settings, recipients)))
        log.info("DRY-RUN: e-posta gönderilmedi, %s yazıldı", eml)
        return DispatchResult(provider="dry-run", sent=list(recipients), eml_path=str(eml),
                              with_media=bool(email.attachments) or "1.25x" in email.text)

    if settings.email_provider == "smtp":
        result = send_smtp(email, settings, recipients)
    else:
        if not settings.resend_api_key:
            raise ValueError("RESEND_API_KEY tanımlı değil")
        result = send_resend(email, settings, recipients)
    result.with_media = bool(email.attachments) or "1.25x" in email.text
    log.info("Ajan 4: %d gönderildi, %d başarısız", len(result.sent), len(result.failed))
    return result


def run(briefing_path: Path, media: Optional[MediaResult] = None, settings: Optional[Settings] = None,
        dry_run: bool = False) -> DispatchResult:
    from agents.data_agent import load_briefing

    settings = settings or get_settings()
    briefing_path = Path(briefing_path)
    briefing = load_briefing(briefing_path)
    html_path = briefing_path.parent / "briefing.html"
    email = compose(briefing, html_path, media, settings)
    # Abonelere giden nihai HTML (medya CTA'sı dahil) arşiv/önizleme için saklanır.
    (briefing_path.parent / "briefing_sent.html").write_text(email.html, encoding="utf-8")
    return dispatch(email, settings, dry_run=dry_run, out_dir=briefing_path.parent)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ajan 4 — e-posta gönderimi")
    ap.add_argument("briefing_json", type=Path)
    ap.add_argument("--video-url", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    m = MediaResult(status="ready", kind="video", url=args.video_url) if args.video_url else None
    print(run(args.briefing_json, media=m, dry_run=args.dry_run))
