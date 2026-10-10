"""Banka haber kaynağı: bankaların kendi sitelerindeki basın bültenleri ve haberler.

Her bankanın sayfa yapısı farklı olduğundan bankaya özel kod yazılmaz. Genel bir çıkarıcı,
sayfada tarih içeren her "haber kartını" bulur: tarihten yukarı doğru çıkarak tek bir haber
linki içeren en küçük kapsayıcıyı arar; başlığı, özeti ve linki oradan alır.

Yalnızca kamuya duyurulmak üzere yayımlanan kurumsal haberler okunur (araştırma raporları değil).
Her banka için sayfa başına tek istek atılır; bir banka hata verirse diğerleri etkilenmez.

Bağımsız çalıştırma:
    python -m agents.bank_news           # pencere içindeki banka haberleri
    python -m agents.bank_news --all     # sayfalardaki tüm haberler (tarih filtresi olmadan)
"""
from __future__ import annotations

import argparse
import json
import copy
import time as _time
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

log = logging.getLogger("agent1.banks")

TR_TZ = timezone(timedelta(hours=3))
HTTP_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 MorningBriefing/1.0"


@dataclass(frozen=True)
class BankPage:
    bank: str
    url: str


# Varsayılan kaynaklar; BANK_NEWS_PAGES ile değiştirilebilir ("Banka|URL,Banka|URL").
DEFAULT_PAGES = [
    BankPage("Garanti BBVA", "https://www.garantibbva.com.tr/kurumsal-iletisim/garanti-bbvadan-haberler"),
    BankPage("Akbank", "https://www.akbank.com/haberler"),
    BankPage("Yapı Kredi", "https://www.yapikredi.com.tr/yapi-kredi-hakkinda/basin-bultenleri"),
    BankPage("QNB", "https://www.qnb.com.tr/qnbyi-taniyin/basin-odasi/basin-bultenleri"),
]

TR_MONTHS = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
             "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
DATE_RE = re.compile(
    r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b"
    r"|\b(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+(20\d{2})\b",
    re.IGNORECASE,
)


@dataclass
class BankNews:
    bank: str
    title: str
    published: date
    url: str
    summary: str = ""


def parse_tr_date(text: str) -> Optional[date]:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        if m.group(1):
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return date(int(m.group(6)), TR_MONTHS[m.group(5).lower()], int(m.group(4)))
    except (ValueError, KeyError):
        return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _tidy_title(title: str) -> str:
    """'... DESTEK.pdf' gibi dosya uzantılarını temizler; harf büyüklüğüne dokunmaz
    (Türkçe/İngilizce karışık başlıklarda otomatik dönüşüm kelimeleri bozuyor)."""
    return re.sub(r"\.(pdf|docx?)$", "", _clean(title), flags=re.I)


