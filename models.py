"""Ajanlar arası veri sözleşmesi (Ajan 1 JSON çıktısının şeması)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr

# Sadece bu kaynaklardan gelen haberler bültene girer.
TIER1_SOURCES = {"Bloomberg", "Bloomberg HT", "Reuters", "Foreks", "KAP", "TCMB"}
# Bankaların kendi kurumsal haberleri: kendileri hakkında birincil kaynak
BANK_SOURCES = {"Garanti BBVA", "Akbank", "Yapı Kredi", "QNB"}
TIER1_SOURCES |= BANK_SOURCES


class MarketIndicator(BaseModel):
    key: str = Field(description="bist100 | usdtry | brent | gold")
    label: str
    value: Optional[float] = None
    change_pct: Optional[float] = None
    unit: str = ""
    decimals: int = 2
    source: str = ""

    @property
    def direction(self) -> str:
        if self.change_pct is None or self.change_pct == 0:
            return "flat"
        return "up" if self.change_pct > 0 else "down"


class NewsItem(BaseModel):
    headline: str
    summary: str
    source: str
    url: Optional[str] = None
    published_at: Optional[str] = None
    impact: Literal["high", "medium", "low"] = "medium"


class CalendarEvent(BaseModel):
    time: str = Field(description="HH:MM, Türkiye saati")
    country: str = Field(description="ISO ülke kodu, ör. TR, US, EZ")
    event: str
    importance: Literal["high", "medium", "low"] = "medium"
    forecast: Optional[str] = None
    previous: Optional[str] = None


class BankMention(BaseModel):
    """Bankayla ilgili diğer kaynaklardaki haber (basın veya KAP)."""
    headline: str
    source: str
    url: Optional[str] = None
    published: Optional[str] = None      # YYYY-MM-DD
    category: str = "finansal"           # finansal | promosyon | ödül | sponsorluk


class BankWatchItem(BaseModel):
    """"4 Büyük Banka" bölümü: bankanın en son finansal açıdan önemli duyurusu."""
    bank: str
    status: Literal["ok", "none", "unavailable"] = "ok"
    headline: Optional[str] = None
    url: Optional[str] = None
    published: Optional[str] = None      # YYYY-MM-DD
    summary: str = ""
    is_new: bool = False
    page_url: Optional[str] = None
    mentions: List[BankMention] = []     # son günlerde basında ve KAP'ta


class Briefing(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    generated_at: str
    markets: List[MarketIndicator]
    executive_summary: List[str] = Field(description="3-5 madde, her biri tek cümle")
    global_developments: List[NewsItem]
    turkey_agenda: List[NewsItem]
    economic_calendar: List[CalendarEvent]
    banking_agenda: List[NewsItem] = []
    bank_watch: List[BankWatchItem] = []
    sources: List[str] = []
    unverified_figures: List[str] = []    # kaynakta doğrulanamayan rakamlar (yapay zekâ denetimi)


class CuratedContent(BaseModel):
    """LLM'in ürettiği editoryal kısım (piyasa verileri kod tarafında eklenir)."""

    executive_summary: List[str]
    global_developments: List[NewsItem]
    turkey_agenda: List[NewsItem]
    economic_calendar: List[CalendarEvent]
    banking_agenda: List[NewsItem] = Field(default_factory=list,
                                           description="Bankaların kendi kurumsal haberleri (Bankacılık Gündemi)")
    # Kod tarafından doldurulur (yapay zekâ denetimi); şemada yer almaz, modelden istenmez
    _unverified: List[str] = PrivateAttr(default_factory=list)
