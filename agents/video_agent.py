"""Ajan 3 — 1.25x Video Producer.

JSON özetinden 110-120 kelimelik teleprompter scripti yazar ve seçilen sağlayıcı
ile ses (ElevenLabs), bülten kartlı video (Gemini) veya avatar videosu
(HeyGen / D-ID) üretir.

Bağımsız çalıştırma:
    python -m agents.video_agent output/2026-10-09/briefing.json --provider none
"""
from __future__ import annotations

import argparse
import base64
import logging
import re
import shutil
import subprocess
import time as _time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import requests

from config import Settings, get_settings
from agents.speech_text import normalize_for_speech, spoken_market_sentence
from models import Briefing

log = logging.getLogger("agent3.video")

MIN_WORDS, MAX_WORDS = 110, 120
ELEVENLABS_MAX_SPEED = 1.2  # API sınırı; kalan fark ffmpeg atempo ile kapatılır
POLL_INTERVAL = 10


@dataclass
class MediaResult:
    status: str                      # ready | skipped | failed | timeout
    kind: Optional[str] = None       # audio | video
    url: Optional[str] = None        # abonelere verilecek link
    file_path: Optional[str] = None  # yerel dosya (ek olarak gönderilebilir)
    script_path: Optional[str] = None
    detail: str = ""
    audio_path: Optional[str] = None  # 1.25x ses dosyası (MP3) — videoya ek olarak e-postaya eklenir
    duration: Optional[float] = None  # oynatma süresi (sn, hedef hızda)
    audio_url: Optional[str] = None   # yayımlanmış sesin adresi (ör. GitHub Pages) — "Dinle" bağlantısı


class DeadlineExceeded(Exception):
    pass


# ---------------------------------------------------------------------------
# Teleprompter scripti
# ---------------------------------------------------------------------------
def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'’%.,/-]+\b", text, flags=re.UNICODE))


def compose_script_rule_based(b: Briefing) -> str:
    """LLM olmadan, öncelik sırasına göre cümle ekleyerek 110-120 kelimeye yaklaşır."""
    opening = "Günaydın, sabah finans brifingine hoş geldiniz."
    closing = "Detaylar e-postanızda. Verimli bir gün dileriz."
    candidates: List[str] = [spoken_market_sentence(b.markets)]
    candidates += b.executive_summary
    candidates += [f"{n.headline}." if not n.headline.endswith(".") else n.headline
                   for n in b.turkey_agenda[:2] + b.global_developments[:2]]
    high = [e for e in b.economic_calendar if e.importance == "high"]
    if high:
        candidates.append("Bugün takipte: " + ", ".join(f"saat {e.time}'da {e.event}" for e in high[:3]) + ".")

    body: List[str] = []
    budget = MAX_WORDS - count_words(opening) - count_words(closing)
    for s in filter(None, candidates):
        if count_words(" ".join(body + [s])) <= budget:
            body.append(s)
    script = " ".join([opening] + body + [closing])
    if count_words(script) < MIN_WORDS:
        log.warning("Rule-based script %d kelimede kaldı (hedef %d-%d)", count_words(script), MIN_WORDS, MAX_WORDS)
    return script


SCRIPT_SYSTEM = f"""Sen bir finans kanalının sabah spikeri için teleprompter metni yazıyorsun.
- Tam olarak {MIN_WORDS}-{MAX_WORDS} kelime. Metin 1.25x hızda seslendirilecek: kısa, ritmik, net cümleler kur.
- Her değeri MUTLAKA birimiyle yaz: endeks "puan", kur "lira ... kuruş", emtia "dolar", CDS "baz puan", değişim "yüzde".
  Örnek: "ons altın yüzde 0,54 yükselişle 3.982 dolar", "dolar/TL 41 lira 97 kuruş", "BIST 100 endeksi 10.842 puan".
- Seslendirmede net anlaşılsın diye değerleri yuvarla: endeks ve altın tam sayı, kur ve petrol iki ondalık.
- "5Y", "bps", "$" gibi sembol ve kısaltmalar yerine açık ifade kullan ("beş yıllık", "baz puan", "dolar").
- Selamlama ile başla, en önemli 3-4 gelişme ve piyasa göstergeleri, günün kritik takvimi, kısa kapanış.
- Sadece verilen bilgileri kullan; başlık, sahne yönergesi veya madde işareti koyma. Yalnızca okunacak metni döndür."""


