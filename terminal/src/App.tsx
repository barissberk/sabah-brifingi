import { useCallback, useEffect, useMemo, useState } from "react";
import type { SampleFlags, WireItem } from "./types";

const SAMPLE_LABEL: Record<keyof SampleFlags, string> = {
  tickers: "piyasa göstergeleri", pivot: "teknik pivot", sectors: "sektör nabzı", pillars: "kritik eksenler",
  audio: "sesli brifing", wire: "piyasa akışı", calendar: "makro takvim", analyst: "analist masası",
};
import { loadTerminalData, type LoadedData } from "./data/load";
import { AudioProvider } from "./state/audio";
import { useTickerFeed } from "./state/useTickerFeed";
import { buildMemo } from "./lib/memo";
import { NAV, TopNav } from "./components/TopNav";
import { TickerRibbon } from "./components/TickerRibbon";
import { Dossier } from "./components/Dossier";
import { MarketWire } from "./components/MarketWire";
import { NewsDrawer } from "./components/NewsDrawer";
import { MacroCalendar } from "./components/MacroCalendar";
import { AnalystDesk } from "./components/AnalystDesk";
import { DesignModal, ExportModal } from "./components/Modals";

function useActiveSection() {
  const [active, setActive] = useState<string>(NAV[0].id);
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-120px 0px -55% 0px" },
    );
    NAV.forEach((n) => {
      const el = document.getElementById(n.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  });
  return active;
}

function Terminal({ loaded }: { loaded: LoadedData }) {
  const { data, sample } = loaded;
  const [simulating, setSimulating] = useState(true);
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [openItem, setOpenItem] = useState<WireItem | null>(null);
  const [modal, setModal] = useState<"export" | "design" | null>(null);
  const live = useTickerFeed(data.tickers, simulating);
  const active = useActiveSection();

  const navigate = useCallback((id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const selectSymbol = useCallback((s: string | null) => {
    setActiveSymbol(s);
    if (s) navigate("akis");
  }, [navigate]);

  const sampleParts = (Object.keys(SAMPLE_LABEL) as (keyof SampleFlags)[]).filter((k) => sample[k]).map((k) => SAMPLE_LABEL[k]);
  const memo = useMemo(
    () => (modal === "export"
      ? buildMemo(data, sampleParts.length ? `Şu bölümler örnek veri içerir: ${sampleParts.join(", ")}.` : null)
      : ""),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [modal],
  );
  const xu100 = live.XU100?.value ?? data.tickers.find((t) => t.symbol === "XU100")?.value ?? null;

  return (
    <>
      <TopNav date={data.date} active={active} onNavigate={navigate}
        onDesign={() => setModal("design")} onExport={() => setModal("export")} />
      <TickerRibbon tickers={data.tickers} live={live} activeSymbol={activeSymbol} onSelect={selectSymbol}
        simulating={simulating} onToggleSim={() => setSimulating((s) => !s)} isSample={sample.tickers} />

      <main className="mx-auto flex max-w-[1440px] flex-col gap-10 px-4 py-6 sm:px-6 sm:py-8">
        {loaded.error && (
          <p className="border-l-2 border-accent pl-3 text-[13px] text-neutral-400">
            {loaded.error}. Tüm bölümler örnek veriyle gösteriliyor; boru hattını çalıştırın:{" "}
            <span className="num text-neutral-200">python main.py --now</span>
          </p>
        )}
        <Dossier pillars={data.pillars} pivot={data.pivot} lastIndex={xu100} sample={sample} />
        <MarketWire items={data.wire} date={data.date} tickers={data.tickers} activeSymbol={activeSymbol}
          onClearSymbol={() => setActiveSymbol(null)} onOpen={setOpenItem} isSample={sample.wire} />
        <MacroCalendar events={data.calendar} date={data.date} isSample={sample.calendar} />
        <AnalystDesk rows={data.analyst_desk.rows} sectors={data.sectors} sample={sample} />
      </main>

      <footer className="border-t hairline">
        <div className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-2 px-4 py-5 text-[11px] text-neutral-500 sm:px-6">
          <span>
            Veri üretimi <span className="num">{new Date(data.generated_at).toLocaleString("tr-TR", { timeZone: "Europe/Istanbul" })}</span>
            <span className="px-1.5 text-neutral-700">·</span>Kaynaklar: {data.sources.join(", ")}
          </span>
          <span>Bilgilendirme amaçlıdır; yatırım tavsiyesi değildir.</span>
        </div>
      </footer>

      <NewsDrawer item={openItem} date={data.date} tickers={data.tickers} onClose={() => setOpenItem(null)}
        onSelectAsset={(s) => { setOpenItem(null); selectSymbol(s); }} />
      {modal === "export" && <ExportModal memo={memo} date={data.date} onClose={() => setModal(null)} />}
      {modal === "design" && <DesignModal onClose={() => setModal(null)} />}
    </>
  );
}

export default function App() {
  const [loaded, setLoaded] = useState<LoadedData | null>(null);
  useEffect(() => {
    void loadTerminalData().then(setLoaded);
  }, []);

  if (!loaded) {
    return <div className="flex h-screen items-center justify-center text-[13px] text-neutral-500">Sabah masası yükleniyor…</div>;
  }
  const a = loaded.data.audio;
  return (
    <AudioProvider url={a?.url ?? null} duration={a?.duration ?? null} transcript={a?.transcript ?? ""}>
      <Terminal loaded={loaded} />
    </AudioProvider>
  );
}
