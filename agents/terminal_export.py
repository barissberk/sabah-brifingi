"""Görsel Ajan veri aktarıcısı — AURA TERMINAL için `terminal/public/data/terminal.json`.

Boru hattının ürettiklerini (bülten JSON'u, toplanan tüm haberler, ses ve konuşma metni) terminal
arayüzünün okuyacağı tek bir sözleşmeye dönüştürür. Ek olarak terminale özgü verileri çeker:
genişletilmiş gösterge şeridi, BIST 100 pivot seviyeleri ve sektör nabzı.

Ücretsiz kaynağı olmayan alanlar uydurulmaz:
  - TR 2Y tahvil → değer yok ("—"), lisanslı kaynak gerekir.
  - Analist masası (hedef fiyatlar) → açıkça "örnek veri" işaretli, gerçek kurum adı kullanılmaz.

Bağımsız çalıştırma:
    python -m agents.terminal_export output/2026-10-09/briefing.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config import BASE_DIR, Settings, get_settings
from models import BANK_SOURCES, Briefing

log = logging.getLogger("agent5.terminal")

TERMINAL_DATA_DIR = BASE_DIR / "terminal" / "public" / "data"

# Gösterge şeridi: (sembol, ad, yfinance, ondalık, tür)
TICKERS = [
    ("XU100", "BIST 100", "XU100.IS", 2, "index"),
    ("XU030", "BIST 30", "XU030.IS", 2, "index"),
    ("USDTRY", "USD/TRY", "USDTRY=X", 4, "fx"),
    ("EURTRY", "EUR/TRY", "EURTRY=X", 4, "fx"),
    ("EURUSD", "EUR/USD", "EURUSD=X", 4, "fx"),
    ("DXY", "Dolar Endeksi", "DX-Y.NYB", 2, "index"),
    ("BRENT", "Brent", "BZ=F", 2, "commodity"),
    ("XAUUSD", "Altın (XAU/USD)", "GC=F", 2, "commodity"),
    ("TR2Y", "TR 2Y Tahvil", None, 2, "rate"),
    ("US10Y", "ABD 10Y Getiri", "^TNX", 3, "rate"),
]

# Sektör nabzı: endeks yoksa öncü hisse sepeti (arayüzde "sepet" olarak gösterilir)
SECTORS = [
    ("banking", "Bankacılık", ["XBANK.IS"], None),
    ("transport", "Ulaştırma", ["THYAO.IS", "PGSUS.IS", "CLEBI.IS"], "THYAO · PGSUS · CLEBI"),
    ("industrial", "Sanayi", ["XUSIN.IS"], None),
    ("holding", "Holding", ["KCHOL.IS", "SAHOL.IS", "AGHOL.IS"], "KCHOL · SAHOL · AGHOL"),
    ("tech", "Teknoloji", ["ASELS.IS", "LOGO.IS", "KAREL.IS"], "ASELS · LOGO · KAREL"),
]

# Haber metninden hisse etiketi çıkarımı (yalnızca adı açıkça geçerse)
TICKER_NAMES = {
    "GARAN": ("garanti",), "AKBNK": ("akbank",), "YKBNK": ("yapı kredi", "yapi kredi"), "QNBTR": ("qnb",),
    "ISCTR": ("iş bankası", "işbank"), "HALKB": ("halkbank", "halk bankası"), "VAKBN": ("vakıfbank",),
    "THYAO": ("türk hava yolları", "thy "), "PGSUS": ("pegasus",), "CLEBI": ("çelebi",),
    "ASELS": ("aselsan",), "EREGL": ("ereğli", "erdemir"), "KRDMD": ("kardemir",), "KCHOL": ("koç holding",),
    "SAHOL": ("sabancı",), "TUPRS": ("tüpraş",), "BIMAS": ("bim ",), "FROTO": ("ford otosan",),
    "TCELL": ("turkcell",), "SISE": ("şişecam",), "HEKTS": ("hektaş",), "ENDAE": ("enda enerji",),
}

CATEGORY_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("emtia", ("petrol", "brent", "altın", "gümüş", "emtia", "doğal gaz", "doğalgaz", "opec", "bakır", "varil")),
    ("doviz", ("dolar/tl", "kur ", "kuru", "döviz", "euro", "tahvil", "getiri", "cds", "eurobond", "swap",
               "rezerv")),
    ("makro", ("merkez bankası", "tcmb", "fed", "ecb", "faiz", "enflasyon", "ppk", "büyüme", "istihdam",
               "işsizlik", "gsyh", "tüfe", "üfe", "bütçe", "cari", "ticaret savaş", "gümrük", "yaptırım")),
]
HIGH_IMPACT_TERMS = ("faiz kararı", "ppk", "enflasyon", "fed ", "ecb", "cds", "rezerv", "eurobond", "temettü",
                     "birleşme", "satın al", "yaptırım", "savaş", "çatışma", "kredi notu", "resesyon")


def _yf_history(symbol: str):
    import yfinance as yf

    return yf.Ticker(symbol).history(period="5d", interval="1d")


def fetch_tickers(history: Callable = _yf_history) -> List[dict]:
    out = []
    for sym, name, yf_sym, dec, kind in TICKERS:
        item = {"symbol": sym, "name": name, "value": None, "change": None, "change_unit": "%", "decimals": dec,
                "kind": kind, "source": None}
        if yf_sym:
            try:
                closes = history(yf_sym)["Close"].dropna()
                last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                item["value"] = last
                if kind == "rate":  # getirilerde değişim baz puan
                    item["change"], item["change_unit"] = round((last - prev) * 100, 1), "bp"
                else:
                    item["change"] = (last - prev) / prev * 100
                item["source"] = "Piyasa verisi (önceki kapanış)"
            except Exception as exc:  # noqa: BLE001
                log.warning("%s alınamadı: %s", sym, exc)
        else:
            item["source"] = "Lisanslı kaynak gerekli"
        out.append(item)
    return out


def compute_pivot(high: float, low: float, close: float) -> Dict[str, float]:
    """Klasik pivot: P=(H+L+C)/3, R1=2P−L, S1=2P−H, R2=P+(H−L), S2=P−(H−L)."""
    p = (high + low + close) / 3
    return {"pivot": p, "r1": 2 * p - low, "r2": p + (high - low), "s1": 2 * p - high, "s2": p - (high - low)}


def fetch_pivot(history: Callable = _yf_history) -> Optional[dict]:
    try:
        h = history("XU100.IS").dropna()
        last = h.iloc[-1]
        levels = compute_pivot(float(last["High"]), float(last["Low"]), float(last["Close"]))
        return {"symbol": "XU100", "basis": f"{h.index[-1].date():%d.%m.%Y} seansı (Y/D/K)", **levels}
    except Exception as exc:  # noqa: BLE001
        log.warning("Pivot hesaplanamadı: %s", exc)
        return None


def fetch_sectors(history: Callable = _yf_history) -> List[dict]:
    out = []
    for key, name, symbols, basket in SECTORS:
        changes = []
        for s in symbols:
            try:
                c = history(s)["Close"].dropna()
                changes.append((float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100)
            except Exception:  # noqa: BLE001
                continue
        out.append({"key": key, "name": name, "change": sum(changes) / len(changes) if changes else None,
                    "basket": basket})
    return out


def categorize(source: str, text: str) -> str:
    if source == "KAP":
        return "kap"
    if source in BANK_SOURCES:
        return "bist"
    low = f" {text.lower()} "
    for cat, terms in CATEGORY_RULES:
        if any(t in low for t in terms):
            return cat
    return "bist" if any(k in low for k in ("bist", "borsa", "hisse", "şirket", "a.ş", "holding")) else "makro"


def detect_tickers(text: str) -> List[str]:
    low = f" {text.lower()} "
    return [t for t, names in TICKER_NAMES.items() if any(n in low for n in names)]


def _impact(text: str, curated_impact: Optional[str]) -> str:
    if curated_impact:
        return curated_impact
    return "high" if any(t in f" {text.lower()} " for t in HIGH_IMPACT_TERMS) else "medium"


def build_wire(briefing: Briefing, raw_news: list) -> List[dict]:
    """Toplanan tüm haberler + bültene seçilenlerin (daha iyi özetli) sürümleri, tekilleştirilmiş."""
    curated = {}
    for n in briefing.global_developments + briefing.turkey_agenda + briefing.banking_agenda:
        curated[n.url or n.headline] = n
    items, seen = [], set()

    def add(headline, summary, source, url, published, impact=None, in_briefing=False):
        key = url or re.sub(r"\W+", "", headline.lower())
        if key in seen:
            return
        seen.add(key)
        text = f"{headline} {summary}"
        items.append({
            "id": f"n{len(items) + 1}", "headline": headline, "summary": summary, "source": source, "url": url,
            "published": published, "category": categorize(source, text), "impact": _impact(text, impact),
            "tickers": detect_tickers(text), "in_briefing": in_briefing,
            "take": None, "commentary": None, "figures": [],
        })

    for n in curated.values():
        add(n.headline, n.summary, n.source, n.url, n.published_at, n.impact, True)
    for r in raw_news:
        published = r.published.isoformat() if r.published else None
        c = curated.get(r.url)
        add(c.headline if c else r.title, c.summary if c else r.summary, r.source, r.url, published,
            c.impact if c else None, bool(c))
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return items


def build_pillars(briefing: Briefing) -> List[dict]:
    """Sabahın 3 kritik ekseni: yönetici özetinin ilk üç maddesi.

    Madde kısa bir başlık ise (kural tabanlı özet) gövde olarak ilgili haberin özeti kullanılır.
    """
    summaries = {re.sub(r"\W+", "", n.headline.lower()): n.summary
                 for n in briefing.global_developments + briefing.turkey_agenda + briefing.banking_agenda}
    pillars = []
    for text in briefing.executive_summary[:3]:
        clean = re.sub(r"^\[[^\]]*\]\s*", "", text)
        head = clean.split(";")[0]
        words = head.split()
        title = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
        body = clean
        if len(clean.split()) <= 12:                      # yalnızca başlık: haberin özetiyle zenginleştir
            match = summaries.get(re.sub(r"\W+", "", text.lower()))
            body = match if match and match != text else ""
        pillars.append({"title": title, "body": body})
    return pillars


SAMPLE_ANALYST_DESK = [
    {"ticker": "THYAO", "house": "Örnek Kurum A", "old_target": 410.0, "new_target": 455.0, "price": 352.5,
     "rating": "AL"},
    {"ticker": "GARAN", "house": "Örnek Kurum B", "old_target": 165.0, "new_target": 178.0, "price": 142.3,
     "rating": "ENDEKS ÜSTÜ"},
    {"ticker": "EREGL", "house": "Örnek Kurum C", "old_target": 38.0, "new_target": 36.5, "price": 33.8,
     "rating": "TUT"},
    {"ticker": "ASELS", "house": "Örnek Kurum D", "old_target": 120.0, "new_target": 134.0, "price": 108.9,
     "rating": "AL"},
]


def export_audio(media: Optional[dict], out_dir: Path, data_dir: Path) -> Optional[dict]:
    """Doğal hızdaki sesi web için AAC'ye çevirir; hız arayüzde (1.0/1.25/1.5x) ayarlanır."""
    from agents.video_agent import ffmpeg_exe

    transcript_path = out_dir / "teleprompter.txt"
    src = out_dir / "briefing_audio.wav"
    briefing_mtime = (out_dir / "briefing.json").stat().st_mtime
    # Ses/metin bültenden eskiyse başka bir bültene aittir (ör. önceki deneme) — aktarılmaz.
    if transcript_path.exists() and transcript_path.stat().st_mtime < briefing_mtime:
        log.warning("Konuşma metni bültenden eski; ses ve metin terminale aktarılmadı")
        return None
    transcript = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else ""
    if not src.exists() or src.stat().st_mtime < briefing_mtime:
        return {"url": None, "duration": None, "transcript": transcript} if transcript else None
    exe = ffmpeg_exe()
    dst = data_dir / "briefing_audio.m4a"
    try:
        if not exe:
            raise RuntimeError("ffmpeg yok")
        subprocess.run([exe, "-y", "-loglevel", "error", "-i", str(src), "-c:a", "aac", "-b:a", "96k", str(dst)],
                       check=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        log.warning("Ses web formatına çevrilemedi, WAV kopyalanıyor: %s", exc)
        dst = data_dir / "briefing_audio.wav"
        shutil.copy(src, dst)
    import wave

    with wave.open(str(src), "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
    return {"url": f"data/{dst.name}", "duration": round(duration, 1), "transcript": transcript}


def build_payload(briefing: Briefing, raw_news: list, tickers: List[dict], pivot: Optional[dict],
                  sectors: List[dict], audio: Optional[dict], is_demo: bool) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": briefing.date,
        "is_demo": is_demo,
        "tickers": tickers,
        "pivot": pivot,
        "sectors": sectors,
        "executive_summary": briefing.executive_summary,
        "pillars": build_pillars(briefing),
        "audio": audio,
        "wire": build_wire(briefing, raw_news),
        "calendar": [dict(e.model_dump(), actual=None) for e in briefing.economic_calendar],
        "analyst_desk": {"is_sample": True, "rows": SAMPLE_ANALYST_DESK},
        "sources": briefing.sources,
    }


def run(briefing_path: Path, settings: Optional[Settings] = None, mock: bool = False,
        data_dir: Optional[Path] = None, history: Optional[Callable] = None) -> Path:
    from agents.data_agent import load_briefing, load_raw_news

    settings = settings or get_settings()
    data_dir = data_dir or TERMINAL_DATA_DIR          # çağrı anında çözülür (testler yönlendirebilsin)
    history = history or _yf_history
    briefing_path = Path(briefing_path)
    out_dir = briefing_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    briefing = load_briefing(briefing_path)
    raw_news = load_raw_news(out_dir / "raw_news.json")
    if mock:
        tickers, pivot, sectors = [], None, []   # arayüz kendi örnek veri setini kullanır
    else:
        tickers, pivot, sectors = fetch_tickers(history), fetch_pivot(history), fetch_sectors(history)
    payload = build_payload(briefing, raw_news, tickers, pivot, sectors,
                            export_audio(None, out_dir, data_dir), is_demo=mock)
    path = data_dir / "terminal.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Görsel ajan verisi hazır → %s (%d akış haberi)", path, len(payload["wire"]))
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="AURA TERMINAL veri aktarımı")
    ap.add_argument("briefing_json", type=Path)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    print(run(args.briefing_json, mock=args.mock))
