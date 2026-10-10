// ÖRNEK VERİ — yalnızca boru hattı verisi olmadığında veya ilgili bölüm boş geldiğinde kullanılır.
// Arayüz bu verinin kullanıldığı her bölümü "Örnek veri" olarak işaretler.
import type { CalendarEvent, Pillar, Pivot, Sector, Ticker, TerminalData, WireItem } from "../types";

const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" });
const at = (hhmm: string, dayOffset = 0) => {
  const d = new Date(`${today}T${hhmm}:00+03:00`);
  d.setDate(d.getDate() + dayOffset);
  return d.toISOString();
};

export const DEMO_TICKERS: Ticker[] = [
  { symbol: "XU100", name: "BIST 100", value: 9968.42, change: 0.62, change_unit: "%", decimals: 2, kind: "index", source: "Örnek" },
  { symbol: "XU030", name: "BIST 30", value: 10874.15, change: 0.71, change_unit: "%", decimals: 2, kind: "index", source: "Örnek" },
  { symbol: "USDTRY", name: "USD/TRY", value: 41.9725, change: 0.12, change_unit: "%", decimals: 4, kind: "fx", source: "Örnek" },
  { symbol: "EURTRY", name: "EUR/TRY", value: 48.6610, change: -0.08, change_unit: "%", decimals: 4, kind: "fx", source: "Örnek" },
  { symbol: "EURUSD", name: "EUR/USD", value: 1.1594, change: -0.21, change_unit: "%", decimals: 4, kind: "fx", source: "Örnek" },
  { symbol: "DXY", name: "Dolar Endeksi", value: 98.74, change: 0.24, change_unit: "%", decimals: 2, kind: "index", source: "Örnek" },
  { symbol: "BRENT", name: "Brent", value: 66.84, change: -0.87, change_unit: "%", decimals: 2, kind: "commodity", source: "Örnek" },
  { symbol: "XAUUSD", name: "Altın (XAU/USD)", value: 3982.4, change: 0.54, change_unit: "%", decimals: 2, kind: "commodity", source: "Örnek" },
  { symbol: "TR2Y", name: "TR 2Y Tahvil", value: 38.42, change: -6.0, change_unit: "bp", decimals: 2, kind: "rate", source: "Örnek" },
  { symbol: "US10Y", name: "ABD 10Y Getiri", value: 4.087, change: 2.1, change_unit: "bp", decimals: 3, kind: "rate", source: "Örnek" },
];

export const DEMO_PIVOT: Pivot = {
  symbol: "XU100", basis: "Örnek seviyeler", pivot: 9940, r1: 10020, r2: 10150, s1: 9880, s2: 9750,
};

export const DEMO_SECTORS: Sector[] = [
  { key: "banking", name: "Bankacılık", change: 1.84, basket: null },
  { key: "transport", name: "Ulaştırma", change: 2.31, basket: "THYAO · PGSUS · CLEBI" },
  { key: "industrial", name: "Sanayi", change: -0.42, basket: null },
  { key: "holding", name: "Holding", change: 0.38, basket: "KCHOL · SAHOL · AGHOL" },
  { key: "tech", name: "Teknoloji", change: -1.12, basket: "ASELS · LOGO · KAREL" },
];

export const DEMO_PILLARS: Pillar[] = [
  {
    title: "TCMB likiditesi ve banka marjları",
    body: "Sterilizasyon araçlarıyla sıkı likidite duruşu korunurken swap hariç net rezervlerdeki toparlanma, bankacılıkta net faiz marjı (NIM) iyileşmesi beklentisini destekliyor.",
  },
  {
    title: "Dolar endeksi ve gelişen piyasa riski",
    body: "Küresel dolar güçlenmesine rağmen 264 baz puandaki 5 yıllık CDS, yerel varlıklar için çıpa görevi görüyor; DXY'deki yükseliş kur tarafında sınırlı yansıyor.",
  },
  {
    title: "Bilanço ve havacılık ivmesi",
    body: "THYAO'nun güçlü yolcu trafiği verisi ve çelik üreticilerindeki marj güncellemeleri, şirket tarafında seans içi ayrışmayı belirleyecek.",
  },
];

export const DEMO_TRANSCRIPT =
  "Günaydın, sabah finans brifingine hoş geldiniz. Piyasalara bakalım. BIST 100 endeksi yüzde 0,62 yükselişle 9.968 puandan kapandı. Dolar/TL 41 lira 97 kuruştan işlem görüyor. Türkiye'nin beş yıllık CDS risk primi 264 baz puan seviyesinde. Brent petrolün varili 66,84 dolardan, ons altın 3.982 dolar seviyesinde. Sabahın ilk ekseni Merkez Bankası likiditesi: swap hariç net rezervlerdeki toparlanma banka marjlarını destekliyor. İkinci eksen dolar endeksi: küresel dolar güçlenirken CDS'teki düşüş yerel varlıkları dengeliyor. Üçüncü eksen şirket tarafı: havacılıkta güçlü trafik verisi öne çıkıyor. Bugün takvimde sanayi üretimi ve Michigan tüketici güveni var. Detaylar terminalde. Verimli bir gün dileriz.";

const wire = (
  id: string, hhmm: string, category: WireItem["category"], impact: WireItem["impact"], source: string,
  headline: string, summary: string, tickers: string[] = [], extra: Partial<WireItem> = {},
): WireItem => ({
  id, headline, summary, source, url: null, published: at(hhmm, hhmm > "08:30" ? -1 : 0), category, impact, tickers,
  in_briefing: impact === "high", take: null, commentary: null, figures: [], ...extra,
});

