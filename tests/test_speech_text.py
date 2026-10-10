"""Seslendirme normalizasyonu: her değer birimiyle, rakamlar kelimeyle okunmalı."""
from agents.speech_text import int_to_words, normalize_for_speech, number_to_words, spoken_market_sentence
from models import MarketIndicator


def test_int_to_words():
    assert int_to_words(0) == "sıfır"
    assert int_to_words(100) == "yüz"
    assert int_to_words(1000) == "bin"
    assert int_to_words(3982) == "üç bin dokuz yüz seksen iki"
    assert int_to_words(10842) == "on bin sekiz yüz kırk iki"
    assert int_to_words(1250000) == "bir milyon iki yüz elli bin"


def test_decimals():
    assert number_to_words("3.982,40") == "üç bin dokuz yüz seksen iki virgül kırk"
    assert number_to_words("4,05") == "dört virgül sıfır beş"
    assert number_to_words("41,9725") == "kırk bir virgül doksan yedi yirmi beş"


def test_normalize_symbols_and_suffixes():
    assert normalize_for_speech("[MOCK] BIST 100 %1,2 yükseldi") == "Bist yüz yüzde bir virgül iki yükseldi"
    assert normalize_for_speech("saat 17:00'de, 14:30'da") == "saat on yedide, on dört otuzda"
    assert normalize_for_speech("$66,84") == "altmış altı virgül seksen dört dolar"
    assert "Türkiye'nin" in normalize_for_speech("Türkiye'nin CDS primi")
    assert not any(ch.isdigit() for ch in normalize_for_speech("TCMB 270 bps, OPEC+ 67 dolar"))


def test_market_sentence_has_units_for_every_value():
    markets = [
        MarketIndicator(key="bist100", label="BIST 100", value=10842.37, change_pct=1.18),
        MarketIndicator(key="usdtry", label="USD/TRY", value=41.9725, change_pct=0.12, decimals=4),
        MarketIndicator(key="cds", label="CDS", value=268, change_pct=-2.15, unit="bps"),
        MarketIndicator(key="brent", label="Brent", value=66.84, change_pct=-0.87, unit="$"),
        MarketIndicator(key="gold", label="Ons Altın", value=3982.40, change_pct=0.54, unit="$"),
    ]
    spoken = normalize_for_speech(spoken_market_sentence(markets))
    assert "on bin sekiz yüz kırk iki puandan kapandı." in spoken
    assert "kırk bir lira doksan yedi kuruştan" in spoken
    assert "iki yüz altmış sekiz baz puan" in spoken
    assert "altmış altı virgül seksen dört dolardan" in spoken
    assert "Ons altın yüzde sıfır virgül elli dört yükselişle üç bin dokuz yüz seksen iki dolar" in spoken


def test_missing_value_is_skipped():
    s = spoken_market_sentence([MarketIndicator(key="cds", label="CDS", value=None)])
    assert s == ""
