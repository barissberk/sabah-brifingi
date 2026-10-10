"""Banka haberleri: farklı sayfa yapılarından kart çıkarımı, önem filtresi, tarih penceresi, bülten bölümü."""
from __future__ import annotations

from datetime import date

from agents import bank_news
from agents.bank_news import BankNews, extract_items

# Garanti tipi: başlık düz paragraf, tarih ayrı, "Detaylı Bilgi" linki (aynı link iki kez)
GARANTI_HTML = """<ul><li class="item"><div class="card"><a href="/kurumsal/tahvil"><img></a>
<div class="body"><p class="title">Banka'dan 125 milyon ABD Doları Tutarında Tahvil İhracı</p>
<p>Banka uluslararası piyasalarda 10 yıl vadeli sermaye benzeri tahvil ihracını tamamladı ve yoğun talep gördü.</p>
<div class="footer"><p class="date">28 Eylül 2026</p><a href="/kurumsal/tahvil">Detaylı Bilgi</a></div></div></div></li>
<li class="item"><div class="card"><div class="body"><p class="title">Genç Konserleri 2026 Başlıyor</p>
<div class="footer"><p class="date">25 Eylül 2026</p><a href="/kurumsal/konser">Detaylı Bilgi</a></div></div></div></li></ul>"""

# Yapı Kredi tipi: PDF linkli haber öğesi, sayısal tarih
YKB_HTML = """<div class="news"><div class="news-item"><a href="/medium/file/kaynak.pdf/download">YAPI KREDİ’YE 1,1 MİLYAR DOLARLIK SENDİKASYON KREDİSİ.pdf</a>
<p class="news-date"><a>04.06.2026</a></p><p>Yapı Kredi, 20 ülkeden 40 bankanın katılımıyla sendikasyon kredisini başarıyla yeniledi ve kaynak sağladı.</p></div></div>"""

# QNB tipi: tarih + başlık listesi; aynı haberin farklı belge linkleriyle kopyaları
QNB_HTML = """<ul class="table-date-group">
<li><span>29.01.2026</span><a href="/medium/doc-1.vsf">QNB Türkiye’den 500 milyon ABD doları Tutarında Eurobond İhracı</a></li>
<li><span>29.01.2026</span><a href="/medium/doc-2.vsf">QNB Türkiye’den 500 milyon ABD doları Tutarında Eurobond İhracı</a></li>
<li><span>02.05.2026</span><a href="/medium/doc-3.vsf">Kristal Kule Maviye Büründü: Farkındalık Etkinliği</a></li></ul>"""


def test_extract_garanti_style_cards():
    items = extract_items(GARANTI_HTML, "https://bank.test/kurumsal/haberler", "Garanti BBVA")
    assert [i.title for i in items][0] == "Banka'dan 125 milyon ABD Doları Tutarında Tahvil İhracı"
    assert items[0].published == date(2026, 9, 28)
    assert items[0].url == "https://bank.test/kurumsal/tahvil"
    assert "sermaye benzeri" in items[0].summary


def test_extract_ykb_style_pdf_items():
    items = extract_items(YKB_HTML, "https://ykb.test/basin-bultenleri", "Yapı Kredi")
    assert len(items) == 1
    assert items[0].title.endswith("SENDİKASYON KREDİSİ")          # .pdf uzantısı temizlendi
    assert items[0].published == date(2026, 6, 4)


def test_extract_qnb_style_list_dedups_copies():
    items = extract_items(QNB_HTML, "https://qnb.test/basin-bultenleri", "QNB")
    titles = [i.title for i in items]
    assert titles.count("QNB Türkiye’den 500 milyon ABD doları Tutarında Eurobond İhracı") == 1
    assert len(items) == 2


