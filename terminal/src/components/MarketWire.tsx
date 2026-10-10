import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import type { Category, Ticker, WireItem } from "../types";
import { CATEGORY_LABEL, TICKER_ALIASES, fmtStamp } from "../lib/format";

type Filter = "all" | Category;
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Tüm Akış" },
  { id: "makro", label: CATEGORY_LABEL.makro },
  { id: "bist", label: CATEGORY_LABEL.bist },
  { id: "doviz", label: CATEGORY_LABEL.doviz },
  { id: "emtia", label: CATEGORY_LABEL.emtia },
  { id: "kap", label: CATEGORY_LABEL.kap },
];

const norm = (s: string) => s.toLocaleLowerCase("tr-TR");

/** Gösterge şeridinden seçilen sembole göre eşleşme: hisse etiketi veya metindeki ilişkili ifadeler. */
export function matchesTicker(item: WireItem, symbol: string): boolean {
  if (item.tickers.includes(symbol)) return true;
  const aliases = TICKER_ALIASES[symbol];
  if (!aliases) return false;
  const text = norm(`${item.headline} ${item.summary}`);
  return aliases.some((a) => text.includes(a));
}

interface Props {
  items: WireItem[];
  date: string;
  tickers: Ticker[];
  activeSymbol: string | null;
  onClearSymbol: () => void;
  onOpen: (item: WireItem) => void;
  isSample: boolean;
}

export function MarketWire({ items, date, tickers, activeSymbol, onClearSymbol, onOpen, isSample }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [highOnly, setHighOnly] = useState(false);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length };
    for (const i of items) c[i.category] = (c[i.category] ?? 0) + 1;
    return c;
  }, [items]);

  const visible = useMemo(() => {
    const q = norm(query.trim().replace(/^\$/, ""));
    return items.filter((i) =>
      (filter === "all" || i.category === filter)
      && (!highOnly || i.impact === "high")
      && (!activeSymbol || matchesTicker(i, activeSymbol))
      && (!q || norm(`${i.headline} ${i.summary} ${i.source} ${i.tickers.join(" ")}`).includes(q)));
  }, [items, filter, highOnly, activeSymbol, query]);

  const activeName = tickers.find((t) => t.symbol === activeSymbol)?.name;

  return (
    <section id="akis" className="scroll-mt-28">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-neutral-50">Piyasa Akışı</h2>
        <span className="text-[11px] text-neutral-500">
          <span className="num">{visible.length}</span> / <span className="num">{items.length}</span> haber
          {isSample && <> <span className="text-neutral-700">·</span> <span className="text-accent">örnek veri</span></>}
        </span>
      </div>

      <div className="surface">
        {/* Kontroller */}
        <div className="flex flex-wrap items-center gap-3 border-b hairline px-4 py-3">
          <div role="group" aria-label="Kategori" className="scroll-thin flex max-w-full overflow-x-auto border hairline">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={filter === f.id}
                className={`shrink-0 border-r hairline px-3 py-1.5 text-[12px] last:border-r-0 transition-colors ${
                  filter === f.id ? "bg-neutral-800 text-neutral-50" : "text-neutral-400 hover:text-neutral-100"
                }`}
              >
                {f.label} <span className="num text-neutral-600">{counts[f.id] ?? 0}</span>
              </button>
            ))}
          </div>

          <label className="flex min-w-[220px] flex-1 items-center gap-2 border hairline px-2.5 py-1.5 focus-within:border-neutral-600">
            <Search size={14} className="text-neutral-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Hisse, başlık veya kurum ara ($THYAO, TCMB…)"
              className="w-full bg-transparent text-[13px] text-neutral-100 placeholder:text-neutral-600 focus:outline-none"
            />
            {query && (
              <button type="button" onClick={() => setQuery("")} aria-label="Aramayı temizle"
                className="text-neutral-500 hover:text-neutral-200"><X size={14} /></button>
            )}
          </label>

          <button
            type="button"
            role="switch"
            aria-checked={highOnly}
            onClick={() => setHighOnly((v) => !v)}
            className="flex items-center gap-2 text-[12px] text-neutral-400 hover:text-neutral-100"
          >
            <span className={`relative h-4 w-7 border transition-colors ${highOnly ? "border-accent bg-accent/20" : "hairline bg-neutral-900"}`}>
              <span className={`absolute top-0.5 h-2.5 w-2.5 transition-all ${highOnly ? "left-3.5 bg-accent" : "left-0.5 bg-neutral-500"}`} />
            </span>
            Yalnızca Yüksek Etki
          </button>
        </div>

        {activeSymbol && (
          <div className="flex items-center gap-2 border-b hairline px-4 py-2 text-[12px] text-neutral-400">
            Gösterge süzgeci: <span className="num text-accent">{activeSymbol}</span>
            <span className="text-neutral-600">{activeName}</span>
            <button type="button" onClick={onClearSymbol} className="ml-1 text-neutral-500 hover:text-neutral-100"
              aria-label="Gösterge süzgecini kaldır"><X size={13} /></button>
          </div>
        )}

        {/* Akış satırları */}
        <ul className="scroll-thin max-h-[640px] divide-y divide-neutral-800/70 overflow-y-auto">
          {visible.map((i) => (
            <li key={i.id}>
              <button
                type="button"
                onClick={() => onOpen(i)}
                className="group grid w-full grid-cols-[72px_minmax(0,1fr)_auto] items-start gap-4 px-4 py-3 text-left transition-colors hover:bg-neutral-800/40"
              >
                <span className="num pt-0.5 text-[12px] text-neutral-500">{fmtStamp(i.published, date)}</span>
                <span className="min-w-0">
                  <span className="flex items-start gap-2">
                    {i.impact === "high" && <span className="mt-[7px] h-1.5 w-1.5 shrink-0 bg-accent" aria-label="Yüksek etki" />}
                    <span className="text-[14px] leading-5 text-neutral-100 group-hover:text-white">{i.headline}</span>
                  </span>
                  <span className="mt-1 block truncate text-[12px] text-neutral-500">
                    {i.source}
                    <span className="px-1.5 text-neutral-700">·</span>
                    {CATEGORY_LABEL[i.category]}
                    {i.in_briefing && <><span className="px-1.5 text-neutral-700">·</span><span className="text-neutral-400">bültende</span></>}
                    {i.summary && i.summary !== i.headline && <><span className="px-1.5 text-neutral-700">/</span>{i.summary}</>}
                  </span>
                </span>
                <span className="num pt-0.5 text-right text-[12px] text-neutral-400">
                  {i.tickers.map((t) => `$${t}`).join(" ")}
                </span>
              </button>
            </li>
          ))}
          {visible.length === 0 && (
            <li className="px-4 py-10 text-center text-[13px] text-neutral-500">Süzgeçlere uyan haber yok.</li>
          )}
        </ul>
      </div>
    </section>
  );
}