def compose_script_with_llm(b: Briefing, settings: Settings, attempts: int = 3) -> str:
    """Yapay zekâ ile konuşma metni; kelime sınırı tutmazsa geri bildirimle yeniden yazdırılır."""
    from agents import llm

    data = "Bülten verisi:\n" + b.model_dump_json(
        include={"markets", "executive_summary", "turkey_agenda", "global_developments", "banking_agenda",
                 "economic_calendar"})
    prompt, script = data, ""
    for _ in range(attempts):
        script = llm.generate_text(settings, SCRIPT_SYSTEM, prompt)
        n = count_words(script)
        if MIN_WORDS <= n <= MAX_WORDS:
            _warn_unverified(script, data, b)
            return script
        prompt = (f"{data}\n\nÖnceki taslak {n} kelimeydi:\n{script}\n\n"
                  f"Anlamı koruyarak tam {MIN_WORDS}-{MAX_WORDS} kelimeye getir. Yalnızca yeni metni döndür.")
    log.warning("Konuşma metni %d kelimede kaldı; yine de kullanılıyor", count_words(script))
    return script


def _warn_unverified(script: str, source_data: str, b: Optional[Briefing] = None) -> None:
    """Konuşma metnindeki rakamlar bülten verisinde geçmiyorsa uyarı (uydurma koruması).

    Metin değerleri yuvarlayabildiği için (12.265,98 → 12.266) yalnızca kayda geçirilir, metin değiştirilmez.
    """
    from agents.data_agent import FIGURE_RE, fmt_tr

    src = source_data.lower()
    for m in (b.markets if b else []):                 # yuvarlanmış Türkçe biçimler (0,4288 → 0,43; 12.265,98 → 12.266)
        if m.value is not None:
            src += " " + " ".join(fmt_tr(m.value, d) for d in range(0, 5))
        if m.change_pct is not None:
            src += " " + " ".join(fmt_tr(abs(m.change_pct), d) for d in (1, 2))
    loose = re.sub(r"[.,]", "", src)
    unknown = [f for f in FIGURE_RE.findall(script.lower()) if f not in src and re.sub(r"[.,]", "", f) not in loose]
    if unknown:
        log.warning("Konuşma metninde bülten verisinde geçmeyen rakam (yuvarlama olabilir): %s", ", ".join(unknown))


def build_script(b: Briefing, settings: Settings) -> str:
    from agents import llm

    if llm.available(settings):
        try:
            return compose_script_with_llm(b, settings)
        except Exception as exc:  # noqa: BLE001
            log.error("Yapay zekâ konuşma metni (%s) başarısız, kural tabanlı yedeğe geçiliyor: %s",
                      llm.provider(settings), exc)
    return compose_script_rule_based(b)


# ---------------------------------------------------------------------------
# Sağlayıcılar
# ---------------------------------------------------------------------------
def _check_deadline(deadline: Optional[datetime]) -> None:
    if deadline and datetime.now(deadline.tzinfo) >= deadline:
        raise DeadlineExceeded(f"Video son teslim saati ({deadline:%H:%M}) aşıldı")