def test_importance_keeps_financial_drops_events():
    tahvil = BankNews("X", "125 milyon ABD Doları Tutarında Tahvil İhracı", date(2026, 9, 28), "u")
    konser = BankNews("X", "Genç Konserleri 2026 Başlıyor", date(2026, 9, 25), "u")
    farkindalik = BankNews("X", "Kristal Kule Maviye Büründü: Farkındalık Etkinliği", date(2026, 5, 2), "u")
    assert bank_news.importance(tahvil) >= bank_news.MIN_IMPORTANCE
    assert bank_news.importance(konser) < bank_news.MIN_IMPORTANCE
    assert bank_news.importance(farkindalik) < bank_news.MIN_IMPORTANCE


def test_window_is_previous_business_day(monkeypatch):
    class Resp:
        status_code = 200
        headers = {"content-type": "text/html"}
        text = """<ul class="g"><li><span>09.10.2026</span><a href="/a">Bugünkü Eurobond İhracı tamamlandı</a></li>
                  <li><span>08.10.2026</span><a href="/b">Dünkü sendikasyon kredisi yenilendi</a></li>
                  <li><span>01.10.2026</span><a href="/c">Geçen haftaki tahvil ihracı</a></li></ul>"""

        def raise_for_status(self):
            pass

    monkeypatch.setattr(bank_news.requests, "get", lambda *a, **k: Resp())
    pages = [bank_news.BankPage("QNB", "https://qnb.test/liste")]
    out = bank_news.fetch_bank_news(pages, today=date(2026, 10, 9), enrich=False)   # Cuma
    assert sorted(i.url.rsplit("/", 1)[1] for i in out) == ["a", "b"]
    monday = bank_news.fetch_bank_news(pages, today=date(2026, 10, 12), enrich=False)  # Pazartesi → Cuma'dan beri
    assert [i.url.rsplit("/", 1)[1] for i in monday] == ["a"]


def test_one_bank_failure_does_not_stop_others(monkeypatch):
    def fake_get(url, **k):
        if "kotu" in url:
            raise ConnectionError("down")

        class R:
            status_code = 200
            headers = {"content-type": "text/html"}
            text = '<ul><li><span>09.10.2026</span><a href="/x">Eurobond ihracı tamamlandı</a></li></ul>'

            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(bank_news.requests, "get", fake_get)
    pages = [bank_news.BankPage("A", "https://kotu.test/l"), bank_news.BankPage("B", "https://iyi.test/l")]
    out = bank_news.fetch_bank_news(pages, today=date(2026, 10, 9), enrich=False)
    assert [i.bank for i in out] == ["B"]


def test_bank_watch_latest_important_per_bank(monkeypatch):
    html = {
        "https://a.test/l": """<ul><li><span>09.10.2026</span><a href="/k">Kariyer programı başvuruları açıldı</a></li>
            <li><span>28.09.2026</span><a href="/t">125 milyon dolarlık tahvil ihracı tamamlandı</a></li>
            <li><span>01.07.2026</span><a href="/s">Sendikasyon kredisi yenilendi</a></li></ul>""",
        "https://b.test/l": """<ul><li><span>09.10.2026</span><a href="/e">500 milyon dolarlık eurobond ihracı</a></li></ul>""",
        "https://c.test/l": """<ul><li><span>01.10.2026</span><a href="/x">Sanat sergisi açıldı</a></li></ul>""",
    }

    def fake_get(url, **k):
        if url not in html:
            raise ConnectionError("down")

        class R:
            status_code = 200
            headers = {"content-type": "text/html"}
            text = html[url]

            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(bank_news.requests, "get", fake_get)
    pages = [bank_news.BankPage(n, u) for n, u in
             [("A", "https://a.test/l"), ("B", "https://b.test/l"), ("C", "https://c.test/l"), ("D", "https://d.test/l")]]
    rows = {r["bank"]: r for r in bank_news.fetch_bank_watch(pages, today=date(2026, 10, 9), enrich=False)}
    assert rows["A"]["url"].endswith("/t") and rows["A"]["is_new"] is False   # en son ÖNEMLİ haber, eski
    assert rows["B"]["is_new"] is True and rows["B"]["published"] == "2026-10-09"
    assert rows["C"]["status"] == "none"                                        # yalnızca önemsiz haber
    assert rows["D"]["status"] == "unavailable"                                 # sayfa okunamadı


