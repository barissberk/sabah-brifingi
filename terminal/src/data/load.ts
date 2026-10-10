import type { SampleFlags, TerminalData } from "../types";
import { DEMO_DATA } from "./demo";

export interface LoadedData {
  data: TerminalData;
  sample: SampleFlags;
  /** Boru hattı verisi hiç okunamadıysa nedeni */
  error: string | null;
}

const ALL_SAMPLE: SampleFlags = {
  tickers: true, pivot: true, sectors: true, pillars: true, audio: true, wire: true, calendar: true, analyst: true,
};

/**
 * Boru hattının ürettiği `data/terminal.json` dosyasını okur. Boş gelen her bölüm örnek veriyle
 * doldurulur ve `sample` bayraklarıyla işaretlenir; böylece arayüz gerçek ve örnek veriyi ayırt eder.
 */
export async function loadTerminalData(): Promise<LoadedData> {
  let real: TerminalData;
  try {
    const res = await fetch(`data/terminal.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    real = (await res.json()) as TerminalData;
  } catch (err) {
    return { data: DEMO_DATA, sample: ALL_SAMPLE, error: `Boru hattı verisi okunamadı (${String(err)})` };
  }

  const demo = DEMO_DATA;
  const isDemo = real.is_demo;
  const usable = real.tickers.filter((t) => t.value != null).length > 0;
  const sample: SampleFlags = {
    tickers: isDemo || !usable,
    pivot: isDemo || !real.pivot,
    sectors: isDemo || !real.sectors.some((s) => s.change != null),
    pillars: isDemo || real.pillars.length === 0,
    audio: !real.audio,
    wire: real.wire.length === 0,
    calendar: real.calendar.length === 0,
    analyst: real.analyst_desk.is_sample,
  };

  return {
    data: {
      ...real,
      tickers: sample.tickers ? demo.tickers : real.tickers,
      pivot: sample.pivot ? demo.pivot : real.pivot,
      sectors: sample.sectors ? demo.sectors : real.sectors,
      pillars: sample.pillars ? demo.pillars : real.pillars,
      audio: sample.audio ? demo.audio : real.audio,
      wire: sample.wire ? demo.wire : real.wire,
      calendar: sample.calendar ? demo.calendar : real.calendar,
    },
    sample,
    error: null,
  };
}
