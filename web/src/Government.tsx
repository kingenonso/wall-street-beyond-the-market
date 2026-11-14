// Government, part 1: Economy → Government.
//
// Who governs this year (an elected leader, or the stand-in run by rules), the tax rates in force, the year's budget and
// the Assembly's vote on it, a vote of no confidence, and the election for next year. Every figure is the server's.

import { useState } from "react";
import { api, ApiError, type GovernmentPage, type Player } from "./api";
import { formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Band, BandCell, Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void };

function useAct(reload: () => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(ask: () => Promise<GovernmentPage>, done: string) {
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

const pct = (bps: number) => formatPercent(bps, 2);

function BudgetForm({ d, act }: { d: GovernmentPage; act: ReturnType<typeof useAct> }) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(d.rates.map((r) => [r.kind, (r.bps / 100).toFixed(2)])));
  const bps = (k: string) => Math.round(Number(values[k]) * 100);
  const valid = d.rates.every((r) => Number.isFinite(bps(r.kind)) && bps(r.kind) >= r.least_bps && bps(r.kind) <= r.most_bps);
  return (
    <form className="inline-form" onSubmit={(e) => {
      e.preventDefault();
      if (valid) act.run(() => api.governmentBudget({ income_bps: bps("income"), company_bps: bps("company"), property_bps: bps("property"), land_bps: bps("land") }),
                         "The budget is before the Assembly. It is counted when the quarter closes.");
    }}>
      {d.rates.map((r) => (
        <label key={r.kind} className="answer">{r.name} (%)
          <input type="text" inputMode="decimal" value={values[r.kind]} onChange={(e) => setValues({ ...values, [r.kind]: e.target.value })} />
        </label>
      ))}
      <button className="button-primary" disabled={act.busy || !valid}>Put the budget</button>
    </form>
  );
}