export const DEMO_WIRE: WireItem[] = [
  wire("d1", "08:12", "makro", "high", "TCMB", "TCMB brüt rezervleri haftalık 3,1 milyar dolar arttı",
    "Brüt rezervler 152,4 milyar dolara yükselirken swap hariç net rezervlerde de belirgin iyileşme kaydedildi.", [],
    {
      take: "Rezerv birikiminin sürmesi, kurda öngörülebilirliği artırarak yabancı taşıma işlemlerine alan açıyor; kısa vadeli TL tahvillerde talep artabilir.",
      commentary: "Swap hariç net rezervdeki artış, CDS'teki düşüşle birlikte risk priminin kalıcı olarak gerilediğine işaret ediyor.",
      figures: [{ label: "Brüt rezerv", value: "152,4 mlr $" }, { label: "Haftalık değişim", value: "▲ 3,1 mlr $" }, { label: "5Y CDS", value: "264 bp" }],
    }),
  wire("d2", "07:58", "bist", "high", "KAP", "THYAO eylül yolcu trafiği yıllık %11 arttı",
    "Dış hat transfer yolcusundaki artış toplam yolcu sayısını rekor seviyeye taşıdı; doluluk oranı 1,8 puan yükseldi.", ["THYAO"],
    {
      take: "Güçlü trafik, üçüncü çeyrek gelir beklentilerinde yukarı yönlü revizyon riskini artırıyor.",
      commentary: "Havacılık hisselerinde endeks üzeri performans beklentisi korunuyor.",
      figures: [{ label: "Yolcu (yıllık)", value: "▲ %11,2" }, { label: "Doluluk", value: "%84,6" }],
    }),
  wire("d3", "07:41", "doviz", "medium", "Bloomberg HT", "Dolar/TL güne yatay başladı, swap oranları geriledi",
    "Gecelik swap oranlarındaki düşüş, yabancı yatırımcının TL pozisyonlarını koruduğuna işaret ediyor.", []),
  wire("d4", "07:30", "emtia", "medium", "Foreks", "Brent, OPEC+ arz artışı beklentisiyle 67 doların altında",
    "Piyasa, gelecek hafta yapılacak OPEC+ toplantısında üretim artışının sürdürülmesini fiyatlıyor.", []),
  wire("d5", "07:12", "bist", "medium", "Bloomberg HT", "Bankacılık endeksi marj beklentileriyle öncü",
    "GARAN ve AKBNK'deki alımlar, faiz indirimi döngüsünde marj toparlanması beklentisine dayanıyor.", ["GARAN", "AKBNK"]),
  wire("d6", "06:45", "makro", "high", "Reuters", "Fed tutanakları: üyelerin çoğu ek indirime açık",
    "İşgücü piyasasındaki yavaşlama, politika faizinde kademeli gevşemeyi destekliyor.", []),
  wire("d7", "06:20", "kap", "medium", "KAP", "EREGL: yassı çelik fiyat listesi güncellendi",
    "Şirket, yurt içi yassı mamul fiyatlarında ton başına 15 dolar artışa gittiğini bildirdi.", ["EREGL"]),
  wire("d8", "21:40", "doviz", "medium", "Reuters", "ABD 10 yıllık getirisi %4,09'a yükseldi",
    "Güçlü perakende satış verisi sonrası tahvil getirilerinde yükseliş görüldü.", []),
];

export const DEMO_CALENDAR: CalendarEvent[] = [
  { time: "10:00", country: "TR", event: "Sanayi Üretimi (Yıllık)", importance: "medium", forecast: "%2,1", previous: "%1,8", actual: null },
  { time: "12:00", country: "EZ", event: "Perakende Satışlar (Aylık)", importance: "medium", forecast: "%0,2", previous: "-%0,3", actual: null },
  { time: "15:30", country: "US", event: "Çekirdek ÜFE (Aylık)", importance: "high", forecast: "%0,3", previous: "%0,2", actual: null },
  { time: "17:00", country: "US", event: "Michigan Tüketici Güveni (Öncü)", importance: "high", forecast: "54,2", previous: "55,1", actual: null },
];

export const DEMO_DATA: TerminalData = {
  generated_at: new Date().toISOString(),
  date: today,
  is_demo: true,
  tickers: DEMO_TICKERS,
  pivot: DEMO_PIVOT,
  sectors: DEMO_SECTORS,
  executive_summary: DEMO_PILLARS.map((p) => p.body),
  pillars: DEMO_PILLARS,
  audio: { url: null, duration: 68, transcript: DEMO_TRANSCRIPT },
  wire: DEMO_WIRE,
  calendar: DEMO_CALENDAR,
  analyst_desk: {
    is_sample: true,
    rows: [
      { ticker: "THYAO", house: "Örnek Kurum A", old_target: 410, new_target: 455, price: 352.5, rating: "AL" },
      { ticker: "GARAN", house: "Örnek Kurum B", old_target: 165, new_target: 178, price: 142.3, rating: "ENDEKS ÜSTÜ" },
      { ticker: "EREGL", house: "Örnek Kurum C", old_target: 38, new_target: 36.5, price: 33.8, rating: "TUT" },
      { ticker: "ASELS", house: "Örnek Kurum D", old_target: 120, new_target: 134, price: 108.9, rating: "AL" },
    ],
  },
  sources: ["Örnek veri"],
};
