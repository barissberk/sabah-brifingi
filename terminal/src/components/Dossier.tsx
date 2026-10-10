import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Pause, Play } from "lucide-react";
import type { Pillar, Pivot } from "../types";
import { RATES, useAudioBriefing } from "../state/audio";
import { fmtDuration, fmtNum } from "../lib/format";
import { SampleNote } from "./SampleNote";

const BARS = 64;

/** Oynatımla eşzamanlı dalga formu: gerçek seste Web Audio frekans verisi, aksi halde simülasyon. */
function Waveform() {
  const audio = useAudioBriefing();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const state = useRef(audio);
  state.current = audio;
  // Duraklatılmış haldeki sabit siluet
  const envelope = useMemo(
    () => Array.from({ length: BARS }, (_, i) => 0.18 + 0.5 * Math.abs(Math.sin(i * 0.37) * Math.cos(i * 0.11))),
    [],
  );
  const smooth = useRef<number[]>(envelope.map((e) => e * 0.6));

  useEffect(() => {
    const canvas = canvasRef.current!;
    const g = canvas.getContext("2d")!;
    let raf = 0;
    const draw = (now: number) => {
      const { playing, current, duration, readLevels } = state.current;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);

      const real = readLevels(BARS);
      const target = real
        ? real.map((v) => 0.08 + Math.min(1, v * 1.35))
        : envelope.map((e, i) =>
          playing ? 0.12 + e * (0.55 + 0.45 * Math.abs(Math.sin(now / 140 + i * 0.9) * Math.sin(now / 410 + i * 0.23))) : e * 0.6);
      smooth.current = smooth.current.map((s, i) => s + (target[i] - s) * (playing ? 0.35 : 0.08));

      const gap = 2;
      const bw = (w - gap * (BARS - 1)) / BARS;
      const progress = duration ? current / duration : 0;
      smooth.current.forEach((v, i) => {
        const bh = Math.max(2, v * h);
        const played = i / BARS < progress;
        g.fillStyle = played ? "#fbbf24" : playing ? "#525252" : "#3f3f46";
        g.fillRect(i * (bw + gap), (h - bh) / 2, bw, bh);
      });
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [envelope]);

  return (
    <canvas
      ref={canvasRef}
      className="h-16 w-full cursor-pointer"
      aria-label="Ses dalga formu; tıklayarak konuma atlayın"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        audio.seek((e.clientX - r.left) / r.width);
      }}
    />
  );
}

/** Konuşma metni: oynatım konumuna göre o an okunan cümle vurgulanır (karakter uzunluğuyla orantılı). */
function Transcript() {
  const { transcript, current, duration } = useAudioBriefing();
  const sentences = useMemo(() => transcript.match(/[^.!?]+[.!?]+/g)?.map((s) => s.trim()) ?? [transcript], [transcript]);
  const bounds = useMemo(() => {
    const total = sentences.reduce((a, s) => a + s.length, 0) || 1;
    let acc = 0;
    return sentences.map((s) => (acc += s.length) / total);
  }, [sentences]);
  const p = duration ? current / duration : 0;
  const idx = current > 0 ? bounds.findIndex((b) => p <= b) : -1;

  return (
    <p className="text-[13px] leading-6 text-neutral-500">
      {sentences.map((s, i) => (
        <span key={i} className={i === idx ? "text-neutral-100" : i < idx ? "text-neutral-400" : undefined}>
          {s}{" "}
        </span>
      ))}
    </p>
  );
}

function AudioPlayer({ isSample }: { isSample: boolean }) {
  const audio = useAudioBriefing();
  const [open, setOpen] = useState(false);

  return (
    <div className="surface flex flex-col p-5">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="text-[15px] font-semibold text-neutral-50">Açılış Brifingi</h3>
        <span className="text-[11px] text-neutral-500">
          {audio.mode === "real" ? "Yapay zekâ spiker · Gemini TTS" : "Ses dosyası yok · zamanlayıcı ile oynatım"}
          {isSample && <> <span className="text-neutral-700">·</span> <span className="text-accent">örnek</span></>}
        </span>
      </div>

      <div className="mt-4">
        <Waveform />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <button
          type="button"
          onClick={audio.toggle}
          aria-label={audio.playing ? "Duraklat" : "Oynat"}
          className="flex h-10 w-10 items-center justify-center bg-accent text-neutral-950 transition-opacity hover:opacity-90"
        >
          {audio.playing ? <Pause size={18} strokeWidth={2.5} /> : <Play size={18} strokeWidth={2.5} className="ml-0.5" />}
        </button>
        <span className="num whitespace-nowrap text-[13px] text-neutral-300">
          {fmtDuration(audio.current)} <span className="text-neutral-600">/ {fmtDuration(audio.duration)}</span>
        </span>
        <div role="group" aria-label="Oynatma hızı" className="ml-auto flex border hairline">
          {RATES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => audio.setRate(r)}
              aria-pressed={audio.rate === r}
              className={`num px-2.5 py-1 text-[12px] transition-colors ${
                audio.rate === r ? "bg-neutral-800 text-accent" : "text-neutral-500 hover:text-neutral-200"
              }`}
            >
              {r.toFixed(r === 1 ? 1 : 2)}x
            </button>
          ))}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="mt-4 flex items-center gap-1.5 self-start text-[12px] text-neutral-400 hover:text-neutral-100"
      >
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        Spiker metni
      </button>
      {open && (
        <div className="scroll-thin mt-3 max-h-56 overflow-y-auto border-t hairline pt-3">
          <Transcript />
        </div>
      )}
    </div>
  );
}

