"""Haber kaynakları: varsayılan liste, site araması (Google → Bing yedeği), başlık temizliği."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agents import data_agent
from config import Settings
from models import TIER1_SOURCES

NOW = datetime(2026, 11, 3, 4, 30, tzinfo=timezone.utc)

GOOGLE_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Altında düşüş sürüyor - Gazete Oksijen</title><link>https://g.test/1</link>
 <pubDate>Tue, 03 Nov 2026 03:00:00 GMT</pubDate><description>Altında düşüş sürüyor Gazete Oksijen</description>
 <source url="https://gazeteoksijen.com">Gazete Oksijen</source></item>
<item><title>Eski haber - Gazete Oksijen</title><link>https://g.test/2</link>
 <pubDate>Fri, 30 Oct 2026 03:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_default_sources_include_new_outlets(monkeypatch):
    monkeypatch.setenv("NEWS_FEEDS", "")
    feeds = dict(Settings().news_feeds) | {}
    names = {n for n, _ in Settings().news_feeds}
    assert {"Investing.com", "Dünya", "Bigpara", "Gazete Oksijen"} <= names <= TIER1_SOURCES
    assert dict(Settings().news_feeds)["Gazete Oksijen"].startswith("gnews:site:gazeteoksijen.com")


def test_search_source_parses_and_cleans(monkeypatch):
    s = Settings()
    s.news_feeds = [("Gazete Oksijen", "gnews:site:gazeteoksijen.com/ekonomi")]
    s.kap_enabled = s.bank_news_enabled = False
    seen = []

    def fake_get(url, **k):
        seen.append(url)

        class R:
            content = GOOGLE_RSS.encode()

            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(data_agent.requests, "get", fake_get)
    news = data_agent.fetch_news(s, now=NOW)
    assert [n.title for n in news] == ["Altında düşüş sürüyor"]          # " - Gazete Oksijen" atıldı, eski elendi
    assert news[0].source == "Gazete Oksijen" and news[0].summary == ""     # özet başlığın tekrarı → boş
    assert "news.google.com" in seen[0] and "site%3Agazeteoksijen.com%2Fekonomi" in seen[0]


def test_search_falls_back_to_bing(monkeypatch):
    s = Settings()
    s.news_feeds = [("Bigpara", "gnews:site:bigpara.hurriyet.com.tr")]
    s.kap_enabled = s.bank_news_enabled = False

    def fake_get(url, **k):
        class R:
            content = GOOGLE_RSS.replace("Gazete Oksijen", "Bigpara").encode()

            def raise_for_status(self):
                if "news.google.com" in url:
                    raise ConnectionError("503")
        return R()

    monkeypatch.setattr(data_agent.requests, "get", fake_get)
    news = data_agent.fetch_news(s, now=NOW)
    assert [n.source for n in news] == ["Bigpara"]


def test_non_finance_sections_are_skipped():
    assert data_agent._excluded_section("https://www.dunya.com/spor/galatasaray-macin-ilk-11leri")
    assert data_agent._excluded_section("https://www.dunya.com/foto-galeri/x")
    assert not data_agent._excluded_section("https://www.dunya.com/ekonomi/abdde-imalat-sanayi")
    assert not data_agent._excluded_section("https://www.dunya.com/finans/haberler/borsa")
    assert not data_agent._excluded_section(None)


def test_verification_accepts_written_out_numbers():
    from agents.data_agent import RawNews, verify_content
    from models import CuratedContent, NewsItem

    news = [RawNews("İhracat rekor", "ihracat 25 milyar 885 milyon dolara ulaştı; 2 bin 285 MW kapasite", "Foreks",
                    "https://k.test/1", None)]
    content = CuratedContent(
        executive_summary=["İhracat 25,885 milyar dolar; 2.285 MW kapasite; enflasyon %31"],
        global_developments=[], turkey_agenda=[], economic_calendar=[], banking_agenda=[])
    assert verify_content(content, news, []) == ["31"]                     # yalnızca kaynakta olmayan rakam
