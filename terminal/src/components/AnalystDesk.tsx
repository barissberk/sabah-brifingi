import type { AnalystRow, Sector } from "../types";
import { ARROW, DIR_TEXT, direction, fmtChange, fmtNum } from "../lib/format";
import { SampleNote } from "./SampleNote";

const RATING_TONE: Record<string, string> = {
  AL: "text-emerald-400",
  "ENDEKS ÜSTÜ": "text-accent",
  TUT: "text-neutral-300",
  SAT: "text-rose-400",
};

function TargetTable({ rows, isSample }: { rows: AnalystRow[]; isSample: boolean }) {
  return (
    <div className="surface overflow-x-auto">
      <div className="flex items-baseline justify-between border-b hairline px-4 py-3">
        <h3 className="text-[14px] font-semibold text-neutral-100">Hedef fiyat revizyonları</h3>
        {isSample && <SampleNote text="Örnek veri · lisanslı araştırma akışı bağlandığında dolar" />}
      </div>
      <table className="w-full min-w-[640px] text-[13px]">
        <thead>
          <tr className="border-b hairline text-left">
            {["Hisse", "Kurum", "Eski hedef", "Yeni hedef", "Fiyat", "Potansiyel", "Tavsiye"].map((h, i) => (
              <th key={h} className={`label px-4 py-2.5 font-medium ${i >= 2 && i <= 5 ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/70">
          {rows.map((r) => {
            const upside = (r.new_target / r.price - 1) * 100;
            const rev = direction(r.new_target - r.old_target);
            return (
              <tr key={`${r.ticker}-${r.house}`}>
                <td className="num px-4 py-2.5 text-neutral-100">${r.ticker}</td>
                <td className="px-4 py-2.5 text-neutral-400">{r.house}</td>
                <td className="num px-4 py-2.5 text-right text-neutral-500">{fmtNum(r.old_target, 2)}</td>
                <td className="num px-4 py-2.5 text-right text-neutral-100">
                  <span className={`mr-1.5 ${DIR_TEXT[rev]}`}>{ARROW[rev]}</span>{fmtNum(r.new_target, 2)}
                </td>
                <td className="num px-4 py-2.5 text-right text-neutral-300">{fmtNum(r.price, 2)}</td>
                <td className={`num px-4 py-2.5 text-right ${DIR_TEXT[direction(upside)]}`}>{fmtChange(upside)}</td>
                <td className={`px-4 py-2.5 text-[12px] font-medium tracking-wide ${RATING_TONE[r.rating] ?? "text-neutral-300"}`}>{r.rating}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SectorHeatmap({ sectors, isSample }: { sectors: Sector[]; isSample: boolean }) {
  const max = Math.max(1, ...sectors.map((s) => Math.abs(s.change ?? 0)));
  return (
    <div className="surface">
      <div className="flex items-baseline justify-between border-b hairline px-4 py-3">
        <h3 className="text-[14px] font-semibold text-neutral-100">Sektör nabzı</h3>
        <span className="text-[11px] text-neutral-500">
          Günlük değişim {isSample && <><span className="text-neutral-700">·</span> <SampleNote text="örnek" /></>}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-px bg-neutral-800 sm:grid-cols-5 xl:grid-cols-2">
        {sectors.map((s) => {
          const d = direction(s.change);
          const alpha = s.change == null ? 0 : 0.06 + (Math.abs(s.change) / max) * 0.28;
          const bg = d === "up" ? `rgb(52 211 153 / ${alpha})` : d === "down" ? `rgb(251 113 133 / ${alpha})` : "transparent";
          return (
            <div key={s.key} className="bg-neutral-950 last:odd:col-span-2 xl:last:odd:col-span-2 sm:last:odd:col-span-1">
              <div className="h-full px-4 py-3.5" style={{ backgroundColor: bg }}>
                <div className="text-[13px] text-neutral-200">{s.name}</div>
                <div className={`num mt-1 text-[18px] ${DIR_TEXT[d]}`}>{fmtChange(s.change)}</div>
                <div className="mt-1 truncate text-[11px] text-neutral-500">{s.basket ? `Sepet: ${s.basket}` : "Endeks"}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AnalystDesk({ rows, sectors, sample }: {
  rows: AnalystRow[]; sectors: Sector[]; sample: { analyst: boolean; sectors: boolean };
}) {
  return (
    <section id="analist" className="scroll-mt-28">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-neutral-50">Analist Masası ve Sektör Nabzı</h2>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <TargetTable rows={rows} isSample={sample.analyst} />
        <SectorHeatmap sectors={sectors} isSample={sample.sectors} />
      </div>
    </section>
  );
}