# --- Diğer kaynaklar: basın + KAP -------------------------------------------
GNEWS_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Garanti BBVA, 100 milyar TL VDMK ihraç tavanı belirledi - Investing.com Türkiye</title>
 <link>https://news.test/1</link><pubDate>Fri, 09 Oct 2026 07:47:00 GMT</pubDate><source url="x">Investing.com Türkiye</source></item>
<item><title>Garanti BBVA Emeklilik iki ödüle layık görüldü - Saray Medya</title>
 <link>https://news.test/2</link><pubDate>Fri, 09 Oct 2026 03:58:00 GMT</pubDate><source url="x">Saray Medya</source></item>
<item><title>Garanti BBVA emekli promosyonu ne kadar? - Milliyet</title>
 <link>https://news.test/3</link><pubDate>Fri, 09 Oct 2026 09:00:00 GMT</pubDate><source url="x">Milliyet</source></item>
<item><title>Borsada günün en çok yükselenleri: 2 milyar TL hacim - Dünya</title>
 <link>https://news.test/4</link><pubDate>Fri, 09 Oct 2026 09:00:00 GMT</pubDate><source url="x">Dünya</source></item>
<item><title>KAP *** GARANTİ BANKASI *** İhraç Tavanına İlişkin Bildirim - GZT</title>
 <link>https://news.test/5</link><pubDate>Fri, 09 Oct 2026 09:00:00 GMT</pubDate><source url="x">GZT</source></item>
<item><title>Garanti BBVA tahvil ihracını tamamladı - Dünya</title>
 <link>https://news.test/6</link><pubDate>Thu, 01 Oct 2026 09:00:00 GMT</pubDate><source url="x">Dünya</source></item>
