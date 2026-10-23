import type { ReactNode } from "react";
import { toneText, type Tone } from "../format";

type Props = { title: string; note?: string; status: string; tone: Tone; detail?: string; children: ReactNode };

/** One lane of the request view: who it is, its status word, then its content. */
export default function Lane({ title, note, status, tone, detail, children }: Props) {
  return (
    <section>
      <div className="flex items-baseline gap-3">
        <h2 className="text-lg text-muted">{title}</h2>
        {note && <span className="text-sm text-faint">{note}</span>}
      </div>
      <div className={`mt-1 text-5xl font-semibold tracking-tight ${toneText[tone]}`}>{status}</div>
      {detail && <p className="mt-2 max-w-2xl text-lg text-muted">{detail}</p>}
      <div className="mt-8 space-y-10">{children}</div>
    </section>
  );
}