export function GovernmentWork({ onLoggedOut }: Props) {
  const page = useLoad(api.government, "government", onLoggedOut);
  const act = useAct(page.reload, onLoggedOut);
  const [pitch, setPitch] = useState("");
  if (page.loading && !page.data) return <Loading what="the Government" />;
  if (page.error || !page.data) return <Failed message={page.error ?? "Could not load the Government."} onRetry={page.reload} />;
  const d = page.data;
  if (!d.ready) return <Panel title="Government"><p className="small">The Government has not opened in this world yet.</p></Panel>;
  const heads = d.assembly.filter((m) => m.kind === "head");
  const computers = d.assembly.filter((m) => m.kind === "computer");
  const e = d.election;
  return (
    <>
      <PageHead title="Government" sub="An elected leader sets the year's taxes; the Assembly passes the budget or throws it out" aside={`${d.quarter} · day ${d.day}`} />
      <Band label="Who governs" columns={4}>
        <BandCell label={`Game year ${d.year}`} value={d.leader ? d.leader.name : "The stand-in"} note={d.leader ? `elected with ${d.leader.votes} votes` : d.stand_in.words} />
        {d.rates.slice(0, 3).map((r) => <BandCell key={r.kind} label={r.name} value={pct(r.bps)} note={`may be set from ${pct(r.least_bps)} to ${pct(r.most_bps)}`} />)}
      </Band>
      {d.term_words && <p className="small">{d.term_words}</p>}
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      <div className="two-columns">
        <Panel title="This year's budget" aside={d.budget ? d.budget.status : "not yet put"}>
          <table className="dense">
            <thead><tr><th scope="col">Tax</th><th scope="col" className="num">In force</th><th scope="col" className="num">In the budget</th></tr></thead>
            <tbody>{d.rates.map((r) => (
              <tr key={r.kind}><th scope="row">{r.name}</th><td className="num mono">{pct(r.bps)}</td><td className="num mono">{d.budget ? pct(Number(d.budget.rates[r.kind])) : "—"}</td></tr>
            ))}</tbody>
          </table>
          {d.budget?.words && <p className="small">{d.budget.words}</p>}
          {d.can_propose ? <BudgetForm d={d} act={act} /> : !d.budget && <p className="muted small">The leader puts the budget in the year's first quarter, by day {d.budget_last_day}. If none is put, the stand-in's applies.</p>}
          {d.budget && d.budget.status === "voting" && d.your_seat && !d.budget.voted && (
            <div className="inline-form">
              <button className="button-primary" disabled={act.busy} onClick={() => act.run(() => api.governmentAssemblyVote({ subject: `budget:${d.budget!.id}`, aye: true }), "Your empire's seat voted for the budget.")}>Vote for</button>
              <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.governmentAssemblyVote({ subject: `budget:${d.budget!.id}`, aye: false }), "Your empire's seat voted against the budget.")}>Vote against</button>
            </div>
          )}
        </Panel>
        <Panel title="The Assembly" aside={`${heads.length} heads · ${computers.length} computer-run members`}>
          <p className="small">The head of every empire run by players sits here with one vote, beside computer-run members whose leanings are published.</p>
          <ul className="small">
            {heads.map((m) => <li key={`h${m.empire_id}`}>{m.name}, for {m.empire}</li>)}
            {(["low_tax", "high_tax", "steady"] as const).map((l) => {
              const n = computers.filter((m) => m.leaning === l).length;
              return n ? <li key={l}>{n} computer-run {n === 1 ? "member" : "members"} who {computers.find((m) => m.leaning === l)?.words}</li> : null;
            })}
          </ul>
          {d.motion && <p className="small">A vote of no confidence: {d.motion.status === "voting" ? "before the Assembly, counted at the close." : `${d.motion.status}, ${d.motion.votes_for} to ${d.motion.votes_against}.`}</p>}
          {d.motion && d.motion.status === "voting" && d.your_seat && !d.motion.voted && (
            <div className="inline-form">
              <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.governmentAssemblyVote({ subject: `motion:${d.motion!.id}`, aye: true }), "Your seat voted to remove the leader.")}>Remove the leader</button>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.governmentAssemblyVote({ subject: `motion:${d.motion!.id}`, aye: false }), "Your seat voted to keep the leader.")}>Keep the leader</button>
            </div>
          )}
          {d.your_seat && d.leader && (!d.motion || d.motion.status !== "voting") && (
            <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.governmentNoConfidence(), "The motion is before the Assembly.")}>Table a vote of no confidence</button>
          )}
        </Panel>
      </div>
      <Panel title={`The election for game year ${e.for_year}`} aside={e.open ? "this quarter" : "in a year's last quarter"}>
        <p className="small">Candidates stand in a year's last quarter, up to day {e.stand_last_day}, with a reputation of {e.least_reputation} and Level {e.least_level} or more. Then everybody past Level 5 has one vote. The count is made as the year closes; with no candidate or no vote, the stand-in governs.</p>
        {e.candidates.length === 0 ? <p className="muted small">Nobody is standing.</p> : (
          <table className="dense">
            <thead><tr><th scope="col">Candidate</th><th scope="col">What they would do</th><th scope="col" className="num">Reputation</th><th scope="col"></th></tr></thead>
            <tbody>{e.candidates.map((c) => (
              <tr key={c.player_id}><th scope="row">{c.name}</th><td>{c.pitch}</td><td className="num">{c.reputation}</td>
                <td>{e.your_vote === c.player_id ? "● your vote" : e.can_vote ? <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.governmentVote({ candidate_id: c.player_id }), "Your vote is cast.")}>Vote</button> : null}</td></tr>
            ))}</tbody>
          </table>
        )}
        {e.can_stand && (
          <form className="inline-form" onSubmit={(ev) => { ev.preventDefault(); if (pitch.trim()) act.run(() => api.governmentStand({ pitch }), "You are standing."); }}>
            <label className="answer">What you would do<input type="text" value={pitch} maxLength={400} onChange={(ev) => setPitch(ev.target.value)} /></label>
            <button className="button-primary" disabled={act.busy || !pitch.trim()}>Stand</button>
          </form>
        )}
      </Panel>
    </>
  );
}
