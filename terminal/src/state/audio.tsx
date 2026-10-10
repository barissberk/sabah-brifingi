import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

export const RATES = [1, 1.25, 1.5] as const;
export type Rate = (typeof RATES)[number];

interface AudioState {
  /** "real": boru hattının ürettiği ses dosyası, "simulated": dosya yok, zamanlayıcıyla oynatım */
  mode: "real" | "simulated";
  playing: boolean;
  rate: Rate;
  current: number;
  duration: number;
  transcript: string;
  toggle: () => void;
  setRate: (r: Rate) => void;
  seek: (fraction: number) => void;
  /** Dalga formu için anlık frekans seviyeleri (0–1); simülasyonda null */
  readLevels: (bins: number) => number[] | null;
}

const Ctx = createContext<AudioState | null>(null);

export function useAudioBriefing() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AudioProvider eksik");
  return ctx;
}

interface Props {
  url: string | null;
  duration: number | null;
  transcript: string;
  children: ReactNode;
}

export function AudioProvider({ url, duration: initialDuration, transcript, children }: Props) {
  const mode = url ? "real" : "simulated";
  const [playing, setPlaying] = useState(false);
  const [rate, setRateState] = useState<Rate>(1.25);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(initialDuration ?? 60);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const bufRef = useRef<Uint8Array<ArrayBuffer> | null>(null);

  // Gerçek ses öğesi
  useEffect(() => {
    if (!url) return;
    const el = new Audio(url);
    el.preload = "metadata";
    el.playbackRate = 1.25;
    el.onloadedmetadata = () => Number.isFinite(el.duration) && setDuration(el.duration);
    el.ontimeupdate = () => setCurrent(el.currentTime);
    el.onended = () => setPlaying(false);
    el.onpause = () => setPlaying(false);
    el.onplay = () => setPlaying(true);
    audioRef.current = el;
    return () => {
      el.pause();
      audioRef.current = null;
    };
  }, [url]);

  // Simülasyon: dosya yoksa zaman çizelgesi zamanlayıcıyla ilerler
  useEffect(() => {
    if (mode !== "simulated" || !playing) return;
    let last = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setCurrent((c) => {
        const n = c + dt * rate;
        if (n >= duration) {
          setPlaying(false);
          return duration;
        }
        return n;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [mode, playing, rate, duration]);

  const ensureAnalyser = useCallback(() => {
    const el = audioRef.current;
    if (!el || analyserRef.current) return;
    try {
      const ac = new AudioContext();
      const src = ac.createMediaElementSource(el);
      const analyser = ac.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.78;
      src.connect(analyser);
      analyser.connect(ac.destination);
      ctxRef.current = ac;
      analyserRef.current = analyser;
      bufRef.current = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));
    } catch {
      /* Web Audio yoksa dalga formu simüle edilir */
    }
  }, []);

  const toggle = useCallback(() => {
    if (mode === "real") {
      const el = audioRef.current;
      if (!el) return;
      ensureAnalyser();
      void ctxRef.current?.resume();
      if (el.paused) {
        if (el.ended || el.currentTime >= (el.duration || Infinity) - 0.05) el.currentTime = 0;
        void el.play();
      } else {
        el.pause();
      }
    } else {
      setPlaying((p) => {
        if (!p && current >= duration) setCurrent(0);
        return !p;
      });
    }
  }, [mode, ensureAnalyser, current, duration]);

  const setRate = useCallback((r: Rate) => {
    setRateState(r);
    if (audioRef.current) audioRef.current.playbackRate = r;
  }, []);

  const seek = useCallback((fraction: number) => {
    const t = Math.max(0, Math.min(1, fraction)) * duration;
    if (audioRef.current) audioRef.current.currentTime = t;
    setCurrent(t);
  }, [duration]);

  const readLevels = useCallback((bins: number) => {
    const analyser = analyserRef.current;
    const buf = bufRef.current;
    if (!analyser || !buf || !playing) return null;
    analyser.getByteFrequencyData(buf);
    // Konuşma enerjisinin yoğunlaştığı alt-orta bantlar
    const usable = Math.floor(buf.length * 0.6);
    const out: number[] = [];
    for (let i = 0; i < bins; i++) {
      const a = Math.floor((i / bins) * usable);
      const b = Math.max(a + 1, Math.floor(((i + 1) / bins) * usable));
      let sum = 0;
      for (let j = a; j < b; j++) sum += buf[j];
      out.push(sum / (b - a) / 255);
    }
    return out;
  }, [playing]);

  const value = useMemo<AudioState>(() => ({
    mode, playing, rate, current, duration, transcript, toggle, setRate, seek, readLevels,
  }), [mode, playing, rate, current, duration, transcript, toggle, setRate, seek, readLevels]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
