import { useEffect, useState } from "react";
import type { CalendarEvent } from "../types";

const IMPORTANCE = { high: "Yüksek", medium: "Orta", low: "Düşük" } as const;

function eventTime(date: string, hhmm: string) {
  return new Date(`${date}T${hhmm.padStart(5, "0")}:00+03:00`).getTime();
}

function countdown(ms: number) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `T− ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function MacroCalendar({ events, date, isSample }: { events: CalendarEvent[]; date: string; isSample: boolean }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Örnek takvim bugünün saatlerine göre geri sayar; gerçek takvim bülten gününe göre
  const day = isSample ? new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" }) : date;
  const sorted = [...events].sort((a, b) => a.time.localeCompare(b.time));
  const nextIdx = sorted.findIndex((e) => eventTime(day, e.time) > now);

  return (
    <section id="takvim" className="scroll-mt-28">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-neutral-50">Makro Olay Takvimi</h2>
        <span className="text-[11px] text-neutral-500">
          Türkiye saati {isSample && <><span className="text-neutral-700">·</span> <span className="text-accent">örnek takvim</span></>}
        </span>
      </div>
      <div className="surface overflow-x-auto">
        <table className="w-full min-w-[760px] text-[13px]">
          <thead>
            <tr className="border-b hairline text-left">
              {["Saat", "Ülke", "Gösterge", "Önem", "Önceki", "Beklenti", "Gerçekleşen", "Geri sayım"].map((h, i) => (
                <th key={h} className={`label px-4 py-2.5 font-medium ${i >= 4 ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800/70">
            {sorted.map((e, i) => {
              const t = eventTime(day, e.time);
              const next = i === nextIdx;
              return (
                <tr key={`${e.time}-${e.event}`} className={next ? "bg-accent/[0.04]" : undefined}>
                  <td className={`num px-4 py-2.5 ${next ? "border-l-2 border-accent text-accent" : "border-l-2 border-transparent text-neutral-300"}`}>{e.time}</td>
                  <td className="num px-4 py-2.5 text-neutral-500">{e.country}</td>
                  <td className="px-4 py-2.5 text-neutral-100">{e.event}</td>
                  <td className={`px-4 py-2.5 ${e.importance === "high" ? "text-accent" : "text-neutral-500"}`}>{IMPORTANCE[e.importance]}</td>
                  <td className="num px-4 py-2.5 text-right text-neutral-500">{e.previous ?? "—"}</td>
                  <td className="num px-4 py-2.5 text-right text-neutral-300">{e.forecast ?? "—"}</td>
                  <td className="num px-4 py-2.5 text-right text-neutral-100">{e.actual ?? "—"}</td>
                  <td className="num px-4 py-2.5 text-right text-neutral-400">
                    {t > now ? countdown(t - now) : e.actual ? "Açıklandı" : "Bekleniyor"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
