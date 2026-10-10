import { Pause, Play } from "lucide-react";
import type { Ticker } from "../types";
import type { LiveTick } from "../state/useTickerFeed";
import { DIR_TEXT, direction, fmtChange, fmtNum } from "../lib/format";

interface Props {
  tickers: Ticker[];
  live: Record<string, LiveTick>;
  activeSymbol: string | null;
  onSelect: (symbol: string | null) => void;
  simulating: boolean;
  onToggleSim: () => void;
  isSample: boolean;
}

export function TickerRibbon({ tickers, live, activeSymbol, onSelect, simulating, onToggleSim, isSample }: Props) {
  return (
    <div className="border-b hairline bg-neutral-950">
      <div className="mx-auto flex max-w-[1440px] items-stretch">
        <div className="scroll-thin flex flex-1 overflow-x-auto">
          {tickers.map((t) => {
            const tick = live[t.symbol];
            const value = tick?.value ?? t.value;
            const change = tick?.change ?? t.change;
            const d = direction(change);
            const active = activeSymbol === t.symbol;
            return (
              <button
                key={t.symbol}
                type="button"
                onClick={() => onSelect(active ? null : t.symbol)}
                aria-pressed={active}
                title={`${t.name} · akışı bu göstergeye göre süz`}
                className={`relative flex shrink-0 flex-col items-start gap-0.5 border-r hairline px-4 py-2.5 text-left transition-colors hover:bg-neutral-900 ${
                  active ? "bg-neutral-900" : ""
                }`}
              >
                <span className="flex items-baseline gap-2 text-[11px]">
                  <span className={`num font-medium ${active ? "text-accent" : "text-neutral-400"}`}>{t.symbol}</span>
                  <span className="text-neutral-600">{t.name}</span>
                </span>
                <span className="flex items-baseline gap-3">
                  <span
                    key={tick?.seq}
                    className={`num -mx-1 px-1 text-[14px] text-neutral-100 ${
                      tick?.flash === "up" ? "flash-up" : tick?.flash === "down" ? "flash-down" : ""
                    }`}
                  >
                    {t.kind === "rate" && value != null ? `%${fmtNum(value, t.decimals)}` : fmtNum(value, t.decimals)}
                  </span>
                  <span className={`num text-[12px] ${DIR_TEXT[d]}`}>{fmtChange(change, t.change_unit)}</span>
                </span>
                {active && <span className="absolute inset-x-0 bottom-0 h-px bg-accent" />}
              </button>
            );
          })}
        </div>
        <div className="hidden shrink-0 items-center gap-3 border-l hairline px-4 text-[11px] text-neutral-500 xl:flex">
          <span>
            {isSample ? <span className="text-accent">Örnek veri</span> : "Önceki kapanış"}
            {simulating && <> <span className="text-neutral-700">·</span> <span className="text-accent/90">simülasyon</span></>}
          </span>
          <button type="button" onClick={onToggleSim} aria-pressed={simulating}
            title={simulating ? "Tik simülasyonunu durdur" : "Tik simülasyonunu başlat"}
            className="flex h-6 w-6 items-center justify-center border hairline text-neutral-400 hover:text-neutral-100">
            {simulating ? <Pause size={12} /> : <Play size={12} />}
          </button>
        </div>
      </div>
    </div>
  );
}
