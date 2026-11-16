// Live events, part 1 (owner, 16 November 2026): Work → Live events.
//
// Three evenings a week (Monday, Wednesday and Friday at 20:00 Lagos time) something happens in the shared world at once
// for everybody, and for thirty minutes every empire competes on how it reads and handles it. This page counts down to
// the bell, shows the event as it runs (the story, the featured share, the table), takes each member's own sealed
// prediction in the first ten minutes (the empire's closest counts), lets the head leave a standing plan, and keeps the past events with their scores.
// Every figure comes from the server; the countdown is the server's time, ticked on between visits.
// Part 2 (16 November 2026): the page is told the moment something changes (the bell, a prediction, a chat message, the
// plan, the scores) and loads itself again; the empire's War Room chat is on the page, so members can talk it over here.

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type LiveEvent, type LivePage, type Player } from "./api";
import { asKobo } from "./Empire";
import { formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { useLivePushes } from "./pushes";
import { Band, BandCell, Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void };

const pct = (bps: number | null | undefined) => (bps === null || bps === undefined ? "—" : formatPercent(bps, 1));
const signedPct = (bps: number) => `${bps > 0 ? "+" : bps < 0 ? "−" : ""}${(Math.abs(bps) / 100).toFixed(1)}%`;
const tone = (bps: number) => (bps > 0 ? "change-up" : bps < 0 ? "change-down" : "");

/** The server's time, ticking every second between loads. */
export function useServerNow(serverNow: string | undefined): number {
  const offset = useRef(0);
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    if (serverNow) offset.current = new Date(serverNow).getTime() - Date.now();
  }, [serverNow]);
  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return tick + offset.current;
}

/** "2d 4h", "3h 12m", "12:05": how long until a moment. */
export function untilWords(ms: number): string {
  if (ms <= 0) return "now";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function whenWords(iso: string): string {
  return new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "long", hour: "2-digit", minute: "2-digit" });
}

