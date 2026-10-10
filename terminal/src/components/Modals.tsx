import { useEffect, useState, type ReactNode } from "react";
import { Check, Copy, Download, X } from "lucide-react";

function Modal({ title, onClose, children, wide = false }: {
  title: string; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Kapat" onClick={onClose} className="absolute inset-0 bg-black/70" />
      <div className={`relative flex max-h-[88vh] w-full flex-col border hairline bg-neutral-950 ${wide ? "max-w-3xl" : "max-w-2xl"}`}>
        <div className="flex items-center justify-between border-b hairline px-5 py-3.5">
          <h2 className="text-[15px] font-semibold text-neutral-50">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Kapat" className="text-neutral-500 hover:text-neutral-100"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ExportModal({ memo, date, onClose }: { memo: string; date: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(memo);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([memo], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `aura-sabah-notu-${date}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Modal title="Sabah notunu aktar" onClose={onClose} wide>
      <pre className="scroll-thin num m-0 flex-1 overflow-auto whitespace-pre px-5 py-4 text-[12px] leading-5 text-neutral-300">{memo}</pre>
      <div className="flex items-center justify-end gap-2 border-t hairline px-5 py-3">
        <button type="button" onClick={copy}
          className="flex h-8 items-center gap-2 border hairline px-3 text-[13px] text-neutral-200 hover:border-neutral-600">
          {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
          {copied ? "Kopyalandı" : "Panoya kopyala"}
        </button>
        <button type="button" onClick={download}
          className="flex h-8 items-center gap-2 bg-accent px-3 text-[13px] font-medium text-neutral-950 hover:opacity-90">
          <Download size={14} /> .txt indir
        </button>
      </div>
    </Modal>
  );
}

const SWATCHES = [
  { name: "Tuval · %60", value: "#09090b", cls: "bg-[#09090b] border hairline" },
  { name: "Yüzey · %30", value: "neutral-900/60 + neutral-800", cls: "bg-neutral-900 border border-neutral-700" },
  { name: "Vurgu · %10", value: "#fbbf24", cls: "bg-accent" },
  { name: "Yükseliş", value: "emerald-400 + ▲", cls: "bg-emerald-400" },
  { name: "Düşüş", value: "rose-400 + ▼", cls: "bg-rose-400" },
];

export function DesignModal({ onClose }: { onClose: () => void }) {
  const rules = [
    ["Meta veri", "Tarih, kaynak ve kategori kutusuz düz metindir; ayraç olarak · ve / kullanılır. Kapsül rozet yoktur. Düğmeler yalnızca etkileşimli öğelerdir."],
    ["Tipografi", "Başlık ve metin Plus Jakarta Sans; tüm fiyat, yüzde, baz puan ve saatler JetBrains Mono, eşit genişlikli rakamlarla (tabular-nums) — canlı güncellemede kayma olmaz."],
    ["Renk", "60-30-10 dağılımı. Kehribar yalnızca odak noktalarında. Yeşil/kırmızı her zaman yön okuyla birlikte kullanılır; renk tek başına anlam taşımaz."],
    ["Veri kökeni", "Gerçek veri ile örnek veri her bölümde ayrı belirtilir. Simüle edilen tikler önceki kapanışa göre ortalamaya döner ve şeritte “simülasyon” olarak işaretlenir."],
    ["Sadelik", "Sahte sistem telemetrisi, kod yorumu biçimli başlıklar veya süs amaçlı skorlar yoktur."],
  ];
  return (
    <Modal title="Tasarım Mimarisi" onClose={onClose}>
      <div className="scroll-thin overflow-y-auto px-5 py-4">
        <div className="grid grid-cols-5 gap-3">
          {SWATCHES.map((s) => (
            <div key={s.name}>
              <div className={`h-10 ${s.cls}`} />
              <div className="mt-1.5 text-[12px] text-neutral-200">{s.name}</div>
              <div className="num text-[11px] text-neutral-500">{s.value}</div>
            </div>
          ))}
        </div>
        <dl className="mt-6 divide-y divide-neutral-800">
          {rules.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[120px_1fr] gap-4 py-3">
              <dt className="text-[13px] font-medium text-neutral-100">{k}</dt>
              <dd className="text-[13px] leading-6 text-neutral-400">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 flex items-baseline gap-6 border-t hairline pt-4">
          <span className="text-[22px] font-semibold text-neutral-50">Aa Jakarta</span>
          <span className="num text-[22px] text-neutral-50">12.265,98 ▲ 0,43%</span>
        </div>
      </div>
    </Modal>
  );
}
