// Live events, part 1 (owner, 16 November 2026): Work → Live events.
//
// Three evenings a week (Monday, Wednesday and Friday at 20:00 Lagos time) something happens in the shared world at once
// for everybody, and for thirty minutes every empire competes on how it reads and handles it. This page counts down to
// the bell, shows the event as it runs (the story, the featured share, the table), takes the empire's one sealed
// prediction in the first ten minutes, lets the head leave a standing plan, and keeps the past events with their scores.
// Every figure comes from the server; the countdown is the server's time, ticked on between visits.

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type LiveEvent, type LivePage, type Player } from "./api";
import { asKobo } from "./Empire";
import { formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
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
      if (ok) act.run(() => api.livePredict({ event_id: event.id, move_bps: Math.round(value * 100) }), "Your empire's prediction is in, sealed.");
    }}>
      <label htmlFor="live-move">How far will {event.featured.ticker} move from the bell to the end?</label>
      <div className="live-predict-row">
        <input id="live-move" className="mono" inputMode="decimal" placeholder="e.g. −4.5 or 2" value={move} onChange={(e) => setMove(e.target.value)} />
        <span className="muted">%</span>
        <button type="submit" className="button-primary" disabled={!ok || act.busy}>Seal the prediction</button>
      </div>
      <p className="small muted">One for the whole empire, by whichever member is first. Sealed: nobody else sees it until the event is scored, and it cannot be changed.</p>
    </form>
  );
}

function Table({ event, running }: { event: LiveEvent; running: boolean }) {
  return (
    <table className="dense live-table">
      <thead><tr>
        <th scope="col">Empire</th>
        <th scope="col" className="num" title="What the event did to its money: the shares it touched, held and traded, against what the empire was worth at the bell">Result</th>
        <th scope="col" className="num">Prediction</th>
        {!running && <th scope="col" className="num">Missed by</th>}
        {!running && <th scope="col" className="num">Points</th>}
      </tr></thead>
      <tbody>{event.table.map((r) => (
        <tr key={r.empire} className={r.yours ? "live-yours" : ""}>
          <th scope="row">{r.empire}{r.run_by === "the computer" && <span className="muted small"> · computer</span>}</th>
          <td className={`num mono ${tone(r.result_bps)}`}>{signedPct(r.result_bps)}{r.result_kobo !== null && <span className="muted small"> ({r.result_kobo.startsWith("-") ? "−" + formatNaira(r.result_kobo.slice(1)) : formatNaira(r.result_kobo)})</span>}</td>
          <td className="num mono">{r.prediction_bps !== null ? signedPct(r.prediction_bps) : r.predicted ? "● sealed" : "—"}</td>
          {!running && <td className="num mono">{r.miss_bps === null ? "—" : pct(r.miss_bps)}</td>}
          {!running && <td className="num"><strong>{r.points ?? 0}</strong></td>}
        </tr>
      ))}</tbody>
    </table>
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
        <p className="small muted">{predictLeft > 0 ? (d.empire ? "Your empire's prediction is in." : "Join an empire run by players to predict for it.") : "Predictions closed ten minutes after the bell."}{predictLeft > 0 && ` Predictions close in ${untilWords(predictLeft)}.`}</p>
      )}
      {event.your_actions.length > 0 && (
        <ul className="small live-actions">{event.your_actions.map((a, i) => <li key={i} className={a.done ? "" : "change-down"}>Your standing plan: {a.what}</li>)}</ul>
      )}
      <Table event={event} running />
      <p className="small muted">Trade on the desk or a company's page as usual: it all counts. The table is updated every few seconds; other empires' predictions stay sealed until the end.</p>
    </section>
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
      <Table event={event} running={false} />
    </details>
  );
}

export function LiveWork({ onLoggedOut }: Props) {
  const page = useLoad(api.live, "live-events", onLoggedOut);
  const act = useAct(page.reload, onLoggedOut);
  const d = page.data;
  const now = useServerNow(d?.now);
  // Every five seconds while an event runs; every minute otherwise, and at the bell itself.
  const running = Boolean(d?.live);
  const nextAt = d?.next_at ? new Date(d.next_at).getTime() : null;
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, running ? 5_000 : 60_000);
    return () => window.clearInterval(id);
  }, [running, reload]);
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
        <BandCell label="To win" value={`${p.places[0]} + ${p.places[0]}`} note="best prediction, best result" />
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
      {d.empire && <Plan key={d.plan?.at ?? "none"} d={d} act={act} />}
      <Panel title="How it works" aside="points go to the league">
        <ul className="small live-rules">
          <li><strong>The bell.</strong> At {d.hour} on {d.days}, one of five things happens for real: a fraud uncovered, a fuel crisis, a run on a bank, an emergency rate move, or a takeover bid. It is in the news at once, and its effect is real: in the companies' accounts, savers' trust, or the Central Bank's next rate.</li>
          <li><strong>The prediction.</strong> In the first {d.predict_minutes} minutes your empire seals one prediction of how far the featured share will move by the end. The closest three earn {p.places.join(", ")} points, if they missed by no more than {pct(p.most_miss_bps)}.</li>
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