def ffmpeg_exe() -> Optional[str]:
    """Sistem ffmpeg'i, yoksa imageio-ffmpeg ile gelen gömülü ikili."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def _adjust_tempo(path: Path, factor: float) -> Path:
    """Sesi ffmpeg atempo ile hedef hıza getirir (ElevenLabs 1.2 sınırı vb.)."""
    if abs(factor - 1.0) < 0.01:
        return path
    exe = ffmpeg_exe()
    if not exe:
        log.warning("ffmpeg yok; ses tempo düzeltmesi (%.2fx) uygulanamadı", factor)
        return path
    out = path.with_name(path.stem + "_final" + path.suffix)
    subprocess.run([exe, "-y", "-loglevel", "error", "-i", str(path), "-filter:a", f"atempo={factor:.4f}",
                    str(out)], check=True, timeout=60)
    return out


def produce_elevenlabs(script: str, settings: Settings, out_dir: Path,
                       deadline: Optional[datetime] = None) -> MediaResult:
    if not (settings.elevenlabs_api_key and settings.elevenlabs_voice_id):
        return MediaResult(status="skipped", detail="ElevenLabs anahtarı/ses ID'si tanımlı değil")
    _check_deadline(deadline)
    api_speed = min(settings.voice_speed, ELEVENLABS_MAX_SPEED)
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"},
        json={
            "text": script,
            "model_id": settings.elevenlabs_model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": api_speed},
        },
        timeout=120,
    )
    resp.raise_for_status()
    raw = out_dir / "briefing_audio.mp3"
    raw.write_bytes(resp.content)
    final = _adjust_tempo(raw, settings.voice_speed / api_speed)
    url = f"{settings.media_public_base_url.rstrip('/')}/{out_dir.name}/{final.name}" \
        if settings.media_public_base_url else None
    return MediaResult(status="ready", kind="audio", file_path=str(final), url=url, audio_path=str(final))


def _poll(fetch: Callable[[], Optional[str]], deadline: Optional[datetime], max_wait: int = 1800) -> str:
    """fetch() hazırsa URL, değilse None döndürür; deadline'a kadar bekler."""
    started = _time.monotonic()
    while _time.monotonic() - started < max_wait:
        _check_deadline(deadline)
        url = fetch()
        if url:
            return url
        _time.sleep(POLL_INTERVAL)
    raise DeadlineExceeded("Sağlayıcı zaman aşımı")


