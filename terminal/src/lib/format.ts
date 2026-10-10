import type { Category, ChangeUnit } from "../types";

const nfCache = new Map<number, Intl.NumberFormat>();
function nf(decimals: number) {
  let f = nfCache.get(decimals);
  if (!f) {
    f = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    nfCache.set(decimals, f);
  }
  return f;
}

export function fmtNum(value: number | null | undefined, decimals = 2): string {
  return value == null || Number.isNaN(value) ? "—" : nf(decimals).format(value);
}

export function direction(change: number | null | undefined): "up" | "down" | "flat" {
  if (change == null || Math.abs(change) < 1e-9) return "flat";
  return change > 0 ? "up" : "down";
}

export const ARROW = { up: "▲", down: "▼", flat: "■" } as const;

export const DIR_TEXT = {
  up: "text-emerald-400",
  down: "text-rose-400",
  flat: "text-neutral-500",
} as const;

/** "▲ 0,43%" / "▼ 1,3 bp" — yön her zaman okla birlikte verilir. */
export function fmtChange(change: number | null | undefined, unit: ChangeUnit = "%"): string {
  if (change == null) return "—";
  const d = direction(change);
  const v = unit === "bp" ? `${fmtNum(Math.abs(change), 1)} bp` : `${fmtNum(Math.abs(change), 2)}%`;
  return `${ARROW[d]} ${v}`;
}

const timeFmt = new Intl.DateTimeFormat("tr-TR", { timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit" });
const longDateFmt = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul", day: "numeric", month: "long", year: "numeric", weekday: "long",
});

export function fmtTime(iso: string | null): string {
  if (!iso) return "--:--";
  return timeFmt.format(new Date(iso));
}

const isoDay = (d: Date) => d.toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" }); // YYYY-MM-DD

/** Bülten gününden farklı bir günse "08.10 21:05", aynı günse yalnızca saat */
export function fmtStamp(iso: string | null, referenceDate: string): string {
  if (!iso) return "--:--";
  const d = new Date(iso);
  if (isoDay(d) === referenceDate) return fmtTime(iso);
  const [, m, dd] = isoDay(d).split("-");
  return `${dd}.${m} ${fmtTime(iso)}`;
}

export function fmtLongDate(isoDate: string): string {
  return longDateFmt.format(new Date(`${isoDate}T09:00:00+03:00`));
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "--:--";
  const s = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export const CATEGORY_LABEL: Record<Category, string> = {
  makro: "Makro & Merkez Bankaları",
  bist: "BIST & Şirketler",
  doviz: "Döviz & Tahvil",
  emtia: "Emtia & Enerji",
  kap: "KAP Bildirimleri",
};

/** Gösterge şeridinden akışa süzme: sembol → haber metninde aranacak ifadeler */
export const TICKER_ALIASES: Record<string, string[]> = {
  XU100: ["bist", "borsa"],
  XU030: ["bist 30", "bist30", "borsa"],
  USDTRY: ["dolar/tl", "dolar", "kur"],
  EURTRY: ["euro/tl", "euro"],
  EURUSD: ["euro/dolar", "parite", "ecb"],
  DXY: ["dolar endeksi", "dxy", "fed"],
  BRENT: ["brent", "petrol", "opec", "varil"],
  XAUUSD: ["altın", "ons"],
  TR2Y: ["tahvil", "faiz", "tcmb"],
  US10Y: ["tahvil", "getiri", "fed", "hazine"],
};

/** Akış haberinin kategorisine göre çekmecede gösterilecek bağlam göstergeleri */
export const CONTEXT_TICKERS: Record<Category, string[]> = {
  makro: ["US10Y", "DXY", "USDTRY"],
  doviz: ["USDTRY", "EURTRY", "TR2Y", "US10Y"],
  bist: ["XU100", "XU030", "USDTRY"],
  emtia: ["BRENT", "XAUUSD", "DXY"],
  kap: ["XU100", "XU030"],
};