def extract_items(html: str, page_url: str, bank: str) -> List[BankNews]:
    """Sayfadaki tarihli haber kartlarını çıkarır."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    page_path = urlparse(page_url).path.rstrip("/")

    def article_links(node) -> List[str]:
        hrefs = []
        for a in node.find_all("a", href=True):
            href = urljoin(page_url, a["href"].split("#")[0])
            path = urlparse(href).path.rstrip("/")
            if path and path != page_path and not href.startswith(("mailto:", "tel:", "javascript:")):
                hrefs.append(href)
        return list(dict.fromkeys(hrefs))

    items: List[BankNews] = []
    seen = set()
    for text_node in soup.find_all(string=DATE_RE):
        published = parse_tr_date(text_node)
        if published is None:
            continue
        # Tarihten yukarı çık: tek bir haber linki taşıyan en GENİŞ kapsayıcı = haber kartı
        # (en küçüğü çoğu zaman yalnızca tarih + "Detay" linkidir, başlık içermez).
        node, card, card_link = text_node.parent, None, None
        for _ in range(8):
            links = article_links(node)
            if len(links) > 1 or (card_link and links and links[0] != card_link):
                break
            if len(links) == 1:
                card, card_link = node, links[0]
            if node.parent is None:
                break
            node = node.parent
        if card is None:
            continue
        url = card_link
        heading = card.find(["h1", "h2", "h3", "h4", "h5", "strong"])
        anchor_texts = [_clean(a.get_text(" ")) for a in card.find_all("a", href=True)]
        candidates = [t for t in ([_clean(heading.get_text(" "))] if heading else []) + anchor_texts
                      if len(t) > 15 and not DATE_RE.fullmatch(t) and t.lower() not in ("detaylı bilgi", "detay")]
        if not candidates:                       # başlık düz metinse: kartın ilk anlamlı satırı
            candidates = [t for t in (_clean(x) for x in card.stripped_strings)
                          if len(t) > 15 and not DATE_RE.search(t) and not t.lower().startswith("detay")][:1]
        if not candidates:
            continue
        title = _tidy_title(candidates[0])
        key = (re.sub(r"\W+", "", title.lower()), published)
        if url in seen or key in seen:           # aynı haberin farklı dosya/link kopyaları
            continue
        chunks = [_clean(s) for s in card.stripped_strings]
        summary = max((c for c in chunks if c != candidates[0] and not DATE_RE.search(c) and len(c) > 60),
                      key=len, default="")
        seen.update({url, key})
        items.append(BankNews(bank=bank, title=title, published=published, url=url, summary=summary[:400]))
    return items


def fetch_description(url: str) -> str:
    """Özeti olmayan haberler için makale sayfasındaki meta açıklamayı okur (HTML ise)."""
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        if "html" not in resp.headers.get("content-type", ""):
            return ""
        m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]+)"',
                      resp.text, re.I)
        return _clean(m.group(1)) if m else ""
    except requests.RequestException:
        return ""


# Banka için finansal önemi olan haberler (başlık + özet, küçük harf)
IMPORTANT_TERMS = {
    "tahvil": 3, "eurobond": 3, "ihraç": 2, "sendikasyon": 3, "seküritizasyon": 3, "fonlama": 2, "kaynak sağla": 2,
    "yeni kaynak": 2, "ana sermaye": 3, "sermaye": 2, "bilanço": 3, "net kâr": 3, "net kar": 3, "kârlılık": 2,
    "finansal sonuç": 3, "çeyrek": 1, "kredi desteği": 2, "ekonomiye": 1, "trilyon": 2, "milyar": 1,
    "milyon dolar": 2, "milyon abd": 2, "birleşme": 3, "satın al": 3, "devral": 3, "stratejik iş birliği": 2,
    "derecelendirme": 3, "kredi notu": 3, "temettü": 3, "kâr payı": 3, "faiz": 1, "dijital banka": 1,
    "vdmk": 3, "ihraç tavan": 2, "aktif büyüklü": 3, "fon büyüklü": 2, "rekabet kurulu": 2, "devr": 2, "hedef fiyat": 2,
    "bilanço tarihi": 1, "pay geri alım": 1, "milyar euro": 2, "milyon euro": 2,
}
# Kurumsal iletişim / etkinlik içerikleri: bülten için önemsiz
MINOR_TERMS = ("konser", "sergi", "ödül", "award", "farkındalık", "kariyer", "program", "festival", "sanat",
               "dünya saati", "taraftar", "spor", "kampanya", "hackathon", "konferans", "iklim haftası", "gençler",
               "öğrenci", "çocuk", "eğitim", "promosyon", "emekli", "canlı grafik", "chip-para", "fırsat",
               "tradingview", "buluşma", "sponsor")
MIN_IMPORTANCE = 2


def importance(item: BankNews) -> int:
    text = f"{item.title} {item.summary}".lower()
    score = sum(w for term, w in IMPORTANT_TERMS.items() if term in text)
    if any(term in text for term in MINOR_TERMS):
        score -= 3
    return score


def previous_business_day(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# Aynı çalışma içinde her banka sayfası bir kez indirilir (taze haberler + "4 Büyük Banka" bölümü)
_PAGE_CACHE: Dict[str, Tuple[float, Optional[List[BankNews]]]] = {}
CACHE_TTL = 900


def page_items(page: BankPage) -> Optional[List[BankNews]]:
    """Sayfadaki tüm haber kartları (önbellekli). Hata durumunda None."""
    cached = _PAGE_CACHE.get(page.url)
    if cached and _time.monotonic() - cached[0] < CACHE_TTL:
        return [copy.copy(i) for i in cached[1]] if cached[1] is not None else None
    try:
        resp = requests.get(page.url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        items: Optional[List[BankNews]] = extract_items(resp.text, page.url, page.bank)
        if not items:
            log.warning("%s: sayfada haber kartı bulunamadı (sayfa yapısı değişmiş olabilir)", page.bank)
    except Exception as exc:  # noqa: BLE001 — bir banka diğerlerini etkilemez
        log.warning("%s haber sayfası okunamadı: %s", page.bank, exc)
        items = None
    _PAGE_CACHE[page.url] = (_time.monotonic(), items)
    return [copy.copy(i) for i in items] if items is not None else None


# ---------------------------------------------------------------------------
# Diğer kaynaklar: basın (Google Haberler araması, güvenilir yayın listesi) + KAP bildirimleri
# ---------------------------------------------------------------------------
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
# banka → (arama sorgusu, başlıkta aranacak adlar, KAP unvanı parçası)
BANK_QUERIES = {
    "Garanti BBVA": ('"Garanti BBVA"', ("garanti bbva", "garanti bankası"), "GARANTİ BANKASI"),
    "Akbank": ("Akbank", ("akbank",), "AKBANK"),
    "Yapı Kredi": ('"Yapı Kredi"', ("yapı kredi", "yapı ve kredi"), "YAPI VE KREDİ BANKASI"),
    "QNB": ('"QNB Türkiye" OR "QNB Bank" OR "QNB Finansbank"', ("qnb",), "QNB BANK"),
}
# Yalnızca tanınmış haber/finans yayınları (yerel/içerik çiftliği siteler elenir)
TRUSTED_OUTLETS = (
    "anadolu ajansı", "aa", "bloomberght", "bloomberg ht", "bloomberg", "reuters", "investing.com", "dünya",
    "ekonomim", "habertürk", "haberturk", "ntv", "cnn türk", "milliyet", "hürriyet", "sabah", "ekonomi gazetesi",
    "paratic", "ekotürk", "foreks", "borsa gündem", "borsa gundem", "matriks", "patronlar dünyası", "uzmanpara",
    "para analiz", "fortune türkiye", "capital", "yeni şafak", "dha", "iha",
)
MENTION_WINDOW_DAYS = 3
MAX_MENTIONS = 3            # finansal haber (basın + KAP)
MAX_CORPORATE = 2           # promosyon / ödül / sponsorluk — konu başına en fazla 1
# Kurumsal ve müşteri odaklı haberler: ayrı alt başlıkta gösterilir
# Sıra önemli: ilk eşleşen konu seçilir ("Garanti BBVA Emeklilik'e ödül" → ödül, promosyon değil)
CORPORATE_TOPICS = {
    "ödül": ("ödül", "award", "birincilik"),
    "sponsorluk": ("sponsor", "konser", "festival", "sergi", "sanat", "taraftar"),
    "promosyon": ("promosyon", "kampanya", "chip-para", "emekliye", "emekli maaş", "emekli promosyon"),
}
# Her durumda elenir: haber değil, sayfa/araç içerikleri
JUNK_TERMS = ("canlı grafik", "hisse senedi canlı", "tradingview", "teknik analiz grafiği")


def financial_score(text: str) -> int:
    low = text.lower()
    return sum(w for term, w in IMPORTANT_TERMS.items() if term in low)


def corporate_topic(text: str) -> Optional[str]:
    low = text.lower()
    return next((topic for topic, terms in CORPORATE_TOPICS.items() if any(t in low for t in terms)), None)


def classify_mention(text: str) -> Optional[str]:
    """'finansal' | kurumsal konu ('promosyon', 'ödül', 'sponsorluk') | None (alınmaz)."""
    if any(j in text.lower() for j in JUNK_TERMS):
        return None
    fin, topic = financial_score(text), corporate_topic(text)
    if fin >= MIN_IMPORTANCE and not (topic and fin < 3):   # promosyon haberindeki "milyar" finansal saymaz
        return "finansal"
    return topic


def _norm_title(t: str) -> str:
    return re.sub(r"\W+", "", t.lower())[:70]


def short_headline(title: str, limit: int = 100) -> str:
    """Alt başlık eklenmiş uzun başlıkları ilk cümle sonunda, yoksa kelime sınırında kısaltır."""
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) <= limit:
        return title
    m = re.search(r"^(.{25,%d}?[!?.])\s" % limit, title)
    if m:
        return m.group(1)
    return title[:limit].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


def _trusted(outlet: str) -> bool:
    """Yayın adı güvenilir listede mi? Kısa adlar (AA, DHA, İHA) tam eşleşme, diğerleri önek eşleşmesi."""
    o = outlet.lower().strip()
    return any(o == t if len(t) <= 3 else o.startswith(t) for t in TRUSTED_OUTLETS)


def fetch_press_mentions(bank: str, today: date) -> List[dict]:
    """Google Haberler araması: son günlerde bankanın adının başlıkta geçtiği finansal veya kurumsal haberler."""
    import feedparser
    from urllib.parse import urlencode

    query, names, _ = BANK_QUERIES[bank]
    url = f"{GOOGLE_NEWS_RSS}?" + urlencode({"q": f"{query} when:{MENTION_WINDOW_DAYS}d", "hl": "tr", "gl": "TR",
                                            "ceid": "TR:tr"})
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        entries = feedparser.parse(resp.content).entries
    except Exception as exc:  # noqa: BLE001
        log.warning("%s basın taraması yapılamadı: %s", bank, exc)
        return []
    out = []
    for e in entries:
        outlet = (e.get("source") or {}).get("title", "")
        title = re.sub(rf"\s+-\s+{re.escape(outlet)}\s*$", "", e.get("title", "")).strip() if outlet else e.get("title", "")
        low = title.lower()
        parsed = e.get("published_parsed")
        published = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(TR_TZ).date() if parsed else None
        if (not published or (today - published).days > MENTION_WINDOW_DAYS or published > today
                or not any(n in low for n in names)          # banka adı başlıkta geçmeli
                or low.startswith("kap ***")                  # KAP kopyaları: KAP'tan doğrudan alınır
                or not _trusted(outlet)):
            continue
        category = classify_mention(title)
        if category is None:
            continue
        out.append({"headline": short_headline(title), "url": e.get("link"), "source": outlet,
                    "published": published.isoformat(), "category": category})
    return out


def kap_mentions(bank: str, records: List[dict], today: date) -> List[dict]:
    """KAP önbelleğindeki bu bankaya ait, rutin olmayan bildirimler."""
    from agents.kap_source import KAP_DISCLOSURE_URL, NOISE_SUBJECTS, parse_publish_date

    title_part = BANK_QUERIES[bank][2]
    out = []
    for r in records:
        if title_part not in (r.get("title") or "").upper():
            continue
        subject = (r.get("subject") or "").strip()
        if any(n in subject.lower() + " " for n in NOISE_SUBJECTS):
            continue
        published = parse_publish_date(r.get("publishDate", ""))
        if not published:
            continue
        d = published.astimezone(TR_TZ).date()
        if (today - d).days > MENTION_WINDOW_DAYS or d > today:
            continue
        detail = re.sub(r"\s+", " ", r.get("summary") or "").strip()
        out.append({"headline": f"{subject}{': ' + detail if detail else ''}", "source": "KAP", "published": d.isoformat(),
                    "url": KAP_DISCLOSURE_URL.format(index=r.get("disclosureIndex")), "category": "finansal"})
    return out


def load_kap_records(output_dir: Path, today: date) -> List[dict]:
    recs: List[dict] = []
    for i in range(MENTION_WINDOW_DAYS + 1):
        f = output_dir / "_kap_cache" / f"{(today - timedelta(days=i)).isoformat()}.json"
        if f.exists():
            try:
                recs += json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return recs


def own_site_corporate(bank: str, own_items: List[BankNews], today: date) -> List[dict]:
    """Bankanın kendi sitesinde son günlerde yayımlanan ödül/sponsorluk/promosyon duyuruları."""
    out = []
    for i in own_items:
        if (today - i.published).days > MENTION_WINDOW_DAYS or i.published > today:
            continue
        topic = corporate_topic(f"{i.title} {i.summary}")
        if topic and financial_score(i.title) < MIN_IMPORTANCE:
            out.append({"headline": i.title, "url": i.url, "source": f"{bank} sitesi",
                        "published": i.published.isoformat(), "category": topic})
    return out


def collect_mentions(bank: str, today: date, kap_records: List[dict], own_items: List[BankNews],
                     press: bool = True) -> List[dict]:
    """KAP + basın + kendi sitesindeki kurumsal duyurular; tekilleştirilmiş, en yeniden eskiye.

    Finansal haberler en fazla MAX_MENTIONS; promosyon/ödül/sponsorluk konu başına en yeni 1 haber,
    toplam en fazla MAX_CORPORATE. Bankanın sitesindeki "son önemli duyuru" tekrar edilmez.
    """
    seen = {_norm_title(i.title) for i in own_items
            if financial_score(i.title) >= MIN_IMPORTANCE}          # finansal duyurular zaten satırın başında
    items = (kap_mentions(bank, kap_records, today) + (fetch_press_mentions(bank, today) if press else [])
             + own_site_corporate(bank, own_items, today))
    financial, corporate, topics_used = [], [], set()
    for m in sorted(items, key=lambda m: (m["published"], m["source"] == "KAP"), reverse=True):
        key = _norm_title(m["headline"])
        if key in seen:
            continue
        seen.add(key)
        if m["category"] == "finansal":
            if len(financial) < MAX_MENTIONS:
                financial.append(m)
        elif m["category"] not in topics_used and len(corporate) < MAX_CORPORATE:
            topics_used.add(m["category"])
            corporate.append(m)
    return financial + corporate


def fetch_bank_watch(pages: Optional[List[BankPage]] = None, today: Optional[date] = None,
                     enrich: bool = True, mentions: bool = True,
                     kap_records: Optional[List[dict]] = None) -> List[dict]:
    """"4 Büyük Banka" bölümü: her banka için en son finansal açıdan önemli haber (tarihi ne olursa olsun).

    Önceki iş gününden bu yana yayımlananlar `is_new=True` olarak işaretlenir. Sayfası okunamayan banka
    `status="unavailable"`, önemli haberi olmayan banka `status="none"` ile yine listelenir.
    """
    pages = pages or DEFAULT_PAGES
    today = today or datetime.now(TR_TZ).date()
    since = previous_business_day(today)
    out = []
    for page in pages:
        items = page_items(page)
        row = {"bank": page.bank, "page_url": page.url, "status": "ok", "headline": None, "url": None,
               "published": None, "summary": "", "is_new": False, "mentions": []}
        if items is None:
            row["status"] = "unavailable"
        else:
            important = sorted((i for i in items if i.published <= today and importance(i) >= MIN_IMPORTANCE),
                               key=lambda i: i.published, reverse=True)
            if not important:
                row["status"] = "none"
            else:
                top = important[0]
                if enrich and not top.summary:
                    top.summary = fetch_description(top.url)
                row.update(headline=top.title, url=top.url, published=top.published.isoformat(),
                           summary=top.summary, is_new=top.published >= since)
        if mentions and page.bank in BANK_QUERIES:
            row["mentions"] = collect_mentions(page.bank, today, kap_records or [], items or [])
        out.append(row)
    return out


def fetch_bank_news(pages: Optional[List[BankPage]] = None, today: Optional[date] = None,
                    enrich: bool = True, all_items: bool = False, important_only: bool = True) -> List[BankNews]:
    """Bankaların bugün ve önceki iş gününden bu yana yayımladığı haberler.

    Banka sayfalarında yalnızca tarih (saat yok) bulunduğundan pencere gün bazındadır.
    """
    pages = pages or DEFAULT_PAGES
    today = today or datetime.now(TR_TZ).date()
    since = previous_business_day(today)
    out: List[BankNews] = []
    for page in pages:
        items = page_items(page)
        if items is None:
            continue
        fresh = items if all_items else [i for i in items if since <= i.published <= today]
        log.info("%s: %d haberden %d tanesi %s sonrası", page.bank, len(items), len(fresh), since)
        for item in fresh:
            if enrich and not item.summary:
                item.summary = fetch_description(item.url)
        if important_only:
            dropped = [i.title for i in fresh if importance(i) < MIN_IMPORTANCE]
            fresh = [i for i in fresh if importance(i) >= MIN_IMPORTANCE]
            if dropped:
                log.info("%s: önemsiz bulunan %d haber elendi: %s", page.bank, len(dropped), "; ".join(dropped)[:200])
        out += fresh
    return out


def to_raw_news(items: List[BankNews]):
    from agents.data_agent import RawNews

    return [RawNews(title=i.title, summary=i.summary or i.title, source=i.bank, url=i.url,
                    published=datetime.combine(i.published, datetime.min.time(), tzinfo=TR_TZ)
                    .astimezone(timezone.utc))
            for i in items]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Banka basın bültenleri")
    ap.add_argument("--all", action="store_true", help="Tarih filtresi olmadan haberler")
    ap.add_argument("--include-minor", action="store_true", help="Önem filtresini kapat")
    args = ap.parse_args()
    for n in fetch_bank_news(all_items=args.all, enrich=not args.all, important_only=not args.include_minor):
        print(f"{n.published:%d.%m.%Y} | {n.bank:12} | önem {importance(n):2} | {n.title[:85]}\n    {n.url}")
