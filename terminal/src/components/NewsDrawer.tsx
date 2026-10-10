import { useEffect } from "react";
import { ExternalLink, X } from "lucide-react";
import type { Ticker, WireItem } from "../types";
import { CATEGORY_LABEL, CONTEXT_TICKERS, DIR_TEXT, direction, fmtChange, fmtNum, fmtStamp } from "../lib/format";

interface Props {
  item: WireItem | null;
  date: string;
  tickers: Ticker[];
  onClose: () => void;
  onSelectAsset: (symbol: string) => void;
}

export function NewsDrawer({ item, date, tickers, onClose, onSelectAsset }: Props) {
  useEffect(() => {
    if (!item) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  if (!item) return null;
  const context = CONTEXT_TICKERS[item.category]
    .map((s) => tickers.find((t) => t.symbol === s))
    .filter((t): t is Ticker => Boolean(t));
  const shownSymbols = item.tickers.filter((t) => tickers.every((x) => x.symbol !== t)); // hisse etiketleri

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <button type="button" aria-label="Kapat" onClick={onClose} className="absolute inset-0 bg-black/60" />
      <aside className="scroll-thin relative h-full w-full max-w-[560px] overflow-y-auto border-l hairline bg-neutral-950 px-7 py-6">
        <div className="flex items-start justify-between gap-4">
          <p className="text-[12px] text-neutral-500">
            <span className="num">{fmtStamp(item.published, date)}</span>
            <span className="px-1.5 text-neutral-700">·</span>{item.source}
            <span className="px-1.5 text-neutral-700">·</span>{CATEGORY_LABEL[item.category]}
            {item.impact === "high" && <><span className="px-1.5 text-neutral-700">·</span><span className="text-accent">yüksek etki</span></>}
          </p>
          <button type="button" onClick={onClose} aria-label="Kapat" className="text-neutral-500 hover:text-neutral-100">
            <X size={18} />
          </button>
        </div>

        <h2 id="drawer-title" className="mt-3 text-[20px] font-semibold leading-7 text-neutral-50">{item.headline}</h2>

        <section className="mt-6">
          <h3 className="label">Özet</h3>
          <p className="mt-2 text-[14px] leading-6 text-neutral-300">{item.summary || item.headline}</p>
        </section>

        {item.take && (
          <section className="mt-6 border-l border-accent/60 pl-4">
            <h3 className="label">Kurumsal konumlanma</h3>
            <p className="mt-2 text-[14px] leading-6 text-neutral-200">{item.take}</p>
          </section>
        )}

        {item.commentary && (
          <section className="mt-6">
            <h3 className="label">Analist yorumu</h3>
            <p className="mt-2 text-[14px] leading-6 text-neutral-300">{item.commentary}</p>
          </section>
        )}

        <section className="mt-6">
          <h3 className="label">{item.figures.length ? "Kritik rakamlar" : "Bağlam göstergeleri · önceki kapanış"}</h3>
          <table className="mt-2 w-full text-[13px]">
            <tbody className="divide-y divide-neutral-800">
              {item.figures.length
                ? item.figures.map((f) => (
                  <tr key={f.label}>
                    <td className="py-2 text-neutral-400">{f.label}</td>
                    <td className="num py-2 text-right text-neutral-100">{f.value}</td>
                  </tr>
                ))
                : context.map((t) => {
                  // Simüle tikler değil, önceki kapanış verisi
                  const v = t.value;
                  const c = t.change;
                  return (
                    <tr key={t.symbol}>
                      <td className="py-2 text-neutral-400">{t.name}</td>
                      <td className="num py-2 text-right text-neutral-100">
                        {t.kind === "rate" && v != null ? `%${fmtNum(v, t.decimals)}` : fmtNum(v, t.decimals)}
                      </td>
                      <td className={`num w-28 py-2 text-right ${DIR_TEXT[direction(c)]}`}>{fmtChange(c, t.change_unit)}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </section>

        {shownSymbols.length > 0 && (
          <section className="mt-6">
            <h3 className="label">İlgili varlıklar</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              {shownSymbols.map((s) => (
                <button key={s} type="button" onClick={() => onSelectAsset(s)}
                  title="Akışı bu varlığa göre süz"
                  className="num border hairline px-2 py-1 text-[12px] text-neutral-200 transition-colors hover:border-accent hover:text-accent">
                  ${s}
                </button>
              ))}
            </div>
          </section>
        )}

        {item.url && (
          <a href={item.url} target="_blank" rel="noreferrer"
            className="mt-8 inline-flex items-center gap-1.5 text-[13px] text-accent hover:underline">
            Kaynağı aç <ExternalLink size={13} />
          </a>
        )}
      </aside>
    </div>
  );
}