function Pillars({ pillars, isSample }: { pillars: Pillar[]; isSample: boolean }) {
  return (
    <div className="surface p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-semibold text-neutral-50">Sabahın 3 Kritik Ekseni</h3>
        {isSample && <SampleNote />}
      </div>
      <ol className="mt-4 grid gap-5 lg:grid-cols-3">
        {pillars.slice(0, 3).map((p, i) => (
          <li key={i} className="border-t hairline pt-3">
            <div className="flex items-baseline gap-2">
              <span className="num text-[12px] text-accent">{i + 1}</span>
              <h4 className="text-[14px] font-medium leading-5 text-neutral-100">{p.title}</h4>
            </div>
            <p className="mt-2 text-[13px] leading-[1.6] text-neutral-400">{p.body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PivotStrip({ pivot, last, isSample }: { pivot: Pivot; last: number | null; isSample: boolean }) {
  const levels = [
    { k: "S2", v: pivot.s2 }, { k: "S1", v: pivot.s1 }, { k: "Pivot", v: pivot.pivot },
    { k: "R1", v: pivot.r1 }, { k: "R2", v: pivot.r2 },
  ];
  const lo = pivot.s2 - (pivot.r2 - pivot.s2) * 0.08;
  const hi = pivot.r2 + (pivot.r2 - pivot.s2) * 0.08;
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100))}%`;

  return (
    <div className="surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-neutral-100">
          {pivot.symbol === "XU100" ? "BIST 100" : pivot.symbol} teknik pivot
        </h3>
        <span className="text-[11px] text-neutral-500">
          Klasik pivot <span className="text-neutral-700">·</span> {pivot.basis}
          {isSample && <> <span className="text-neutral-700">·</span> <span className="text-accent">örnek</span></>}
        </span>
      </div>
      {/* Yan boşluk: uçtaki etiketler (S2/R2) kartın dışına taşmasın */}
      <div className="relative mx-7 mt-6 h-14 sm:h-10">
        <div className="absolute inset-x-0 top-3 h-px bg-neutral-800" />
        {levels.map((l, i) => (
          <div key={l.k} className="absolute top-0 -translate-x-1/2 text-center" style={{ left: pos(l.v) }}>
            <div className={`mx-auto h-[13px] w-px ${l.k === "Pivot" ? "bg-accent" : l.k.startsWith("R") ? "bg-rose-400/70" : "bg-emerald-400/70"}`} />
            {/* Dar ekranda S1/R1 bir alt satıra iner, etiketler çakışmaz */}
            <div className={`mt-1.5 whitespace-nowrap text-[11px] ${i % 2 === 1 ? "max-sm:mt-6" : ""}`}>
              <span className={l.k === "Pivot" ? "text-accent" : "text-neutral-500"}>{l.k}</span>{" "}
              <span className="num text-neutral-200">{fmtNum(l.v, 0)}</span>
            </div>
          </div>
        ))}
        {last != null && (
          <div className="absolute -top-4 -translate-x-1/2 transition-[left] duration-300" style={{ left: pos(last) }}
            title="Son değer">
            <div className="num whitespace-nowrap text-[10px] text-neutral-100">{fmtNum(last, 0)}</div>
            <div className="mx-auto h-0 w-0 border-x-4 border-t-[5px] border-x-transparent border-t-neutral-100" />
          </div>
        )}
      </div>
    </div>
  );
}

interface DossierProps {
  pillars: Pillar[];
  pivot: Pivot | null;
  lastIndex: number | null;
  sample: { pillars: boolean; pivot: boolean; audio: boolean };
}

export function Dossier({ pillars, pivot, lastIndex, sample }: DossierProps) {
  return (
    <section id="brifing" className="scroll-mt-28">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-neutral-50">08:30 Açılış Dosyası</h2>
        <span className="label">Sabah brifingi</span>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <AudioPlayer isSample={sample.audio} />
        <div className="flex flex-col gap-4">
          <Pillars pillars={pillars} isSample={sample.pillars} />
          {pivot && <PivotStrip pivot={pivot} last={lastIndex} isSample={sample.pivot} />}
        </div>
      </div>
    </section>
  );
}