def produce_heygen(script: str, settings: Settings, out_dir: Path,
                   deadline: Optional[datetime] = None) -> MediaResult:
    if not (settings.heygen_api_key and settings.heygen_avatar_id and settings.heygen_voice_id):
        return MediaResult(status="skipped", detail="HeyGen anahtarı/avatar/ses tanımlı değil")
    headers = {"X-Api-Key": settings.heygen_api_key, "Content-Type": "application/json"}
    resp = requests.post("https://api.heygen.com/v2/video/generate", headers=headers, timeout=60, json={
        "video_inputs": [{
            "character": {"type": "avatar", "avatar_id": settings.heygen_avatar_id, "avatar_style": "normal"},
            "voice": {"type": "text", "input_text": script, "voice_id": settings.heygen_voice_id,
                      "speed": settings.voice_speed},
            "background": {"type": "color", "value": "#0B0E14"},
        }],
        "dimension": {"width": 1280, "height": 720},
        "title": f"Sabah Brifingi {out_dir.name}",
    })
    resp.raise_for_status()
    video_id = resp.json()["data"]["video_id"]
    log.info("HeyGen video kuyruğa alındı: %s", video_id)

    def fetch() -> Optional[str]:
        r = requests.get("https://api.heygen.com/v1/video_status.get", params={"video_id": video_id},
                         headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()["data"]
        if data.get("status") == "failed":
            raise RuntimeError(f"HeyGen hata: {data.get('error')}")
        return data.get("video_url") if data.get("status") == "completed" else None

    return MediaResult(status="ready", kind="video", url=_poll(fetch, deadline), detail=f"heygen:{video_id}")


def produce_did(script: str, settings: Settings, out_dir: Path,
                deadline: Optional[datetime] = None) -> MediaResult:
    if not (settings.did_api_key and settings.did_source_url):
        return MediaResult(status="skipped", detail="D-ID anahtarı/kaynak görsel tanımlı değil")
    # D-ID panelindeki anahtar Basic auth değeri olarak doğrudan kullanılır.
    headers = {"Authorization": f"Basic {settings.did_api_key}", "Content-Type": "application/json"}
    rate = f"{int(settings.voice_speed * 100)}%"
    ssml = f'<speak><prosody rate="{rate}">{script}</prosody></speak>'
    resp = requests.post("https://api.d-id.com/talks", headers=headers, timeout=60, json={
        "source_url": settings.did_source_url,
        "script": {"type": "text", "input": ssml, "ssml": True,
                   "provider": {"type": "microsoft", "voice_id": "tr-TR-AhmetNeural"}},
    })
    resp.raise_for_status()
    talk_id = resp.json()["id"]
    log.info("D-ID talk kuyruğa alındı: %s", talk_id)

    def fetch() -> Optional[str]:
        r = requests.get(f"https://api.d-id.com/talks/{talk_id}", headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") in ("error", "rejected"):
            raise RuntimeError(f"D-ID hata: {data.get('error')}")
        return data.get("result_url") if data.get("status") == "done" else None

    return MediaResult(status="ready", kind="video", url=_poll(fetch, deadline), detail=f"did:{talk_id}")


# --- Gemini (Google AI Studio): TTS + bülten kartı → MP4 ---------------------
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
CARD_W, CARD_H = 1280, 720
_FONT_CANDIDATES = {
    "regular": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "C:/Windows/Fonts/arial.ttf"],
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
}


def gemini_tts(script: str, settings: Settings) -> bytes:
    """Gemini Interactions API ile Türkçe seslendirme; 24 kHz mono 16-bit WAV döndürür."""
    resp = requests.post(
        GEMINI_INTERACTIONS_URL,
        headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
        json={
            "model": settings.gemini_tts_model,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": script,
                    "annotations": [{"type": "speech_metadata", "style": settings.gemini_tts_style}],
                }],
            }],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": settings.gemini_voice}]},
        },
        timeout=180,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini TTS {resp.status_code}: {resp.text[:300]}")
    audio = [c for step in resp.json().get("steps", []) if step.get("type") == "model_output"
             for c in step.get("content", []) if c.get("type") == "audio"]
    if not audio:
        raise RuntimeError("Gemini yanıtında ses bloğu yok")
    return base64.b64decode(audio[-1]["data"])


