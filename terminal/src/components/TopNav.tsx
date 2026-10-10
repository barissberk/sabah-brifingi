import { FileDown, Pause, Play } from "lucide-react";
import { useAudioBriefing } from "../state/audio";
import { fmtDuration, fmtLongDate } from "../lib/format";

export const NAV = [
  { id: "brifing", label: "Sabah Brifingi" },
  { id: "akis", label: "Piyasa Akışı" },
  { id: "takvim", label: "Makro Takvim" },
  { id: "analist", label: "Analist Masası" },
] as const;

interface Props {
  date: string;
  active: string;
  onNavigate: (id: string) => void;
  onDesign: () => void;
  onExport: () => void;
}

export function TopNav({ date, active, onNavigate, onDesign, onExport }: Props) {
  const audio = useAudioBriefing();
  const remaining = audio.duration / audio.rate - audio.current / audio.rate;

  return (
    <header className="sticky top-0 z-30 border-b hairline bg-canvas/90 backdrop-blur">
      <div className="mx-auto grid h-14 max-w-[1440px] grid-cols-[auto_1fr_auto] items-center gap-3 px-4 sm:gap-6 sm:px-6">
        {/* Sol: marka + oturum */}
        <div className="flex min-w-0 items-baseline gap-4">
          <span className="whitespace-nowrap text-[14px] font-semibold tracking-[0.14em] text-neutral-50 sm:text-[15px] sm:tracking-[0.18em]">AURA<span className="hidden sm:inline"> TERMINAL</span></span>
          <span className="hidden whitespace-nowrap text-xs text-neutral-500 lg:inline">
            <span className="num text-accent">08:30</span> SABAH MASASI
            <span className="hidden 2xl:inline"><span className="px-1 text-neutral-700">·</span>{fmtLongDate(date)}</span>
          </span>
        </div>

        {/* Orta: gezinme */}
        <nav aria-label="Bölümler" className="hidden items-center justify-center gap-1 md:flex">
          {NAV.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => onNavigate(n.id)}
              aria-current={active === n.id ? "true" : undefined}
              className={`relative px-3 py-2 text-[13px] transition-colors ${
                active === n.id ? "text-neutral-50" : "text-neutral-400 hover:text-neutral-100"
              }`}
            >
              {n.label}
              {active === n.id && <span className="absolute inset-x-3 -bottom-[9px] h-px bg-accent" />}
            </button>
          ))}
          <button type="button" onClick={onDesign}
            className="px-3 py-2 text-[13px] text-neutral-400 transition-colors hover:text-neutral-100">
            Tasarım Mimarisi
          </button>
        </nav>

        {/* Sağ: birincil eylemler */}
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={audio.toggle}
            aria-pressed={audio.playing}
            aria-label="Sesli brifing"
            className="flex h-8 items-center gap-2 whitespace-nowrap border border-accent/40 bg-accent/10 px-3 text-[13px] font-medium text-accent transition-colors hover:bg-accent/15"
          >
            {audio.playing ? <Pause size={14} strokeWidth={2.25} /> : <Play size={14} strokeWidth={2.25} />}
            <span className="hidden sm:inline">Sesli Brifing</span>
            <span className="num text-accent/80">({fmtDuration(audio.playing ? remaining : audio.duration / audio.rate)})</span>
          </button>
          <button
            type="button"
            onClick={onExport}
            aria-label="Notu aktar"
            className="flex h-8 items-center gap-2 border hairline px-3 text-[13px] text-neutral-300 transition-colors hover:border-neutral-600 hover:text-neutral-50"
          >
            <FileDown size={14} />
            <span className="hidden sm:inline">Notu Aktar</span>
          </button>
        </div>
      </div>
    </header>
  );
}
