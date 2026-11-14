// Government, part 1: Economy → Government.
//
// Who governs this year (an elected leader, or the stand-in run by rules), the tax rates in force, the year's budget and
// the Assembly's vote on it, a vote of no confidence, and the election for next year. Every figure is the server's.

import { useState } from "react";
import { api, ApiError, type GovernmentPage, type Player } from "./api";
import { formatNaira, formatPercent } from "./format";
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


function Powers({ d, act }: { d: GovernmentPage; act: ReturnType<typeof useAct> }) {
  const p = d.powers!;
  const [rate, setRate] = useState("");
  const [empire, setEmpire] = useState("");
  const [levy, setLevy] = useState("");
  const [reason, setReason] = useState("");
  const [seat, setSeat] = useState("");
  const rateBps = Math.round(Number(rate) * 100);
  const levyBps = Math.round(Number(levy) * 100);
  const computers = d.assembly.filter((m) => m.kind === "computer");
  const openVotes: { subject: string; label: string }[] = [
    ...(d.budget && d.budget.status === "voting" && d.budget.voted ? [{ subject: `budget:${d.budget.id}`, label: "the budget" }] : []),
    ...(d.motion && d.motion.status === "voting" && d.motion.voted ? [{ subject: `motion:${d.motion.id}`, label: "the vote of no confidence" }] : []),
    ...p.levies.filter((l) => l.status === "voting").map((l) => ({ subject: `motion:${l.id}`, label: `the levy on ${l.empire}` })),
  ];
  const [subject, setSubject] = useState("");
  const taken = new Set(p.lobbied.filter((l) => l.subject === (subject || openVotes[0]?.subject)).map((l) => l.seat));
  return (
    <>
      <div className="two-columns">
        <Panel title="The leader's powers" aside={`pay ${formatNaira(String(p.leader_pay))} a quarter`}>
          <p className="small"><strong>A decree</strong> sets next quarter's Central Bank rate, held within {pct(p.decree_most_bps)} of the Central Bank's own rule. It costs: prices rise {pct(p.decree_price_bps)} faster that quarter, and confidence falls {pct(p.decree_confidence_bps)}. One a quarter.</p>
          {p.last_decree && <p className="small">Last decree, {p.last_decree.quarter}: {pct(p.last_decree.rate_bps)}, where the Central Bank would have set {pct(p.last_decree.rule_bps)}.</p>}
          {p.decree_now_bps !== null && <p className="small">● A decree of {pct(p.decree_now_bps)} stands for this quarter's close.</p>}
          {p.can_decree && (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (rate) act.run(() => api.governmentDecree({ rate_bps: rateBps }), "Decreed. It takes effect as the quarter closes."); }}>
              <label className="answer">The rate (%)<input type="text" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} /></label>
              <button className="button-primary" disabled={act.busy || !rate || !Number.isFinite(rateBps)}>Decree</button>
            </form>
          )}
          <p className="small"><strong>A levy</strong> takes up to {pct(p.levy_most_bps)} of one empire's cash for the Treasury. Targeting an empire needs the Assembly: computer-run members who favour high taxes back it; the rest protect the empires.</p>
          {p.is_leader && (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (empire && levy && reason.trim()) act.run(() => api.governmentLevy({ empire_id: Number(empire), bps: levyBps, reason }), "The levy is before the Assembly."); }}>
              <label className="answer">On<select value={empire} onChange={(e) => setEmpire(e.target.value)}><option value="">choose an empire</option>{p.empires.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
              <label className="answer">Share of its cash (%)<input type="text" inputMode="decimal" value={levy} onChange={(e) => setLevy(e.target.value)} /></label>
              <label className="answer">Why<input type="text" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} /></label>
              <button className="button-primary" disabled={act.busy || !empire || !levy || !reason.trim()}>Put it to the Assembly</button>
            </form>
          )}
        </Panel>
        <Panel title="Lobbying" aside={`${formatNaira(String(p.lobby_cost))} a member, in the open`}>
          <p className="small">The head of an empire may pay the Treasury to win over a computer-run member's vote: the member then votes as the head's seat did. At most {p.lobby_most} members for one empire on one vote. Every naira and every member is public.</p>
          {p.can_lobby && openVotes.length > 0 && (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const s = subject || openVotes[0].subject; if (seat) act.run(() => api.governmentLobby({ subject: s, seat: Number(seat) }), "The member is won over."); }}>
              <label className="answer">On<select value={subject || openVotes[0].subject} onChange={(e) => setSubject(e.target.value)}>{openVotes.map((v) => <option key={v.subject} value={v.subject}>{v.label}</option>)}</select></label>
              <label className="answer">Member<select value={seat} onChange={(e) => setSeat(e.target.value)}><option value="">choose</option>{computers.filter((m) => !taken.has(m.seat!)).map((m) => <option key={m.seat} value={m.seat}>{m.name}, who would {m.words}</option>)}</select></label>
              <button className="button-primary" disabled={act.busy || !seat}>Lobby</button>
            </form>
          )}
          {p.can_lobby && openVotes.length === 0 && <p className="muted small">Vote first on an open budget or motion; then you can lobby members to vote with you.</p>}
          {!p.can_lobby && <p className="muted small">Only the head of an empire run by players can lobby. Every lobby paid this year is listed here.</p>}
          {p.lobbied.length === 0 && <p className="muted small">Nobody has lobbied yet.</p>}
          {p.lobbied.length > 0 && (
            <table className="dense">
              <thead><tr><th scope="col">Empire</th><th scope="col">Member</th><th scope="col">On</th><th scope="col">Now votes</th><th scope="col" className="num">Paid</th></tr></thead>
              <tbody>{p.lobbied.map((l, i) => <tr key={i}><th scope="row">{l.empire}</th><td>Member {l.seat}</td><td>{l.subject}</td><td>{l.vote ? "for" : "against"}</td><td className="num mono">{formatNaira(String(l.paid))}</td></tr>)}</tbody>
            </table>
          )}
        </Panel>
      </div>
      {p.levies.length > 0 && (
        <Panel title="Levies this year">
          <table className="dense">
            <thead><tr><th scope="col">On</th><th scope="col" className="num">Share</th><th scope="col">Why</th><th scope="col">Result</th><th scope="col"></th></tr></thead>
            <tbody>{p.levies.map((l) => (
              <tr key={l.id}><th scope="row">{l.empire}</th><td className="num">{pct(l.bps)}</td><td>{l.reason}</td>
                <td>{l.status === "voting" ? "before the Assembly" : `${l.status}, ${l.votes_for} to ${l.votes_against}${l.collected ? `: ${formatNaira(String(l.collected))} collected` : ""}`}</td>
                <td>{l.status === "voting" && d.your_seat ? (
                  <span className="inline-form">
                    <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.governmentAssemblyVote({ subject: `motion:${l.id}`, aye: true }), "Your seat voted for the levy.")}>For</button>
                    <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.governmentAssemblyVote({ subject: `motion:${l.id}`, aye: false }), "Your seat voted against the levy.")}>Against</button>
                  </span>) : null}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
      )}
    </>
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
        {d.rates.slice(0, 3).map((r) => <BandCell key={r.kind} label={r.name} value={pct(r.bps)} note={`${pct(r.least_bps)} to ${pct(r.most_bps)} allowed`} />)}
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
              return n ? <li key={l}>{n} computer-run {n === 1 ? "member, who would" : "members who"} {computers.find((m) => m.leaning === l)?.words}</li> : null;
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
      {d.powers && <Powers d={d} act={act} />}
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

export function GovernmentRail() {
  return (
    <Panel title="How government works">
      <ul className="small">
        <li>Each game year has a leader, elected in the year before by every player past Level 5. With nobody elected, a stand-in run by published rules governs.</li>
        <li>The leader puts one budget a year: income, company, property and land tax, within set limits. The Assembly passes it or throws it out.</li>
        <li>The leader may decree the Central Bank rate once a quarter, held within 3 points of the bank's own rule. A decree pushes prices up and confidence down.</li>
        <li>A levy on one empire, up to 2% of its cash, needs the Assembly too.</li>
        <li>Heads of empires lobby computer-run members by paying the Treasury, in the open. A vote of no confidence can remove the leader.</li>
      </ul>
    </Panel>
  );
}
