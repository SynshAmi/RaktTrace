import { useEffect, useMemo, useState } from "react";
import { api, type Phone, type PhoneMessage } from "../api";
import { hhmm } from "../format";
import { usePoll } from "../usePoll";

const ROLE_ORDER: Phone["role"][] = ["donor", "staff", "family", "coordinator"];
const ROLE_LABEL: Record<Phone["role"], string> = { donor: "Donors", staff: "Blood-centre staff", family: "Family", coordinator: "Coordinator" };

/** A tapped button's title, from the message that offered it (inbound taps arrive as the button id). */
function replyText(m: PhoneMessage, all: PhoneMessage[]): string {
  for (const o of all) {
    const b = o.buttons.find((x) => x.id === m.body);
    if (b) return b.title;
  }
  return m.body;
}

type Props = { version: number; paused: boolean; run: number; onChanged: () => void };

/** What each participant sees on their phone in the running scenario: the real messages and buttons from the
 *  backend, answered through the same reply endpoint the simulated people use. A Telegram-like view, not Telegram. */
export default function Phones({ version, paused, run, onChanged }: Props) {
  const [own, setOwn] = useState(0);  // bumps after a reply here, so the chat refreshes at once
  const phones = usePoll(api.phones, `phones:${run}`, version + own, undefined, paused);
  const [picked, setPicked] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const list = phones.data ?? [];
  const groups = useMemo(() => ROLE_ORDER.map((role) => ({ role, items: list.filter((p) => p.role === role) }))
    .filter((g) => g.items.length > 0), [list]);
  const selected = list.find((p) => p.id === picked) ?? null;

  // A new scenario or a phone that no longer exists: pick the first donor (or anyone) instead.
  useEffect(() => {
    if (phones.data && !phones.data.some((p) => p.id === picked)) {
      setPicked((phones.data.find((p) => p.role === "donor") ?? phones.data[0])?.id ?? null);
    }
  }, [phones.data, picked]);

  const chat = usePoll(() => (selected ? api.messages(selected.id) : Promise.resolve([] as PhoneMessage[])),
    `chat:${run}:${selected?.id ?? ""}`, version + own, undefined, paused);
  const messages = chat.data ?? [];

  async function send(reply: { button_id: string } | { text: string }) {
    if (!selected || sending) return;
    setSending(true);
    setError(null);
    try {
      await api.reply(selected.id, reply);
      if ("text" in reply) setText("");
      setOwn((n) => n + 1);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="mx-auto max-w-420 px-4 pb-16 sm:px-6">
      <div className="border-b border-line py-4">
        <h1 className="text-xl font-bold">Phones</h1>
        <p className="text-muted">
          What each participant sees in the running scenario: the real messages and buttons the agent sent. A Telegram-like
          simulation; tapping here answers for that participant through the simulation.
        </p>
      </div>

      <div className="mt-6 grid gap-8 md:grid-cols-[18rem_minmax(0,1fr)]">
        <nav aria-label="Participants" className="space-y-5">
          {phones.error && <p className="text-danger">Couldn't load phones: {phones.error}</p>}
          {!phones.data && !phones.error && <p className="text-muted">Loading phones…</p>}
          {phones.data && groups.length === 0 && <p className="text-muted">No messages yet. Step the scenario to start.</p>}
          {groups.map((g) => (
            <div key={g.role}>
              <h2 className="text-xs font-bold uppercase tracking-wider text-muted">{ROLE_LABEL[g.role]} ({g.items.length})</h2>
              <ul className="mt-1.5 space-y-1">
                {g.items.map((p) => (
                  <li key={p.id}>
                    <button
                      onClick={() => setPicked(p.id)}
                      aria-current={p.id === picked}
                      className={`flex w-full items-center justify-between rounded-md px-3 py-1.5 text-left ${p.id === picked
                        ? "bg-tab/15 font-semibold" : "hover:bg-text/5"}`}
                    >
                      <span className="truncate">{p.name}</span>
                      {p.unread > 0 && <span className="ml-2 rounded-full bg-tab px-2 text-xs font-bold text-white">{p.unread}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <section aria-label="Phone" className="flex justify-center md:justify-start">
          {selected && (
            <div className="flex h-[40rem] w-full max-w-sm flex-col overflow-hidden rounded-[2rem] border-4 border-line-strong bg-[#0e1621] text-white shadow-xl">
              <div className="flex items-center gap-3 bg-[#17212b] px-4 py-3">
                <div className="grid h-9 w-9 place-items-center rounded-full bg-[#5288c1] font-bold">R</div>
                <div className="min-w-0">
                  <div className="truncate font-semibold">RaktTrace bot</div>
                  <div className="truncate text-xs text-[#8ea1b3]">on {selected.name}'s phone · {selected.role}</div>
                </div>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto px-3 py-3" aria-live="polite">
                {chat.error && <p className="text-sm text-[#f28b82]">Couldn't load messages: {chat.error}</p>}
                {!chat.data && !chat.error && <p className="text-sm text-[#8ea1b3]">Loading…</p>}
                {chat.data && messages.length === 0 && <p className="text-sm text-[#8ea1b3]">No messages for this participant yet.</p>}
                {messages.map((m) => m.direction === "out" ? (
                  <div key={m.id} className="max-w-[85%]">
                    <div className="whitespace-pre-wrap rounded-2xl rounded-tl-sm bg-[#182533] px-3 py-2 text-sm">
                      {m.body}
                      <div className="mt-1 text-right text-[10px] text-[#8ea1b3]">{hhmm(m.at)}{m.channel === "telegram" && " · sent on Telegram"}</div>
                    </div>
                    {m.buttons.length > 0 && (
                      <div className="mt-1 grid gap-1">
                        {m.buttons.map((b) => (
                          <button key={b.id} onClick={() => send({ button_id: b.id })} disabled={sending}
                            className="rounded-lg bg-[#2b5278] px-3 py-1.5 text-sm font-semibold hover:bg-[#35648f] disabled:opacity-50">
                            {b.title}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div key={m.id} className="ml-auto max-w-[85%] rounded-2xl rounded-tr-sm bg-[#2b5278] px-3 py-2 text-sm">
                    {replyText(m, messages)}
                    <div className="mt-1 text-right text-[10px] text-[#b3c7da]">
                      {hhmm(m.at)}{m.read_by && ` · read by ${m.read_by}`}
                    </div>
                  </div>
                ))}
              </div>
              {error && <p className="bg-[#3a1d1d] px-3 py-1 text-xs text-[#f28b82]">{error}</p>}
              <form className="flex gap-2 bg-[#17212b] p-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send({ text: text.trim() }); }}>
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a reply…" aria-label="Reply"
                  className="min-w-0 flex-1 rounded-full bg-[#242f3d] px-3 py-1.5 text-sm text-white placeholder:text-[#8ea1b3]" />
                <button type="submit" disabled={sending || !text.trim()}
                  className="rounded-full bg-[#5288c1] px-4 text-sm font-semibold disabled:opacity-50">Send</button>
              </form>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
