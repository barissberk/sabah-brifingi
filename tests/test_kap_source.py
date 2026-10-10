"""KAP kaynağı: gürültü eleme, puanlama, zaman penceresi, gece kopyası ve hata toleransı."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from agents import kap_source
from config import Settings

NOW = datetime(2026, 10, 9, 4, 30, tzinfo=timezone.utc)          # 07:30 TR
CUTOFF = datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)      # 18 saat öncesi


def rec(idx, subject, summary, title="ÖRNEK HOLDİNG A.Ş.", when="09.10.2026 06:00:00"):
    return {"disclosureIndex": idx, "subject": subject, "summary": summary, "title": title, "publishDate": when}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.output_dir = tmp_path / "output"
    s.kap_watchlist_path = tmp_path / "watch.txt"
    s.kap_max_items = 8
    return s


def test_noise_subjects_are_dropped():
    assert kap_source.score(rec(1, "Aracı Kuruma Ödenen Komisyon ve Varlık Alım Satım Bilgileri", "x")) == 0
    assert kap_source.score(rec(2, "Fon Sürekli Bilgilendirme Formu", "x")) == 0
    assert kap_source.score(rec(3, "Pay Bazında Devre Kesici Bildirimi", "x")) == 0


def test_important_and_unknown_subjects_are_scored():
    assert kap_source.score(rec(1, "Kâr Payı Dağıtım İşlemlerine İlişkin Bildirim", "2025 temettü")) >= 5
    # Listede olmayan konu: içerikteki güçlü ifadeler ile seçilebilir
    assert kap_source.score(rec(2, "Bilinmeyen Yeni Konu", "500 milyon dolarlık ihale sözleşmesi")) >= kap_source.MIN_SCORE
    # Rutin özel durum (YK üye değişikliği) eşiğin altında kalır
    assert kap_source.score(rec(3, "Özel Durum Açıklaması (Genel)", "Yönetim Kurulu Üye Değişiklikleri")) < kap_source.MIN_SCORE


def test_watchlist_boost():
    r = rec(1, "Genel Açıklama", "bilgilendirme", title="QNB BANK A.Ş.")
    assert kap_source.score(r, ["QNB"]) == kap_source.score(r) + 3


def test_select_respects_window_dedup_and_order():
    records = [
        rec(1, "Birleşme İşlemlerine İlişkin Bildirim", "birleşme", when="09.10.2026 06:00:00"),
        rec(1, "Birleşme İşlemlerine İlişkin Bildirim", "birleşme", when="09.10.2026 06:00:00"),   # tekrar
        rec(2, "Kredi Derecelendirmesi", "kredi notu", when="08.10.2026 20:00:00"),
        rec(3, "Kredi Derecelendirmesi", "kredi notu", when="07.10.2026 10:00:00"),               # pencere dışı
    ]
    out = kap_source.select(records, NOW, CUTOFF)
    assert [r["disclosureIndex"] for r in out] == [1, 2]


def test_short_company():
    assert kap_source.short_company("BRİSA BRİDGESTONE SABANCI LASTİK SANAYİ VE TİCARET A.Ş.") == \
        "BRİSA BRİDGESTONE SABANCI LASTİK"


def test_morning_run_uses_previous_evening_snapshot(settings):
    # Önceki akşamın kopyası (canlı servis sabah yalnızca yeni günü döndürür)
    kap_source.snapshot(settings, raw=[rec(10, "Pay Satın Alma Teklifi", "çağrı", when="08.10.2026 21:00:00")],
                        today=date(2026, 10, 8))
    live = [rec(11, "Sermaye Artırımı - Azaltımı İşlemlerine İlişkin Bildirim", "bedelsiz", when="09.10.2026 07:00:00")]
    news = kap_source.fetch_kap_news(settings, now=NOW, cutoff=CUTOFF, raw_today=live)
    assert {n.url.rsplit("/", 1)[1] for n in news} == {"10", "11"}
    assert all(n.source == "KAP" for n in news)


def test_kap_failure_falls_back_to_cache(settings, monkeypatch):
    kap_source.snapshot(settings, raw=[rec(20, "Pay Satın Alma Teklifi", "çağrı", when="08.10.2026 21:00:00")],
                        today=date(2026, 10, 8))
    monkeypatch.setattr(kap_source, "fetch_raw", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    news = kap_source.fetch_kap_news(settings, now=NOW, cutoff=CUTOFF)
    assert [n.url.rsplit("/", 1)[1] for n in news] == ["20"]
