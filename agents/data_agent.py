"""Ajan 1 — Data Collector & Curator.

Piyasa göstergelerini ve Tier-1 haberleri toplar, küratörlükten geçirir ve
`output/<tarih>/briefing.json` olarak kaydeder.

Bağımsız çalıştırma:
    python -m agents.data_agent --mock
"""
from __future__ import annotations

import argparse
import calendar
import json
import re
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional

import requests

from config import Settings, get_settings
from models import BANK_SOURCES, TIER1_SOURCES, Briefing, CalendarEvent, CuratedContent, MarketIndicator, NewsItem

log = logging.getLogger("agent1.data")

HTTP_TIMEOUT = 15

# Gösterge tanımları: anahtar -> (etiket, yfinance sembolü, birim, ondalık)
INDICATORS = {
    "bist100": ("BIST 100", "XU100.IS", "", 2),
    "usdtry": ("USD/TRY", "USDTRY=X", "", 4),
    "brent": ("Brent Petrol", "BZ=F", "$", 2),
    "gold": ("Ons Altın", "GC=F", "$", 2),
}

# Kaynağın kendisi Türkiye'ye özgüyse doğrudan Türkiye Gündemi; Bloomberg HT/Foreks hem küresel hem yerel yayın yapar.
TURKEY_SOURCES = {"KAP", "TCMB"}
TURKEY_KEYWORDS = (
    "türkiye", "türk ", "turkey", "tcmb", "bist", "borsa istanbul", "lira", "ankara", "kap ", "tüik", "bddk",
    "spk", "hazine ve maliye", "şimşek", "karahan", "erdoğan", "ziraat", "halkbank", "halk katılım", "vakıf",
    "tvf", "varlık fonu", "istanbul", "dolar/tl", "kamu bankası", "katılım bankası",
)


@dataclass
class RawNews:
    title: str
    summary: str
    source: str
    url: Optional[str]
    published: Optional[datetime]


# ---------------------------------------------------------------------------
# Piyasa verileri
# ---------------------------------------------------------------------------
def _fetch_yfinance(symbol: str):
    """Son iki kapanıştan (değer, % değişim) döndürür."""
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period="5d", interval="1d")
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        raise ValueError(f"{symbol} için yeterli veri yok")
    last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
    return last, (last - prev) / prev * 100


def _fetch_tcmb_usdtry() -> float:
    """TCMB gösterge kuru (today.xml) — yfinance erişilemezse yedek kaynak."""
    resp = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    node = root.find(".//Currency[@CurrencyCode='USD']/ForexSelling")
    if node is None or not node.text:
        raise ValueError("TCMB XML içinde USD bulunamadı")
    return float(node.text)


def fetch_market_data(settings: Settings) -> List[MarketIndicator]:
    """Tüm göstergeleri toplar; tek bir kaynağın hatası diğerlerini etkilemez."""
    out: List[MarketIndicator] = []
    for key, (label, symbol, unit, decimals) in INDICATORS.items():
        ind = MarketIndicator(key=key, label=label, unit=unit, decimals=decimals)
        try:
            ind.value, ind.change_pct = _fetch_yfinance(symbol)
            ind.source = "Piyasa verisi"
        except Exception as exc:  # noqa: BLE001 — her gösterge izole
            log.warning("%s alınamadı: %s", label, exc)
            if key == "usdtry":
                try:
                    ind.value, ind.source = _fetch_tcmb_usdtry(), "TCMB"
                except Exception as exc2:  # noqa: BLE001
                    log.warning("TCMB yedek kur da alınamadı: %s", exc2)
        out.append(ind)
    return out


# ---------------------------------------------------------------------------
# Haberler
# ---------------------------------------------------------------------------
TR_MONTH_ABBR = {"oca": 1, "şub": 2, "mar": 3, "nis": 4, "may": 5, "haz": 6, "tem": 7, "ağu": 8, "eyl": 9,
                 "eki": 10, "kas": 11, "ara": 12}
TR_TZ = timezone(timedelta(hours=3))


def parse_entry_date(entry) -> Optional[datetime]:
    """RFC tarihleri feedparser ile; TCMB'nin '1 Eki 2026 00:00:00' gibi Türkçe tarihleri elle ayrıştırılır."""
    import re

    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    raw = (entry.get("published") or entry.get("updated") or "").strip()
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", raw)
    if m and m.group(2)[:3].lower() in TR_MONTH_ABBR:
        d, mon, y, hh, mm, ss = m.groups()
        local = datetime(int(y), TR_MONTH_ABBR[mon[:3].lower()], int(d), int(hh or 0), int(mm or 0), int(ss or 0),
                         tzinfo=TR_TZ)
        return local.astimezone(timezone.utc)
    return None


