"""Seslendirme için metin normalizasyonu (Türkçe).

TTS motorları "3.982,40", "%1,18", "$66" veya "5Y" gibi ifadeleri tutarsız okuyabilir.
Bu modül rakamları Türkçe kelimelere çevirir ve kısaltmaları açar; böylece her değer
birimiyle birlikte net ve deterministik okunur.
"""
from __future__ import annotations

import re
from typing import List, Optional

from models import MarketIndicator

_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SCALES = [(10 ** 12, "trilyon"), (10 ** 9, "milyar"), (10 ** 6, "milyon"), (1000, "bin")]


def _under_thousand(n: int) -> List[str]:
    words: List[str] = []
    h, rest = divmod(n, 100)
    if h:
        words += ([] if h == 1 else [_ONES[h]]) + ["yüz"]
    t, o = divmod(rest, 10)
    words += [w for w in (_TENS[t], _ONES[o]) if w]
    return words


def int_to_words(n: int) -> str:
    """12345 → 'on iki bin üç yüz kırk beş'"""
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + int_to_words(-n)
    words: List[str] = []
    for value, name in _SCALES:
        count, n = divmod(n, value)
        if count:
            words += ([] if (count == 1 and name == "bin") else int_to_words(count).split()) + [name]
    words += _under_thousand(n)
    return " ".join(words)


def number_to_words(text: str) -> str:
    """Türkçe biçimli sayı ('3.982,40', '1,18', '270') → kelimeler. Ondalık 'virgül' ile okunur."""
    integer, _, decimal = text.replace(".", "").partition(",")
    spoken = int_to_words(int(integer))
    if decimal:
        # Ondalık ikişerli gruplar halinde okunur: 41,9725 → 'kırk bir virgül doksan yedi yirmi beş'
        groups = [decimal[i:i + 2] for i in range(0, len(decimal), 2)]
        spoken += " virgül " + " ".join(
            ("sıfır " + _ONES[int(g[1])] if g.startswith("0") and len(g) == 2 and g != "00" else
             "sıfır sıfır" if g == "00" else int_to_words(int(g))).strip()
            for g in groups)
    return spoken


# Kısaltma → okunuş (kelime sınırlarında, büyük/küçük harf duyarlı)
ABBREVIATIONS = {
    "USD/TRY": "dolar/TL kuru",
    "Dolar/TL": "Dolar/TL",
    "TCMB": "Merkez Bankası",
    "ECB": "Avrupa Merkez Bankası",
    "BIST": "Bist",
    "OPEC+": "OPEC artı",
    "bps": "baz puan",
    "5Y": "beş yıllık",
}

_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def normalize_for_speech(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]\s*", "", text)                              # [MOCK] vb. etiketler
    for abbr, spoken in ABBREVIATIONS.items():
        text = re.sub(rf"(?<![\w/]){re.escape(abbr)}(?![\w/])", spoken, text)
    text = re.sub(rf"\$\s*({_NUM})", r"\1 dolar", text)                    # $66,84 → 66,84 dolar
    text = re.sub(rf"%\s*({_NUM})", r"yüzde \1", text)                     # %1,2 → yüzde 1,2
    text = re.sub(rf"({_NUM})\s*%", r"yüzde \1", text)
    # Saat: 14:30'da → on dört otuzda, 17:00'de → on yedide (sayıya bağlı kesme işareti kaldırılır)
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b['’]?",
                  lambda m: int_to_words(int(m.group(1))) +
                  (" " + int_to_words(int(m.group(2))) if int(m.group(2)) else ""), text)
    text = re.sub(rf"({_NUM})['’]?", lambda m: number_to_words(m.group(1)), text)
    return re.sub(r"\s{2,}", " ", text).strip()


# ---------------------------------------------------------------------------
# Piyasa cümlesi: her değer birimiyle ve konuşma diline uygun yuvarlamayla
# ---------------------------------------------------------------------------
def _tr(value: float, decimals: int) -> str:
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _move(change: Optional[float]) -> str:
    if change is None or abs(change) < 0.005:
        return ""
    return f"yüzde {_tr(abs(change), 2)} {'yükselişle' if change > 0 else 'düşüşle'} "


def spoken_market_phrase(m: MarketIndicator) -> Optional[str]:
    """Gösterge başına kısa, birimli bir cümle; normalize_for_speech ile kelimeye çevrilir."""
    if m.value is None:
        return None
    mv = _move(m.change_pct)
    if m.key == "bist100":
        return f"BIST 100 endeksi {mv}{_tr(round(m.value), 0)} puandan kapandı."
    if m.key == "usdtry":
        lira, kurus = divmod(round(m.value * 100), 100)
        return f"Dolar/TL {mv}{lira} lira {kurus} kuruştan işlem görüyor."
    if m.key == "cds":
        return f"Türkiye'nin beş yıllık CDS risk primi {mv}{_tr(round(m.value), 0)} baz puan seviyesinde."
    if m.key == "brent":
        return f"Brent petrolün varili {mv}{_tr(m.value, 2)} dolardan işlem görüyor."
    if m.key == "gold":
        return f"Ons altın {mv}{_tr(round(m.value), 0)} dolar seviyesinde."
    unit = {"$": "dolar", "bps": "baz puan"}.get(m.unit, m.unit)
    return f"{m.label} {mv}{_tr(m.value, m.decimals)} {unit} seviyesinde.".replace("  ", " ")


def spoken_market_sentence(markets: List[MarketIndicator]) -> str:
    phrases = [p for p in (spoken_market_phrase(m) for m in markets) if p]
    return ("Piyasalara bakalım. " + " ".join(phrases)) if phrases else ""
