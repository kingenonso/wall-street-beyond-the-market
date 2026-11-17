// Prediction markets (owner, 16 November 2026: "build"): The Floor → Predictions. Yes or No on things the game itself
// decides: the Central Bank's rate at the close, the largest companies' profits, the next live event, the featured share
// in a live event. A winning share pays ₦100; the price of Yes is the crowd's chance that it happens. The computer makes
// the market by a rule, so there is always a price, and every purchase moves it. Every figure comes from the server.

import { useEffect, useState } from "react";
import { api, ApiError, type Player, type PredictionMarket, type PredictionsPage } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Failed, Loading, PageHead, Panel } from "./Shell";
import { play } from "./sound";

type Props = { player: Player; onLoggedOut: () => void; inLive?: boolean };
const pct = (bps: number) => `${Math.round(bps / 100)}%`;
const when = (iso: string) => new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "short", hour: "2-digit", minute: "2-digit" });

function Spark({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const w = 120, h = 28;
  const path = points.map((p, i) => `${i ? "L" : "M"}${(i / (points.length - 1)) * w},${h - (p / 10000) * h}`).join(" ");
  return <svg className="pm-spark" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`The chance moved from ${pct(points[0])} to ${pct(points[points.length - 1])}`}><path d={path} /></svg>;
}

function Card({ m, run, busy }: { m: PredictionMarket; run: (ask: () => Promise<PredictionsPage>, words: string) => void; busy: boolean }) {
  const [count, setCount] = useState("100");
  const n = Number(count.replace(/[,\s]/g, ""));
  const ok = Number.isInteger(n) && n > 0;
  const open = m.status === "open";
  const about = (side: "yes" | "no") => {
    const p = side === "yes" ? m.chance_bps : 10000 - m.chance_bps;
    return formatNaira(String(Math.round((n * p) / 10000) * 100));
  };
  const y = m.yours;
  return (
    <div className={`pm-card ${m.status !== "open" ? "pm-done" : ""}`}>
      <div className="pm-head">
        <span className="pm-area small muted">{m.area}</span>
        {m.closes_at && open && <span className="small muted">closes {when(m.closes_at)}</span>}
        {m.status === "closed" && <span className="small">Betting closed: waiting for the answer</span>}
        {m.status === "resolved" && <span className={`small strong ${m.outcome ? "change-up" : "change-down"}`}>Answered: {m.outcome ? "Yes" : "No"}</span>}
        {m.status === "void" && <span className="small">Came to nothing: stakes handed back</span>}
      </div>
      <h3 className="pm-question">{m.question}</h3>
      <p className="small muted">{m.details}</p>
      <div className="pm-chance">
        <div className="pm-bar" role="img" aria-label={`The crowd says ${pct(m.chance_bps)} Yes`}><span style={{ width: `${m.chance_bps / 100}%` }} /></div>
        <span className="mono strong">{pct(m.chance_bps)} Yes</span>
        <Spark points={m.history} />
        <span className="small muted">{m.volume.toLocaleString("en-NG")} shares traded</span>
      </div>
      {y && (
        <p className="small">You hold {y.yes ? `${y.yes.toLocaleString("en-NG")} Yes` : ""}{y.yes && y.no ? " and " : ""}{y.no ? `${y.no.toLocaleString("en-NG")} No` : ""}
          {y.worth_now !== null && <> · worth {formatNaira(y.worth_now)} now (you put in {formatNaira(y.paid)})</>}
          {BigInt(y.paid_out) > 0n && <> · paid out {formatNaira(y.paid_out)}</>}.</p>
      )}
      {open && !m.barred && (
        <div className="pm-trade">
          <input className="mono" inputMode="numeric" aria-label="How many shares" value={count} onChange={(e) => setCount(e.target.value)} />
          <button className="pm-yes" disabled={!ok || busy} onClick={() => run(() => api.predictionTrade(m.id, "yes", n), `Bought ${n.toLocaleString("en-NG")} Yes.`)}>Buy Yes · about {about("yes")}</button>
          <button className="pm-no" disabled={!ok || busy} onClick={() => run(() => api.predictionTrade(m.id, "no", n), `Bought ${n.toLocaleString("en-NG")} No.`)}>Buy No · about {about("no")}</button>
          {y && y.yes > 0 && <button className="button-outline small" disabled={!ok || busy || n > y.yes} onClick={() => run(() => api.predictionTrade(m.id, "yes", -n), `Sold ${n.toLocaleString("en-NG")} Yes back.`)}>Sell Yes back</button>}
          {y && y.no > 0 && <button className="button-outline small" disabled={!ok || busy || n > y.no} onClick={() => run(() => api.predictionTrade(m.id, "no", -n), `Sold ${n.toLocaleString("en-NG")} No back.`)}>Sell No back</button>}
        </div>
      )}
      {open && m.barred && <p className="small change-down">You decide this one as Government Leader, so you may not bet on it.</p>}
    </div>
  );
}

export function PredictionsWork({ onLoggedOut, inLive }: Props) {
  const page = useLoad(api.predictions, "predictions", onLoggedOut);
  const [fresh, setFresh] = useState<PredictionsPage | null>(null);
  const d = fresh ?? page.data;
  useEffect(() => { if (page.data) setFresh(null); }, [page.data]);
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, 15_000);
    return () => window.clearInterval(id);
  }, [reload]);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; words: string } | null>(null);
  async function run(ask: () => Promise<PredictionsPage>, words: string) {
    setBusy(true); setSaid(null);
    try { setFresh(await ask()); setSaid({ ok: true, words }); play("trade"); }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setSaid({ ok: false, words: problem instanceof ApiError ? problem.message : "Could not reach the server." });
    } finally { setBusy(false); }
  }
  if (page.loading && !d) return <Loading what="the prediction markets" />;
  if (page.error || !d) return <Failed message={page.error ?? "Could not load the prediction markets."} onRetry={page.reload} />;
  if (!d.ready) return <Panel title="Predictions"><p className="small">Prediction markets have not started in this world yet.</p></Panel>;
  const markets = d.markets ?? [];
  const open = markets.filter((m) => m.status === "open"), rest = markets.filter((m) => m.status !== "open");
  return (
    <>
      {inLive ? <h2 className="season-head" id="predictions">Prediction markets: bet on what the game decides <span className="small muted">{open.length} open</span></h2>
        : <PageHead title="Predictions" sub="Bet Yes or No on what the game will decide. A winning share pays ₦100; the price of Yes is the crowd's chance." aside={`${open.length} open`} />}
      {said && <p className={`small ${said.ok ? "" : "change-down"}`} role={said.ok ? "status" : "alert"}>{said.words}</p>}
      <Panel title="How it works" aside="the price is a probability">
        <p className="small">If Yes costs ₦70, the crowd thinks it is 70% likely. If you think it is likelier, buy Yes: you pay ₦70 and get ₦100 if it happens. Every purchase moves the price; you can sell back before the close at the price then. Every answer comes from the game's own books, so nobody can rig it. One player may have at most {d.most_stake ? formatNaira(d.most_stake) : "—"} in one question.</p>
      </Panel>
      <div className="pm-grid">{open.map((m) => <Card key={m.id} m={m} run={run} busy={busy} />)}</div>
      {rest.length > 0 && <Panel title="Closed and answered" aside="the last three days"><div className="pm-grid">{rest.map((m) => <Card key={m.id} m={m} run={run} busy={busy} />)}</div></Panel>}
    </>
  );
}
