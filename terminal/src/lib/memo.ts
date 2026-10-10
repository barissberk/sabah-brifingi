import type { TerminalData, Ticker } from "../types";
import { CATEGORY_LABEL, fmtChange, fmtLongDate, fmtNum, fmtStamp } from "./format";

const LINE = "─".repeat(64);

function tickerLine(t: Ticker, value: number | null, change: number | null) {
  const v = t.kind === "rate" && value != null ? `%${fmtNum(value, t.decimals)}` : fmtNum(value, t.decimals);
  return `  ${t.name.padEnd(18)}${v.padStart(14)}   ${fmtChange(change, t.change_unit)}`;
}

/**
 * Kurumsal sabah notu (düz metin) — panoya kopyalama veya .txt indirme için.
 * Bilerek yalnızca gerçek kapanış verisini kullanır; şeritteki simüle tikler nota asla girmez.
 */
export function buildMemo(d: TerminalData, sampleNote: string | null): string {
  const out: string[] = [];
  out.push("AURA TERMINAL · SABAH NOTU", fmtLongDate(d.date), LINE);
  if (sampleNote) out.push(`Not: ${sampleNote}`, LINE);

  out.push("", "PİYASALAR (önceki kapanış)");
  for (const t of d.tickers) {
    out.push(tickerLine(t, t.value, t.change));
  }

  out.push("", "YÖNETİCİ ÖZETİ");
  d.executive_summary.forEach((s) => out.push(`  • ${s}`));

  if (d.pillars.length) {
    out.push("", "SABAHIN 3 KRİTİK EKSENİ");
    d.pillars.slice(0, 3).forEach((p, i) => out.push(`  ${i + 1}. ${p.title}`, `     ${p.body}`));
  }

  if (d.pivot) {
    const p = d.pivot;
    out.push("", `TEKNİK PİVOT (${p.symbol}, ${p.basis})`,
      `  S2 ${fmtNum(p.s2, 0)}  ·  S1 ${fmtNum(p.s1, 0)}  ·  Pivot ${fmtNum(p.pivot, 0)}  ·  R1 ${fmtNum(p.r1, 0)}  ·  R2 ${fmtNum(p.r2, 0)}`);
  }

  const high = d.wire.filter((w) => w.impact === "high").slice(0, 8);
  if (high.length) {
    out.push("", "YÜKSEK ETKİLİ GELİŞMELER");
    high.forEach((w) => out.push(
      `  ${fmtStamp(w.published, d.date)}  ${w.headline}`,
      `         ${w.source} / ${CATEGORY_LABEL[w.category]}${w.url ? ` / ${w.url}` : ""}`,
    ));
  }

  if (d.calendar.length) {
    out.push("", "GÜNÜN TAKVİMİ (TSİ)");
    d.calendar.forEach((e) => out.push(
      `  ${e.time}  ${e.country.padEnd(3)} ${e.event}${e.forecast ? `  · beklenti ${e.forecast}` : ""}${e.previous ? ` · önceki ${e.previous}` : ""}`,
    ));
  }

  out.push("", LINE, `Kaynaklar: ${d.sources.join(", ")}`,
    "Bu not yalnızca bilgilendirme amaçlıdır; yatırım tavsiyesi niteliği taşımaz.");
  return out.join("\n");
}