def _font(kind: str, size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _wrap(draw, text: str, font, max_w: int, max_lines: int) -> List[str]:
    """Kelime bazlı satır kırma; sığmayan son satır '…' ile biter."""
    lines: List[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    else:
        lines.append(current)
        return lines
    last = lines[-1]
    while draw.textlength(last + "…", font=font) > max_w:
        last = last[:-1]
    lines[-1] = last.rstrip() + "…"
    return lines


def render_video_card(b: Briefing, path: Path) -> Path:
    """Videonun görsel katmanı: koyu tema piyasa kartları + öne çıkan başlıklar (1280x720 PNG)."""
    from PIL import Image, ImageDraw

    from agents.html_agent import PALETTE as C, change_color, fmt_change, fmt_date_tr, fmt_number

    img = Image.new("RGB", (CARD_W, CARD_H), C["bg"])
    d = ImageDraw.Draw(img)
    pad = 64
    d.text((pad, 48), "SABAH FİNANS BRİFİNGİ", font=_font("bold", 22), fill=C["accent"])
    d.text((CARD_W - pad, 48), fmt_date_tr(b.date), font=_font("regular", 22), fill=C["muted"], anchor="ra")
    d.text((pad, 86), "Piyasalar güne nasıl başlıyor?", font=_font("bold", 44), fill=C["text"])
    d.rectangle((pad, 150, pad + 64, 154), fill=C["accent"])

    n = max(len(b.markets), 1)
    gap = 16
    tile_w = (CARD_W - 2 * pad - gap * (n - 1)) // n
    top, tile_h = 190, 150
    for i, m in enumerate(b.markets):
        x = pad + i * (tile_w + gap)
        d.rounded_rectangle((x, top, x + tile_w, top + tile_h), radius=14, fill=C["card"], outline=C["border"])
        d.text((x + 20, top + 20), m.label.upper(), font=_font("regular", 17), fill=C["muted"])
        value = ("$" if m.unit == "$" else "") + fmt_number(m.value, m.decimals) + \
            (f" {m.unit}" if m.unit and m.unit != "$" else "")
        d.text((x + 20, top + 52), value, font=_font("bold", 32), fill=C["text"])
        d.text((x + 20, top + 104), fmt_change(m.change_pct), font=_font("bold", 22),
               fill=change_color(m.change_pct))

    y = top + tile_h + 44
    d.text((pad, y), "ÖNE ÇIKANLAR", font=_font("bold", 20), fill=C["muted"])
    y += 40
    body = _font("regular", 24)
    max_w = CARD_W - 2 * pad - 30
    for item in b.executive_summary[:3]:
        lines = _wrap(d, item, body, max_w, max_lines=2)
        d.rectangle((pad, y + 9, pad + 10, y + 19), fill=C["accent"])
        for line in lines:
            d.text((pad + 30, y), line, font=body, fill=C["text"])
            y += 32
        y += 14

    img.save(path)
    return path


def _wav_seconds(path: Path) -> float:
    import wave

    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def export_mp3(wav: Path, out: Path, tempo: float) -> Optional[Path]:
    """Doğal hızdaki WAV → hedef hızda (1.25x) e-posta dostu MP3. Başarısızsa None."""
    exe = ffmpeg_exe()
    if not exe:
        return None
    cmd = [exe, "-y", "-loglevel", "error", "-i", str(wav)]
    if abs(tempo - 1.0) >= 0.01:
        cmd += ["-filter:a", f"atempo={tempo:.4f}"]
    cmd += ["-codec:a", "libmp3lame", "-b:a", "96k", "-ac", "1", str(out)]
    try:
        subprocess.run(cmd, check=True, timeout=120)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("MP3 üretilemedi: %s", exc)
        return None


def mux_video(card: Path, audio: Path, out: Path, tempo: float) -> Path:
    """Durağan kart + ses → e-posta dostu küçük MP4 (H.264/AAC), sesi hedef hıza getirerek."""
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg bulunamadı (imageio-ffmpeg kurulu değil)")
    cmd = [exe, "-y", "-loglevel", "error", "-loop", "1", "-framerate", "2", "-i", str(card), "-i", str(audio)]
    if abs(tempo - 1.0) >= 0.01:
        cmd += ["-filter:a", f"atempo={tempo:.4f}"]
    # Döngüdeki tek karede -shortest sesi aşabiliyor; WAV ise süre kesin olarak verilir.
    if audio.suffix.lower() == ".wav":
        cmd += ["-t", f"{_wav_seconds(audio) / tempo:.3f}"]
    cmd += ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "2",
            "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, timeout=180)
    return out


def produce_gemini(script: str, settings: Settings, out_dir: Path,
                   deadline: Optional[datetime] = None) -> MediaResult:
    """Gemini TTS (doğal tempo) → atempo ile 1.25x → bülten kartıyla MP4.

    Gemini'de sayısal hız parametresi olmadığından ses doğal spiker temposunda üretilir ve
    hız ffmpeg ile deterministik olarak VOICE_SPEED'e getirilir. ffmpeg yoksa ham WAV döner.
    """
    from agents.data_agent import load_briefing

    if not settings.gemini_api_key:
        return MediaResult(status="skipped", detail="GEMINI_API_KEY tanımlı değil")
    _check_deadline(deadline)
    wav = out_dir / "briefing_audio.wav"
    wav.write_bytes(gemini_tts(script, settings))
    _check_deadline(deadline)

    public = (lambda name: f"{settings.media_public_base_url.rstrip('/')}/{out_dir.name}/{name}") \
        if settings.media_public_base_url else (lambda name: None)
    duration = _wav_seconds(wav) / settings.voice_speed
    mp3 = export_mp3(wav, out_dir / "briefing_audio.mp3", settings.voice_speed)
    audio_path = str(mp3) if mp3 else None
    try:
        card = render_video_card(load_briefing(out_dir / "briefing.json"), out_dir / "video_card.png")
        mp4 = mux_video(card, wav, out_dir / "briefing_video.mp4", settings.voice_speed)
        return MediaResult(status="ready", kind="video", file_path=str(mp4), url=public(mp4.name),
                           detail=f"gemini:{settings.gemini_tts_model}", audio_path=audio_path,
                           duration=duration)
    except Exception as exc:  # noqa: BLE001 — video olmasa da ses kullanılabilir
        log.warning("Video birleştirilemedi, yalnızca ses gönderilecek: %s", exc)
        audio = Path(audio_path) if audio_path else _adjust_tempo(wav, settings.voice_speed)
        return MediaResult(status="ready", kind="audio", file_path=str(audio), url=public(audio.name),
                           detail=f"gemini:{settings.gemini_tts_model} (yalnızca ses)", audio_path=str(audio),
                           duration=duration)


def produce_mock(script: str, settings: Settings, out_dir: Path,
                 deadline: Optional[datetime] = None) -> MediaResult:
    """Test sağlayıcısı: dış servis çağırmadan yer tutucu bir ses dosyası üretir."""
    _check_deadline(deadline)
    audio = out_dir / "briefing_audio.mp3"
    audio.write_bytes(b"MOCK-AUDIO")
    return MediaResult(status="ready", kind="audio", file_path=str(audio), audio_path=str(audio), duration=54.0,
                       detail="mock")


PROVIDERS = {"elevenlabs": produce_elevenlabs, "heygen": produce_heygen, "did": produce_did, "gemini": produce_gemini,
             "mock": produce_mock}


def run(briefing_path: Path, settings: Optional[Settings] = None, deadline: Optional[datetime] = None,
        provider: Optional[str] = None) -> MediaResult:
    """Script yazar, medyayı üretir. Hata fırlatmaz; durumu MediaResult ile bildirir."""
    from agents.data_agent import load_briefing

    settings = settings or get_settings()
    briefing_path = Path(briefing_path)
    out_dir = briefing_path.parent
    provider = (provider or settings.video_provider).lower()

    script_path: Optional[Path] = None
    try:
        script = build_script(load_briefing(briefing_path), settings)
        script_path = out_dir / "teleprompter.txt"
        script_path.write_text(script, encoding="utf-8")
        log.info("Teleprompter scripti hazır (%d kelime)", count_words(script))
        # Seslendirme motoruna rakamlar kelimeyle, kısaltmalar açık şekilde gider.
        tts_text = normalize_for_speech(script)
        (out_dir / "teleprompter_tts.txt").write_text(tts_text, encoding="utf-8")

        producer = PROVIDERS.get(provider)
        if producer is None:
            result = MediaResult(status="skipped", detail=f"Sağlayıcı: {provider}")
        else:
            result = producer(tts_text, settings, out_dir, deadline)
    except DeadlineExceeded as exc:
        result = MediaResult(status="timeout", detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — video bülteni asla durdurmamalı
        log.exception("Ajan 3 hatası")
        result = MediaResult(status="failed", detail=str(exc))

    # Medya üretilemese de script spikere/arşive iletilebilsin diye yol her durumda korunur.
    result.script_path = str(script_path) if script_path else None
    log.info("Ajan 3 sonucu: %s", asdict(result))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ajan 3 — teleprompter + ses/video")
    ap.add_argument("briefing_json", type=Path)
    ap.add_argument("--provider", choices=["gemini", "elevenlabs", "heygen", "did", "mock", "none"], default=None)
    args = ap.parse_args()
    print(asdict(run(args.briefing_json, provider=args.provider)))
