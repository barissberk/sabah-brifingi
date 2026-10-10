/** Örnek (demo) veriyle doldurulan bölümler için kutusuz, sade işaret. */
export function SampleNote({ text = "Örnek veri" }: { text?: string }) {
  return <span className="text-[11px] text-accent">{text}</span>;
}