def news_cutoff(now: datetime, lookback_hours: int) -> datetime:
    """Pazartesi sabahı hafta sonu gelişmelerini de kapsamak için pencere 48 saat uzatılır."""
    extra = 48 if now.astimezone(TR_TZ).weekday() == 0 else 0
    return now - timedelta(hours=lookback_hours + extra)


def fetch_news(settings: Settings, now: Optional[datetime] = None) -> List[RawNews]:
    """Yapılandırılmış RSS/Atom akışlarından haber penceresindeki haberleri çeker.

    Tarihi okunamayan haberler elenir; aksi halde eski duyurular bültene sızabilir.
    """
    import feedparser

    now = now or datetime.now(timezone.utc)
    cutoff = news_cutoff(now, settings.news_lookback_hours)
    items: List[RawNews] = []
    for source, url in settings.news_feeds:
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": "Mozilla/5.0 MorningBriefing/1.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s akışı okunamadı: %s", source, exc)
            continue
        kept = 0
        for entry in feed.entries:
            published = parse_entry_date(entry)
            if published is None or published < cutoff or published > now + timedelta(hours=1):
                continue
            kept += 1
            items.append(
                RawNews(
                    title=_strip_html(entry.get("title", "")),
                    summary=_strip_html(entry.get("summary", ""))[:600],
                    source=source,
                    url=entry.get("link"),
                    published=published,
                )
            )
        log.info("%s: %d/%d haber pencere içinde", source, kept, len(feed.entries))
    if settings.kap_enabled:
        from agents.kap_source import fetch_kap_news

        items += fetch_kap_news(settings, now=now, cutoff=cutoff)
    if settings.bank_news_enabled:
        from agents.bank_news import fetch_bank_news, to_raw_news

        try:
            items += to_raw_news(fetch_bank_news(today=now.astimezone(TR_TZ).date()))
        except Exception as exc:  # noqa: BLE001
            log.warning("Banka haberleri alınamadı: %s", exc)
    return filter_tier1(items)


def filter_tier1(items: List[RawNews]) -> List[RawNews]:
    """Sadece Tier-1 kaynaklar; başlık bazlı tekilleştirme."""
    seen, out = set(), []
    for it in items:
        key = it.title.lower()[:80]
        if it.source in TIER1_SOURCES and it.title and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _strip_html(text: str) -> str:
    import re

    import html

    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


# ---------------------------------------------------------------------------
# Küratörlük
# ---------------------------------------------------------------------------
CURATOR_SYSTEM = """Sen bir yatırım bankasının sabah bülteni editörüsün. Okuyucular üst düzey yöneticiler ve portföy yöneticileridir.
Kurallar:
- Yalnızca sana verilen haber listesindeki bilgileri kullan; rakam, tarih veya olay uydurma.
- Executive Summary: 3-5 madde, her biri tek ve yoğun bir cümle, piyasaya etkisi net.
- Küresel Gelişmeler ve Türkiye Gündemi: her biri en fazla 5 haber, önem sırasına göre; özetler 1-2 cümle.
- Aynı olayı anlatan haberleri (farklı kaynaklardan gelse bile) TEK maddede birleştir; birden fazla kaynak varsa
  source alanına virgülle yaz (ör. "Bloomberg HT, Foreks"); url olarak birincil kaynağınkini (KAP/TCMB/banka) seç.
- Kaynak alanına haberin geldiği kaynağı aynen yaz; url ve published_at değerlerini verilen veriden aynen koru.
- impact: politika faizi, enflasyon, jeopolitik şok, kredi notu, büyük birleşme/satın alma = "high"; şirket ölçeğinde
  rutin gelişmeler = "medium"; bağlam bilgisi = "low".
- Ekonomik takvim: yalnızca haberlerde veya verilen takvim verisinde geçen bugünkü veri/karar açıklamaları.
- Bankacılık Gündemi: kaynağı Garanti BBVA, Akbank, Yapı Kredi veya QNB olan haberler (bankaların kendi
  duyuruları) yalnızca bu bölüme girer; tahvil/eurobond ihracı, sendikasyon, fonlama, finansal sonuçlar gibi
  finansal önemi olanları seç. Uygun haber yoksa bölümü boş bırak.
- Dil: profesyonel Türkçe, nötr ton, yatırım tavsiyesi verme."""