function useAct(reload: () => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(ask: () => Promise<LivePage>, done: string) {
    setBusy(true); setError(null); setNotice(null);
    try {
      await ask();
      setNotice(done);
      reload();
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
type Act = ReturnType<typeof useAct>;

function Prediction({ event, act }: { event: LiveEvent; act: Act }) {
  const [move, setMove] = useState("");
  const value = Number(move.replace(/[%+\s]/g, "").replace("−", "-"));
  const ok = move.trim() !== "" && Number.isFinite(value) && Math.abs(value) <= 50;
  return (
    <form className="live-predict" onSubmit={(e) => {
      e.preventDefault();
      if (ok) act.run(() => api.livePredict({ event_id: event.id, move_bps: Math.round(value * 100) }), "Your prediction is in, sealed.");
    }}>
      <label htmlFor="live-move">How far will {event.featured.ticker} move from the bell to the end?</label>
      <div className="live-predict-row">
        <input id="live-move" className="mono" inputMode="decimal" placeholder="e.g. −4.5 or 2" value={move} onChange={(e) => setMove(e.target.value)} />
        <span className="muted">%</span>
        <button type="submit" className="button-primary" disabled={!ok || act.busy}>Seal the prediction</button>
      </div>
      <p className="small muted">Every member makes their own; your empire's closest counts. Your own empire's members can see it, to talk it over; rivals see nothing until the event is scored. One each, and it cannot be changed.</p>
    </form>
  );
}

function Members({ event }: { event: LiveEvent }) {
  if (event.your_members.length === 0) return null;
  return (
    <div className="live-members small">
      <span className="muted">Your empire's predictions{event.status === "open" ? " (only your empire sees these)" : ""}:</span>
      {event.your_members.map((m, i) => (
        <span key={i} className="live-chip">{m.name} <span className="mono">{signedPct(m.prediction_bps)}</span>{m.miss_bps !== null && <span className="muted"> · missed {pct(m.miss_bps)}</span>}</span>
      ))}
    </div>
  );
}

function Table({ event, running }: { event: LiveEvent; running: boolean }) {
  return (
    <div className="live-table-wrap">
    <table className="dense live-table">
      <thead><tr>
        <th scope="col">Empire</th>
        <th scope="col" className="num" title="What the event did to its money: the shares it touched, held and traded, against what the empire was worth at the bell">Result</th>
        <th scope="col" className="num" title="The empire's closest prediction counts. While the event runs, only how many members have predicted is shown">Prediction</th>
        {!running && <th scope="col" className="num">Missed by</th>}
        {!running && <th scope="col" className="num">Points</th>}
      </tr></thead>
      <tbody>{event.table.map((r) => (
        <tr key={r.empire} className={r.yours ? "live-yours" : ""}>
          <th scope="row">{r.empire}{r.run_by === "the computer" && <span className="muted small live-computer"> · computer</span>}</th>
          <td className={`num mono ${tone(r.result_bps)}`}>{signedPct(r.result_bps)}{r.result_kobo !== null && <span className="muted small"> ({r.result_kobo.startsWith("-") ? "−" + formatNaira(r.result_kobo.slice(1)) : formatNaira(r.result_kobo)})</span>}</td>
          <td className="num mono">{r.prediction_bps !== null
            ? <>{signedPct(r.prediction_bps)}{r.counted_by && <span className="muted small"> by {r.counted_by}</span>}</>
            : r.predicted ? `● ${r.predictions > 1 ? `${r.predictions} sealed` : "sealed"}` : "—"}</td>
          {!running && <td className="num mono">{r.miss_bps === null ? "—" : pct(r.miss_bps)}</td>}
          {!running && <td className="num"><strong>{r.points ?? 0}</strong></td>}
        </tr>
      ))}</tbody>
    </table>
    </div>
  );
}

function LiveNow({ d, event, now, act }: { d: LivePage; event: LiveEvent; now: number; act: Act }) {
  const left = new Date(event.ends_at).getTime() - now;
  const predictLeft = new Date(event.predict_until).getTime() - now;
  return (
    <section className="live-now" aria-label="The live event">
      <div className="live-now-head">
        <span className="live-dot" aria-hidden="true" /><span className="live-word">Live</span>
        <span className="live-name">{event.name}</span>
        <span className="live-clock mono" aria-label={`${untilWords(left)} left`}>{untilWords(left)}</span>
      </div>
      <h2 className="live-headline">{event.headline}</h2>
      <p className="live-story">{event.story}</p>
      <div className="live-figures">
        <div><span className="muted small">Featured share</span><a className="mono strong" href={`#/companies/${event.featured.ticker}`}>{event.featured.ticker}</a><span className="small">{event.featured.name}</span></div>
        <div><span className="muted small">At the bell</span><span className="mono strong">{formatNaira(event.start_price)}</span></div>
        <div><span className="muted small">Now</span><span className="mono strong">{formatNaira(event.price_now)}</span></div>
        <div><span className="muted small">Move</span><span className={`mono strong ${tone(event.move_bps)}`}>{signedPct(event.move_bps)}</span></div>
      </div>
      <div className="live-touched">
        <span className="muted small">It touches</span>
        {event.touched.map((t) => (
          <a key={t.ticker} href={`#/companies/${t.ticker}`} className={`live-chip ${t.direction}`} title={t.name}>
            {t.direction === "up" ? "▲" : t.direction === "down" ? "▼" : "◆"} {t.ticker}
          </a>
        ))}
      </div>
      {d.can_predict ? <Prediction event={event} act={act} /> : (
        <p className="small muted">{d.your_prediction_bps !== null && d.your_prediction_bps !== undefined
          ? `Your prediction is in: ${signedPct(d.your_prediction_bps)}.`
          : predictLeft > 0 ? (d.empire ? "" : "Join an empire run by players to predict.") : "Predictions closed ten minutes after the bell."}
          {predictLeft > 0 && ` Predictions close in ${untilWords(predictLeft)}.`}</p>
      )}
      <Members event={event} />
      {event.your_actions.length > 0 && (
        <ul className="small live-actions">{event.your_actions.map((a, i) => <li key={i} className={a.done ? "" : "change-down"}>Your standing plan: {a.what}</li>)}</ul>
      )}
      <Table event={event} running />
      <p className="small muted">Trade on the desk or a company's page as usual: it all counts. Predictions, messages and the scores appear the moment they happen; prices in the table are updated every few seconds. Other empires' predictions stay sealed until the end.</p>
    </section>
  );
}

function LiveChat({ d, act, open }: { d: LivePage; act: Act; open: boolean }) {
  const [body, setBody] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const lines = d.chat ?? [];
  const last = lines.length ? lines[lines.length - 1].id : 0;
  useEffect(() => {
    const box = log.current;
    if (box) box.scrollTop = box.scrollHeight;          // the newest message in view
  }, [last]);
  return (
    <Panel title="Your empire's chat" aside={open ? "messages appear at once" : "same chat as the War Room"}>
      <div className="chat" role="log" aria-live="polite" ref={log}>
        {lines.length === 0 && <p className="muted small">Nobody has said anything yet. Talk the event over here: only {d.empire}'s members see it.</p>}
        {lines.map((m) => (
          <div key={m.id} className={m.yours ? "chat-line yours" : "chat-line"}>
            <div className="muted small">{m.yours ? "You" : m.who} · {new Date(m.at).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" })}</div>
            <div>{m.body}</div>
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={(e) => {
        e.preventDefault();
        const text = body.trim();
        if (text) act.run(async () => { await api.empireSay(text); setBody(""); return d; }, "");
      }}>
        <input type="text" aria-label="Your message" maxLength={500} value={body} onChange={(e) => setBody(e.target.value)} placeholder={`Say something to ${d.empire}`} />
        <button className="button-outline" disabled={act.busy || !body.trim()}>Send</button>
      </form>
    </Panel>
  );
}

function Plan({ d, act }: { d: LivePage; act: Act }) {
  const [plan, setPlan] = useState(d.plan?.plan ?? "hold");
  const [budget, setBudget] = useState(d.plan ? String(Number(d.plan.budget) / 100) : "");
  const needsBudget = plan === "buy_the_fall" || plan === "ride";
  const kobo = needsBudget ? asKobo(budget) : 0;
  return (
    <Panel title="Your standing plan" aside={d.plan ? `set ${new Date(d.plan.at).toLocaleDateString("en-NG")}` : "none set: hold"}>
      <p className="small">For when nobody from {d.empire} can be there: carried out at the bell by the head's own authority, inside every limit an order from the head would meet.</p>
      {d.is_head ? (
        <form onSubmit={(e) => { e.preventDefault(); if (kobo !== null) act.run(() => api.livePlan({ plan, budget_kobo: kobo ?? 0 }), "The standing plan is set."); }}>
          <fieldset className="live-plans">
            <legend className="sr-only">The plan</legend>
            {(d.plans ?? []).map((p) => (
              <label key={p.code} className={plan === p.code ? "live-plan on" : "live-plan"}>
                <input type="radio" name="plan" value={p.code} checked={plan === p.code} onChange={() => setPlan(p.code)} />
                <span><strong>{p.words.split(":")[0]}</strong>{p.words.includes(":") ? `: ${p.words.split(":").slice(1).join(":").trim()}` : ""}</span>
              </label>
            ))}
          </fieldset>
          {needsBudget && (
            <label className="small">Budget, in naira <input className="mono" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="e.g. 2,000,000" /></label>
          )}
          <button type="submit" className="button-primary" disabled={act.busy || kobo === null}>Set the plan</button>
        </form>
      ) : (
        <p className="small"><strong>{(d.plans ?? []).find((p) => p.code === (d.plan?.plan ?? "hold"))?.words}</strong>{d.plan && Number(d.plan.budget) > 0 && `, up to ${formatNaira(d.plan.budget)}`}. Only the head sets it.</p>
      )}
    </Panel>
  );
}

function Past({ event }: { event: LiveEvent }) {
  const winner = event.table.find((r) => (r.points ?? 0) > 0);
  return (
    <details className="live-past">
      <summary>
        <span className="mono small muted">{whenWords(event.starts_at)}</span>
        <span className="strong">{event.name}</span>
        <span>{event.headline}</span>
        <span className={`mono ${tone(event.move_bps)}`}>{event.featured.ticker} {signedPct(event.move_bps)}</span>
        <span className="small">{winner ? <>Won by <strong>{winner.empire}</strong>, {winner.points} points</> : "No points"}</span>
      </summary>
      <p className="small">{event.story}</p>
      <Members event={event} />
      <Table event={event} running={false} />
      {(event.floor ?? []).length > 0 && (
        <p className="small">On the Floor: {(event.floor ?? []).map((f) => `${f.name} (${f.role === "bank" ? "bank" : "client"}, ${f.place}${f.points ? `, ${f.points} points` : ""})`).join(" · ")}</p>
      )}
    </details>
  );
}

export function LiveWork({ onLoggedOut }: Props) {
  const page = useLoad(api.live, "live-events", onLoggedOut);
  const act = useAct(page.reload, onLoggedOut);
  const d = page.data;
  const now = useServerNow(d?.now);
  const running = Boolean(d?.live);
  const nextAt = d?.next_at ? new Date(d.next_at).getTime() : null;
  const reload = page.reload;
  // The moment something changes, the server says so. Prices move all the time, so while an event runs the table is
  // still read every ten seconds (every five if the line to the server is down); between events, every five minutes.
  const pushed = useLivePushes(reload);
  useEffect(() => {
    const id = window.setInterval(reload, running ? (pushed ? 10_000 : 5_000) : (pushed ? 300_000 : 60_000));
    return () => window.clearInterval(id);
  }, [running, pushed, reload]);
  const bellPassed = nextAt !== null && now >= nextAt + 2_000;
  useEffect(() => { if (bellPassed && !running) reload(); }, [bellPassed, running, reload]);

  if (page.loading && !d) return <Loading what="the live events" />;
  if (page.error || !d) return <Failed message={page.error ?? "Could not load the live events."} onRetry={page.reload} />;
  if (!d.ready) return <Panel title="Live events"><p className="small">Live events have not started in this world yet.</p></Panel>;
  const p = d.points!;
  return (
    <>
      <PageHead title="Live events" sub={`${d.days} at ${d.hour}: thirty minutes, every empire at once`}
                aside={d.live ? <span className="live-pill"><span className="live-dot" aria-hidden="true" /> Live</span> : `next in ${untilWords((nextAt ?? now) - now)}`} />
      <Band label="Where you stand" columns={4}>
        <BandCell label="The next bell" value={d.next_at ? whenWords(d.next_at) : "—"} note={d.live ? "after this one" : `in ${untilWords((nextAt ?? now) - now)}`} />
        <BandCell label="Your empire" value={d.empire ?? "—"} note={d.empire ? "competes as one" : "join one to compete"} />
        <BandCell label="To win" value={`${p.places[0]} + ${p.places[0]}`} note="closest prediction, best result" />
        <BandCell label="Your plan" value={d.plan ? (d.plans ?? []).find((x) => x.code === d.plan!.plan)?.words.split(":")[0] : "Hold"} note={d.is_head ? "you set it" : "the head sets it"} />
      </Band>
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      {d.live ? <LiveNow d={d} event={d.live} now={now} act={act} /> : (
        <section className="live-wait" aria-label="The next live event">
          <span className="muted small live-eyebrow">The next bell</span>
          <span className="live-countdown mono">{untilWords((nextAt ?? now) - now)}</span>
          <span>{d.next_at && whenWords(d.next_at)}, Lagos time. What happens is decided at the bell: nobody knows in advance.</span>
          <span className="live-kinds">{(d.kinds ?? []).map((k) => <span key={k.code} className="live-chip">{k.name}</span>)}</span>
        </section>
      )}
      {d.empire && <LiveChat d={d} act={act} open={pushed} />}
      {d.empire && <Plan key={d.plan?.at ?? "none"} d={d} act={act} />}
      <Panel title="How it works" aside="points go to the league">
        <ul className="small live-rules">
          <li><strong>The bell.</strong> At {d.hour} on {d.days}, one of five things happens for real: a fraud uncovered, a fuel crisis, a run on a bank, an emergency rate move, or a takeover bid. It is in the news at once, and its effect is real: in the companies' accounts, savers' trust, or the Central Bank's next rate.</li>
          <li><strong>The prediction.</strong> In the first {d.predict_minutes} minutes every member seals their own prediction of how far the featured share will move by the end; your empire's closest counts. The three closest empires earn {p.places.join(", ")} points, if they missed by no more than {pct(p.most_miss_bps)}.</li>
          <li><strong>The money.</strong> What the event did to each empire's money: the shares it touched, held and traded in the window, against what the empire was worth at the bell, so a small empire can beat a big one. The best three that made money earn {p.places.join(", ")}.</li>
          <li><strong>Taking part</strong> earns {p.took_part}: predict, trade a touched share, or have your plan act.</li>
          <li>Investors who read the news at once react within minutes; the institutions a day later. Computer-run empires are in the field too.</li>
        </ul>
      </Panel>
      <Panel title="Past events" aside="newest first">
        {(d.past ?? []).length === 0 ? <p className="muted small">No live event has been held yet.</p> : (d.past ?? []).map((e) => <Past key={e.id} event={e} />)}
      </Panel>
    </>
  );
}

/** A strip on the desk: the countdown to the next bell, or the event running now. */
export function LiveStrip({ onLoggedOut }: { onLoggedOut: () => void }) {
  const page = useLoad(api.live, "live-strip", onLoggedOut);
  const d = page.data;
  const now = useServerNow(d?.now);
  const running = Boolean(d?.live);
  const reload = page.reload;
  useLivePushes(reload, ["event"]);                    // the bell and the scores at once
  useEffect(() => {
    const id = window.setInterval(reload, running ? 15_000 : 120_000);
    return () => window.clearInterval(id);
  }, [running, reload]);
  if (!d?.ready) return null;
  if (d.live) {
    const e = d.live;
    return (
      <a className="live-strip on" href="#/live">
        <span className="live-dot" aria-hidden="true" /><span className="live-word">Live</span>
        <span className="strong">{e.name}</span><span className="live-strip-headline">{e.headline}</span>
        <span className={`mono ${tone(e.move_bps)}`}>{e.featured.ticker} {signedPct(e.move_bps)}</span>
        <span className="mono live-strip-clock">{untilWords(new Date(e.ends_at).getTime() - now)} left</span>
      </a>
    );
  }
  const nextAt = d.next_at ? new Date(d.next_at).getTime() : now;
  return (
    <a className="live-strip" href="#/live">
      <span className="muted small live-eyebrow">Next live event</span>
      <span>{d.next_at && whenWords(d.next_at)}</span>
      <span className="mono live-strip-clock">{untilWords(nextAt - now)}</span>
      {d.past?.[0] && <span className="small muted live-strip-last">Last: {d.past[0].name}, won by {d.past[0].table.find((r) => (r.points ?? 0) > 0)?.empire ?? "nobody"}</span>}
    </a>
  );
}
