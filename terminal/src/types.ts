// Python boru hattının ürettiği terminal.json sözleşmesi (agents/terminal_export.py)

export type ChangeUnit = "%" | "bp";
export type Impact = "high" | "medium" | "low";
export type Category = "makro" | "doviz" | "bist" | "emtia" | "kap";

export interface Ticker {
  symbol: string;
  name: string;
  value: number | null;
  change: number | null;
  change_unit: ChangeUnit;
  decimals: number;
  kind: "index" | "fx" | "commodity" | "rate";
  source: string | null;
}

export interface Pivot {
  symbol: string;
  basis: string;
  pivot: number;
  r1: number;
  r2: number;
  s1: number;
  s2: number;
}

export interface Sector {
  key: string;
  name: string;
  change: number | null;
  basket: string | null;
}

export interface Pillar {
  title: string;
  body: string;
}

export interface AudioBriefing {
  url: string | null;
  duration: number | null;
  transcript: string;
}

export interface Figure {
  label: string;
  value: string;
}

export interface WireItem {
  id: string;
  headline: string;
  summary: string;
  source: string;
  url: string | null;
  published: string | null;
  category: Category;
  impact: Impact;
  tickers: string[];
  in_briefing: boolean;
  take: string | null;
  commentary: string | null;
  figures: Figure[];
}

export interface CalendarEvent {
  time: string;
  country: string;
  event: string;
  importance: Impact;
  forecast: string | null;
  previous: string | null;
  actual: string | null;
}

export interface AnalystRow {
  ticker: string;
  house: string;
  old_target: number;
  new_target: number;
  price: number;
  rating: "AL" | "ENDEKS ÜSTÜ" | "TUT" | "SAT" | string;
}

export interface TerminalData {
  generated_at: string;
  date: string;
  is_demo: boolean;
  tickers: Ticker[];
  pivot: Pivot | null;
  sectors: Sector[];
  executive_summary: string[];
  pillars: Pillar[];
  audio: AudioBriefing | null;
  wire: WireItem[];
  calendar: CalendarEvent[];
  analyst_desk: { is_sample: boolean; rows: AnalystRow[] };
  sources: string[];
}

/** Hangi bölümlerin örnek (demo) veriyle doldurulduğu — arayüzde açıkça belirtilir. */
export interface SampleFlags {
  tickers: boolean;
  pivot: boolean;
  sectors: boolean;
  pillars: boolean;
  audio: boolean;
  wire: boolean;
  calendar: boolean;
  analyst: boolean;
}
