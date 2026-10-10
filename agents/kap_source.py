"""KAP (Kamuyu Aydınlatma Platformu) bildirim kaynağı.

KAP'ın resmi bir RSS'i veya açık API'si yoktur. Bu modül, kap.org.tr sitesinin kendi
sayfaları için kullandığı (belgelenmemiş) bildirim listesi servisini okur:
  - Günde en fazla birkaç istek atılır (gece kopyası + sabah çalışması).
  - Servis yanıt vermez veya biçim değişirse hata fırlatılmaz; bülten KAP'sız çıkar.

Servis yalnızca *o günün* bildirimlerini döndürür. 07:30'daki çalışma önceki akşamı da
kapsayabilsin diye `snapshot()` her gece çalıştırılıp liste `output/_kap_cache/` altına
kaydedilir; `fetch_kap_news()` canlı listeyi önceki günlerin kopyalarıyla birleştirir.

Bağımsız çalıştırma:
    python -m agents.kap_source            # süzülmüş bildirimleri listeler
    python -m agents.kap_source --snapshot # gece kopyası alır
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

from config import Settings, get_settings

log = logging.getLogger("agent1.kap")

KAP_LIST_URL = "https://www.kap.org.tr/tr/api/disclosure/list/light"
KAP_DISCLOSURE_URL = "https://www.kap.org.tr/tr/Bildirim/{index}"
TR_TZ = timezone(timedelta(hours=3))
HTTP_TIMEOUT = 20

# Bülten için önemli bildirim konuları ve ağırlıkları
SUBJECT_WEIGHTS: Dict[str, int] = {
    "Özel Durum Açıklaması (Genel)": 3,
    "Finansal Rapor": 5,
    "Kâr Payı Dağıtım İşlemlerine İlişkin Bildirim": 5,
    "Kar Payı Dağıtım İşlemlerine İlişkin Bildirim": 5,
    "Sermaye Artırımı - Azaltımı İşlemlerine İlişkin Bildirim": 5,
    "Kredi Derecelendirmesi": 4,
    "Birleşme İşlemlerine İlişkin Bildirim": 6,
    "Bölünme İşlemlerine İlişkin Bildirim": 5,
    "Pay Satın Alma Teklifi": 6,
    "Yeni İş İlişkisi": 4,
    "Maddi Duran Varlık Alımı": 4,
    "Maddi Duran Varlık Satımı": 4,
    "Finansal Duran Varlık Edinimi": 5,
    "Finansal Duran Varlık Satımı": 5,
    "Sözleşme İmzalanması": 4,
    "İhale Süreci / Sonucu": 4,
    "Payların Geri Alınmasına İlişkin Bildirim": 1,
    "Genel Açıklama": 1,
}

# Özette geçerse önemi artıran ifadeler
KEYWORD_BOOST = {
    "ihale": 2, "sözleşme": 2, "satın al": 2, "birleşme": 3, "devral": 2, "temettü": 2, "kâr payı": 2,
    "kar payı": 2, "bedelsiz": 2, "bedelli": 2, "sermaye artırımı": 2, "sipariş": 2, "yatırım karar": 2,
    "kredi notu": 2, "derecelendirme": 1, "iş ilişkisi": 1, "milyon": 1, "milyar": 2, "lisans": 1,
    "ihracat": 1, "kapasite": 1, "satış": 1,
}
# Özette geçerse önemi düşüren rutin konular
KEYWORD_PENALTY = ("yönetim kurulu üye", "genel kurul", "bağımsız denetim kuruluşu", "pay geri alım işlemleri",
                   "imza sirküleri", "merkez değişikliği")
# Bülten için gürültü olan rutin bildirim konuları (alt dize, küçük harf)
NOISE_SUBJECTS = (
    "aracı kuruma ödenen komisyon", "devre kesici", "repo", "fon ", "fon sürekli", "fon toplam", "fon gider",
    "şirket genel bilgi formu", "ihraç tavanı", "ihraç belgesi", "varant", "likidite sağlayıcılık",
    "yatırımcı bilgi formu", "tanıtım formu", "piyasa yapıcılığı", "pay alım satım bildirimi",
    "pay dışında sermaye piyasası aracı", "temerrüt işlemi", "esas sözleşme tadili", "izahname",
    "sorumluluk beyanı", "faaliyet raporu", "kurumsal yönetim", "sürdürülebilirlik",
)
UNKNOWN_SUBJECT_WEIGHT = 1
MIN_SCORE = 3


def _cache_dir(settings: Settings) -> Path:
    path = settings.output_dir / "_kap_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch_raw(session: Optional[requests.Session] = None) -> List[dict]:
    """KAP'tan günün bildirim listesini alır (tek istek)."""
    http = session or requests
    resp = http.get(KAP_LIST_URL, timeout=HTTP_TIMEOUT,
                    headers={"User-Agent": "Mozilla/5.0 MorningBriefing/1.0", "Accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Beklenmeyen KAP yanıt biçimi: {type(data).__name__}")
    return data


def snapshot(settings: Optional[Settings] = None, raw: Optional[List[dict]] = None,
             today: Optional[date] = None) -> Path:
    """Günün listesini önbelleğe yazar; aynı gün içinde birden fazla alınırsa birleştirir."""
    settings = settings or get_settings()
    today = today or datetime.now(TR_TZ).date()
    raw = raw if raw is not None else fetch_raw()
    path = _cache_dir(settings) / f"{today.isoformat()}.json"
    merged = {r["disclosureIndex"]: r for r in _load(path)}
    merged.update({r["disclosureIndex"]: r for r in raw if "disclosureIndex" in r})
    path.write_text(json.dumps(list(merged.values()), ensure_ascii=False), encoding="utf-8")
    log.info("KAP kopyası kaydedildi: %s (%d bildirim)", path.name, len(merged))
    _prune(settings, keep_days=7)
    return path


def _load(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _prune(settings: Settings, keep_days: int) -> None:
    cutoff = datetime.now(TR_TZ).date() - timedelta(days=keep_days)
    for f in _cache_dir(settings).glob("*.json"):
        try:
            if date.fromisoformat(f.stem) < cutoff:
                f.unlink()
        except ValueError:
            continue


def parse_publish_date(value: str) -> Optional[datetime]:
    """'09.10.2026 21:42:09' (TR saati) → UTC datetime"""
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y %H:%M:%S").replace(tzinfo=TR_TZ).astimezone(timezone.utc)
    except (AttributeError, ValueError):
        return None


def short_company(title: str) -> str:
    name = re.sub(r"\s+A\.\s?Ş\.?$", "", (title or "").strip())
    name = re.sub(r"\s+(SANAYİ VE TİCARET|SANAYİ VE TİCARET ANONİM ŞİRKETİ|ANONİM ŞİRKETİ)$", "", name)
    return name


def load_watchlist(settings: Settings) -> List[str]:
    """Öncelikli şirketler (ör. BIST 100 veya müşteri portföyü): satır başına şirket adının bir parçası."""
    path = settings.kap_watchlist_path
    if not path or not Path(path).exists():
        return []
    return [line.strip().upper() for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def score(record: dict, watchlist: Iterable[str] = ()) -> int:
    subject = (record.get("subject") or "").strip()
    summary = (record.get("summary") or "").lower()
    if any(n in subject.lower() + " " for n in NOISE_SUBJECTS):
        return 0                                  # rutin/gürültü konuları tamamen elenir
    # Bilinmeyen bir konu düşük taban puanla değerlendirilir; içerik anahtar kelimeleri yükseltebilir.
    s = SUBJECT_WEIGHTS.get(subject, UNKNOWN_SUBJECT_WEIGHT)
    s += sum(w for k, w in KEYWORD_BOOST.items() if k in summary)
    if any(k in summary for k in KEYWORD_PENALTY):
        s -= 3
    title = (record.get("title") or "").upper()
    if any(w in title for w in watchlist):
        s += 3
    return s


def select(records: List[dict], now: datetime, cutoff: datetime, watchlist: Iterable[str] = (),
           limit: int = 8) -> List[dict]:
    """Zaman penceresindeki önemli bildirimleri puan ve yeniliğe göre sıralar."""
    watchlist = list(watchlist)
    seen, picked = set(), []
    for r in records:
        published = parse_publish_date(r.get("publishDate", ""))
        if published is None or not (cutoff <= published <= now + timedelta(hours=1)):
            continue
        idx = r.get("disclosureIndex")
        if idx in seen:
            continue
        seen.add(idx)
        sc = score(r, watchlist)
        if sc >= MIN_SCORE:
            picked.append((sc, published, r))
    picked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [dict(r, _score=sc, _published=pub) for sc, pub, r in picked[:limit]]


def fetch_kap_news(settings: Settings, now: Optional[datetime] = None, cutoff: Optional[datetime] = None,
                   raw_today: Optional[List[dict]] = None):
    """Canlı liste + son günlerin kopyaları → RawNews listesi. Hata durumunda boş liste."""
    from agents.data_agent import RawNews, news_cutoff

    now = now or datetime.now(timezone.utc)
    cutoff = cutoff or news_cutoff(now, settings.news_lookback_hours)
    try:
        live = raw_today if raw_today is not None else fetch_raw()
        snapshot(settings, raw=live, today=now.astimezone(TR_TZ).date())
    except Exception as exc:  # noqa: BLE001 — KAP bülteni durdurmamalı
        log.warning("KAP canlı listesi alınamadı, yalnızca önbellek kullanılacak: %s", exc)
        live = []

    records: List[dict] = list(live)
    day = cutoff.astimezone(TR_TZ).date()
    while day <= now.astimezone(TR_TZ).date():
        records += _load(_cache_dir(settings) / f"{day.isoformat()}.json")
        day += timedelta(days=1)

    chosen = select(records, now, cutoff, load_watchlist(settings), settings.kap_max_items)
    log.info("KAP: %d bildirimden %d önemli bildirim seçildi", len({r.get('disclosureIndex') for r in records}),
             len(chosen))
    news = []
    for r in chosen:
        company = short_company(r.get("title", ""))
        detail = re.sub(r"\s+", " ", (r.get("summary") or "")).strip()
        subject = r.get("subject", "")
        news.append(RawNews(
            title=f"{company}: {detail or subject}",
            summary=f"KAP bildirimi — {subject}. {detail}".strip(),
            source="KAP",
            url=KAP_DISCLOSURE_URL.format(index=r.get("disclosureIndex")),
            published=r["_published"],
        ))
    return news


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="KAP bildirim kaynağı")
    ap.add_argument("--snapshot", action="store_true", help="Günün listesini önbelleğe kaydet")
    args = ap.parse_args()
    s = get_settings()
    if args.snapshot:
        print(snapshot(s))
    else:
        for n in fetch_kap_news(s):
            print(f"{n.published.astimezone(TR_TZ):%d.%m %H:%M} | {n.title[:110]}\n    {n.url}")