def _curate_with_llm(news: List[RawNews], markets: List[MarketIndicator], calendar_hint: List[dict],
                     settings: Settings) -> CuratedContent:
    from agents import llm

    payload = {
        "markets": [m.model_dump(include={"label", "value", "change_pct", "unit"}) for m in markets],
        "news": [
            {"title": n.title, "summary": n.summary, "source": n.source, "url": n.url,
             "published": n.published.isoformat() if n.published else None}
            for n in news
        ],
        "calendar": calendar_hint,
    }
    return llm.generate_json(
        settings, CURATOR_SYSTEM,
        "Bugünün sabah bülteni için aşağıdaki verileri küratörlükten geçir:\n\n" + json.dumps(payload, ensure_ascii=False),
        CuratedContent,
    )


def _curate_rule_based(news: List[RawNews], calendar_hint: List[dict]) -> CuratedContent:
    """LLM yokken deterministik yedek: kaynağa/anahtar kelimeye göre sınıflandırır."""
    def is_turkey(n: RawNews) -> bool:
        text = f" {n.title} {n.summary} ".lower()
        return n.source in TURKEY_SOURCES or any(k in text for k in TURKEY_KEYWORDS)

    news = sorted(news, key=lambda n: n.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def to_item(n: RawNews) -> NewsItem:
        return NewsItem(headline=n.title, summary=n.summary[:280] or n.title, source=n.source, url=n.url,
                        published_at=n.published.isoformat() if n.published else None)

    def balanced(items: List[RawNews], limit: int = 5, per_source: int = 2) -> List[NewsItem]:
        """Tek bir kaynağın bölümü doldurmasını engeller (kaynak başına en fazla `per_source`)."""
        counts: dict = {}
        out: List[NewsItem] = []
        for n in items:
            if counts.get(n.source, 0) < per_source:
                counts[n.source] = counts.get(n.source, 0) + 1
                out.append(to_item(n))
            if len(out) == limit:
                break
        return out

    banks = balanced([n for n in news if n.source in BANK_SOURCES], limit=4, per_source=1)
    news = [n for n in news if n.source not in BANK_SOURCES]
    tr = balanced([n for n in news if is_turkey(n)])
    gl = balanced([n for n in news if not is_turkey(n)])
    summary = [i.headline for i in (gl[:2] + tr[:3])] or ["Bugün için Tier-1 kaynaklarda öne çıkan gelişme bulunmadı."]
    return CuratedContent(
        executive_summary=summary,
        global_developments=gl,
        turkey_agenda=tr,
        banking_agenda=banks,
        economic_calendar=[CalendarEvent(**e) for e in calendar_hint],
    )


FIGURE_RE = re.compile(
    r"\d[\d.,]*\d|\d|(?:ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\s+\d{4}")


def verify_content(content: CuratedContent, news: List[RawNews], markets: List[MarketIndicator]) -> List[str]:
    """Yapay zekâ çıktısını kaynak verilere karşı denetler (uydurma koruması).

    - Kaynak haberlerde olmayan linkler silinir.
    - Kaynak haberlerde veya piyasa verisinde geçmeyen rakam/tarihler döndürülür (çalışma kaydına uyarı).
    """
    corpus = " ".join(f"{n.title} {n.summary}" for n in news).lower()
    corpus += " " + " ".join(
        f"{m.label} {m.value} {m.change_pct} {fmt_tr(m.value, m.decimals)} {fmt_tr(abs(m.change_pct or 0), 2)}"
        for m in markets if m.value is not None).lower()
    known_urls = {n.url for n in news if n.url}
    texts = list(content.executive_summary)
    for item in content.global_developments + content.turkey_agenda + content.banking_agenda:
        if item.url and item.url not in known_urls:
            log.warning("Kaynakta olmayan link kaldırıldı: %s", item.url)
            item.url = None
        texts.append(f"{item.headline} {item.summary}")
    unverified = sorted({f for t in texts for f in FIGURE_RE.findall(t.lower()) if f not in corpus})
    if unverified:
        log.warning("Kaynakta doğrulanamayan rakam/tarih: %s", ", ".join(unverified))
    return unverified


def fmt_tr(value: Optional[float], decimals: int) -> str:
    if value is None:
        return ""
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def curate(news: List[RawNews], markets: List[MarketIndicator], settings: Settings,
           calendar_hint: Optional[List[dict]] = None) -> CuratedContent:
    from agents import llm

    calendar_hint = calendar_hint or []
    if llm.available(settings):
        try:
            content = _curate_with_llm(news, markets, calendar_hint, settings)
            log.info("Küratörlük: %s", llm.provider(settings))
            content._unverified = verify_content(content, news, markets)
            return content
        except Exception as exc:  # noqa: BLE001 — bülten her koşulda çıkmalı
            log.error("Yapay zekâ küratörlüğü (%s) başarısız, kural tabanlı yedeğe geçiliyor: %s",
                      llm.provider(settings), exc)
    return _curate_rule_based(news, calendar_hint)


def load_calendar_hint(settings: Settings, run_date: date) -> List[dict]:
    """Ekonomik takvim: output/<tarih>/calendar.json veya fixtures/economic_calendar.json (varsa)."""
    for path in (settings.output_dir / run_date.isoformat() / "calendar.json",
                 settings.fixtures_dir / "economic_calendar.json"):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------
def build_briefing(markets: List[MarketIndicator], content: CuratedContent, run_date: date,
                   bank_watch: Optional[List[dict]] = None) -> Briefing:
    sources = sorted({n.source for n in content.global_developments + content.turkey_agenda + content.banking_agenda}
                     | {m.source for m in markets if m.source})
    return Briefing(
        date=run_date.isoformat(),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        markets=markets,
        sources=sources,
        unverified_figures=content._unverified,
        bank_watch=bank_watch or [],
        **content.model_dump(),
    )


def load_mock_briefing(settings: Settings, run_date: date) -> Briefing:
    data = json.loads((settings.fixtures_dir / "mock_briefing.json").read_text(encoding="utf-8"))
    data["date"] = run_date.isoformat()
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return Briefing(**data)


def run(settings: Optional[Settings] = None, run_date: Optional[date] = None, mock: bool = False,
        market_fetcher: Callable[[Settings], List[MarketIndicator]] = fetch_market_data,
        news_fetcher: Callable[[Settings], List[RawNews]] = fetch_news,
        bank_watch_fetcher: Optional[Callable[[Settings, date], List[dict]]] = None) -> Path:
    """Ajan 1'i çalıştırır ve JSON dosya yolunu döndürür."""
    settings = settings or get_settings()
    run_date = run_date or date.today()
    out_dir = settings.output_dir / run_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    bank_watch_fetcher = bank_watch_fetcher or fetch_bank_watch
    if mock:
        briefing = load_mock_briefing(settings, run_date)
    else:
        markets = market_fetcher(settings)
        news = news_fetcher(settings)
        log.info("%d Tier-1 haber toplandı", len(news))
        save_raw_news(news, out_dir / "raw_news.json")
        content = curate(news, markets, settings, load_calendar_hint(settings, run_date))
        briefing = build_briefing(markets, content, run_date, bank_watch_fetcher(settings, run_date))

    path = out_dir / "briefing.json"
    path.write_text(briefing.model_dump_json(indent=2), encoding="utf-8")
    log.info("Ajan 1 tamamlandı → %s", path)
    return path


def fetch_bank_watch(settings: Settings, run_date: date) -> List[dict]:
    """"4 Büyük Banka" bölümü (her gün görünür). Hata bülteni durdurmaz."""
    if not settings.bank_news_enabled:
        return []
    try:
        from agents.bank_news import fetch_bank_watch as _watch, load_kap_records

        return _watch(today=run_date, mentions=settings.bank_mentions_enabled,
                      kap_records=load_kap_records(settings.output_dir, run_date))
    except Exception as exc:  # noqa: BLE001
        log.warning("4 Büyük Banka bölümü hazırlanamadı: %s", exc)
        return []


def save_raw_news(news: List[RawNews], path: Path) -> None:
    """Toplanan tüm Tier-1 haberler (yalnızca bültene seçilenler değil) — terminal piyasa akışı için."""
    path.write_text(json.dumps([
        {"title": n.title, "summary": n.summary, "source": n.source, "url": n.url,
         "published": n.published.isoformat() if n.published else None} for n in news
    ], ensure_ascii=False, indent=1), encoding="utf-8")


def load_raw_news(path: Path) -> List[RawNews]:
    if not Path(path).exists():
        return []
    return [RawNews(title=d["title"], summary=d.get("summary") or "", source=d["source"], url=d.get("url"),
                    published=datetime.fromisoformat(d["published"]) if d.get("published") else None)
            for d in json.loads(Path(path).read_text(encoding="utf-8"))]


def load_briefing(path: Path) -> Briefing:
    return Briefing.model_validate_json(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ajan 1 — veri toplama ve küratörlük")
    ap.add_argument("--mock", action="store_true", help="Sahte veriyle çalıştır")
    args = ap.parse_args()
    print(run(mock=args.mock))