</channel></rss>"""


def test_trusted_outlets():
    assert bank_news._trusted("Investing.com Türkiye") and bank_news._trusted("Anadolu Ajansı")
    assert bank_news._trusted("AA") and not bank_news._trusted("AAA Haber")
    assert not bank_news._trusted("Doğubayazıt Gazetesi") and not bank_news._trusted("Saray Medya")


def test_press_mentions_filters_noise(monkeypatch):
    class R:
        status_code = 200
        content = GNEWS_RSS.encode()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(bank_news.requests, "get", lambda *a, **k: R())
    out = bank_news.fetch_press_mentions("Garanti BBVA", date(2026, 10, 10))
    # güvenilir yayın + başlıkta banka adı + pencere içinde + KAP kopyası değil; finansal veya kurumsal
    got = {m["headline"]: m["category"] for m in out}
    assert got == {"Garanti BBVA, 100 milyar TL VDMK ihraç tavanı belirledi": "finansal",
                   "Garanti BBVA emekli promosyonu ne kadar?": "promosyon"}        # Milliyet: güvenilir
    assert "Garanti BBVA Emeklilik iki ödüle layık görüldü" not in got              # Saray Medya: güvenilir değil


def test_kap_mentions_and_dedup(monkeypatch):
    records = [
        {"disclosureIndex": 1, "title": "YAPI VE KREDİ BANKASI A.Ş.", "subject": "Özel Durum Açıklaması (Genel)",
         "summary": "Sendikasyon kredisi", "publishDate": "09.10.2026 18:00:00"},
        {"disclosureIndex": 2, "title": "YAPI VE KREDİ BANKASI A.Ş.", "subject": "Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim",
         "summary": "", "publishDate": "09.10.2026 18:00:00"},                                   # rutin → elenir
        {"disclosureIndex": 3, "title": "AKBANK T.A.Ş.", "subject": "Özel Durum Açıklaması (Genel)",
         "summary": "x", "publishDate": "09.10.2026 18:00:00"},                                  # başka banka
    ]
    monkeypatch.setattr(bank_news, "fetch_press_mentions", lambda bank, today: [
        {"headline": "Özel Durum Açıklaması (Genel): Sendikasyon kredisi", "source": "Dünya", "url": "u",
         "published": "2026-10-09"}])                                                            # KAP'la aynı → tekrar edilmez
    out = bank_news.collect_mentions("Yapı Kredi", date(2026, 10, 10), records, own_items=[])
    assert len(out) == 1 and out[0]["source"] == "KAP" and out[0]["url"].endswith("/1")


def test_classify_mention_topics():
    c = bank_news.classify_mention
    assert c("Garanti BBVA Emeklilik'e Smart-i Awards 2026'da iki ödül") == "ödül"       # "Emeklilik" ≠ promosyon
    assert c("Akbank emekli maaş promosyon tutarları") == "promosyon"
    assert c("Yapı Kredi sponsorluğunda caz festivali") == "sponsorluk"
    assert c("Garanti BBVA Emeklilik fon büyüklüğü 50 milyar TL'yi aştı") == "finansal"
    assert c("AKBANK Hisse Senedi Canlı Grafik") is None
    assert c("QNB Türkiye Trabzon'da reel sektörle buluştu") is None


def test_corporate_mentions_one_per_topic(monkeypatch):
    press = [
        {"headline": f"Akbank emekli promosyonu {i}", "source": "Milliyet", "url": f"u{i}",
         "published": f"2026-10-0{i}", "category": "promosyon"} for i in (7, 8, 9)
    ] + [
        {"headline": "Akbank'a ödül", "source": "AA", "url": "o", "published": "2026-10-08", "category": "ödül"},
        {"headline": "Akbank tahvil ihracı", "source": "Dünya", "url": "t", "published": "2026-10-08",
         "category": "finansal"},
    ]
    monkeypatch.setattr(bank_news, "fetch_press_mentions", lambda bank, today: press)
    own = [BankNews("Akbank", "Akbank Caz Festivali sponsorluğu başladı", date(2026, 10, 9), "s")]
    out = bank_news.collect_mentions("Akbank", date(2026, 10, 10), [], own_items=own)
    fin = [m for m in out if m["category"] == "finansal"]
    corp = [m for m in out if m["category"] != "finansal"]
    assert [m["headline"] for m in fin] == ["Akbank tahvil ihracı"]
    assert len(corp) == 2 and len({m["category"] for m in corp}) == 2                   # konu başına 1, en fazla 2
    by_topic = {m["category"]: m for m in corp}
    assert by_topic["sponsorluk"]["source"] == "Akbank sitesi"                           # kendi sitesinden
    assert by_topic["promosyon"]["published"] == "2026-10-09"                           # konunun en yeni haberi


def test_short_headline():
    long = ("Akbank emekli maaş promosyon tutarları! 1-31 Ekim Akbank emekli maaş promosyonu ne kadar? "
            "İşte maaş tutarlarına göre güncel rakamlar...")
    assert bank_news.short_headline(long) == "Akbank emekli maaş promosyon tutarları!"
    assert bank_news.short_headline("Kısa başlık") == "Kısa başlık"
    no_stop = "Garanti BBVA " + "çok uzun başlık " * 10
    out = bank_news.short_headline(no_stop)
    assert out.endswith("…") and len(out) <= 101


def test_press_falls_back_to_bing_when_google_unavailable(monkeypatch):
    bing = """<?xml version="1.0"?><rss xmlns:News="https://www.bing.com/news/search?q=x&amp;format=rss"><channel>
    <item><title>Akbank, 50 milyon Euro tahvil ihraç edecek</title><link>https://bing.test/1</link>
     <pubDate>Fri, 09 Oct 2026 07:00:00 GMT</pubDate><News:Source>Investing.com Türkiye</News:Source></item>
    </channel></rss>"""

    def fake_get(url, **k):
        class R:
            status_code = 200
            content = bing.encode()

            def raise_for_status(self):
                if "news.google.com" in url:
                    raise ConnectionError("503 Service Unavailable")
        return R()

    monkeypatch.setattr(bank_news.requests, "get", fake_get)
    out = bank_news.fetch_press_mentions("Akbank", date(2026, 10, 10))
    assert [(m["headline"], m["source"]) for m in out] == [("Akbank, 50 milyon Euro tahvil ihraç edecek",
                                                             "Investing.com Türkiye")]
