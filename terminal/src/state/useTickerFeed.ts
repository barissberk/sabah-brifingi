import { useEffect, useRef, useState } from "react";
import type { Ticker } from "../types";

export interface LiveTick {
  value: number | null;
  change: number | null;
  flash: "up" | "down" | null;
  /** Her yeni tikte artar; parlama animasyonunu yeniden tetiklemek için anahtar olarak kullanılır */
  seq: number;
}

// Tür başına tik oynaklığı (göreli). Getirilerde mutlak yüzde puanı.
const SIGMA: Record<Ticker["kind"], number> = { index: 0.00018, fx: 0.00007, commodity: 0.00022, rate: 0.0025 };
const TICK_MS = 250;

function gauss() {
  return Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());
}

/** Önceki kapanış (referans) değeri: değişim yüzdesi veya baz puandan geri hesaplanır. */
function reference(t: Ticker): number | null {
  if (t.value == null || t.change == null) return null;
  return t.change_unit === "bp" ? t.value - t.change / 100 : t.value / (1 + t.change / 100);
}

/**
 * Önceki kapanış verisinin üzerinde saniye altı tik simülasyonu.
 * Değerler referansa doğru ortalamaya döner (sapma birikmez); `running=false` iken gerçek kapanış gösterilir.
 */
export function useTickerFeed(base: Ticker[], running: boolean): Record<string, LiveTick> {
  const initial = () =>
    Object.fromEntries(base.map((t) => [t.symbol, { value: t.value, change: t.change, flash: null, seq: 0 }]));
  const [ticks, setTicks] = useState<Record<string, LiveTick>>(initial);
  const baseRef = useRef(base);

  useEffect(() => {
    baseRef.current = base;
    setTicks(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  useEffect(() => {
    if (!running) {
      setTicks(initial());
      return;
    }
    const id = window.setInterval(() => {
      setTicks((prev) => {
        const next = { ...prev };
        const live = baseRef.current.filter((t) => t.value != null);
        const count = 1 + Math.floor(Math.random() * 3);
        for (let i = 0; i < count && live.length; i++) {
          const t = live[Math.floor(Math.random() * live.length)];
          const cur = next[t.symbol]?.value ?? t.value!;
          const pull = (t.value! - cur) * 0.04;                      // ortalamaya dönüş
          const shock = t.kind === "rate" ? SIGMA.rate * gauss() : cur * SIGMA[t.kind] * gauss();
          const value = cur + pull + shock;
          const ref = reference(t);
          const change = ref == null ? t.change
            : t.change_unit === "bp" ? (value - ref) * 100 : (value / ref - 1) * 100;
          next[t.symbol] = {
            value, change, flash: value > cur ? "up" : value < cur ? "down" : null,
            seq: (next[t.symbol]?.seq ?? 0) + 1,
          };
        }
        return next;
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  return ticks;
}
