// Competition, part 1: Work → Competition.
//
// Two kinds of work with a winner. Mandates: a company selling new shares invites every empire to pitch, and chooses the
// pitch best for it. Ranked work: each quarter each build forecasts one figure about one company, and the closest are
// ranked when the quarter closes. Other players' pitches and forecasts are never shown until they are judged: the server
// does not send them.

import { useState } from "react";
import { api, ApiError, type CompetitionCall, type CompetitionContest, type CompetitionMandate, type CompetitionPage, type Player } from "./api";
import { asKobo } from "./Empire";
import { formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Band, BandCell, Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void };

function useAct(reload: () => void, onLoggedOut: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(ask: () => Promise<CompetitionPage>, done: string) {
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

const pct = (bps: number | null | undefined) => (bps === null || bps === undefined ? "—" : formatPercent(bps, 1));

/** A figure in kobo that may be a loss. */
function signed(kobo: string): string {
  return kobo.startsWith("-") ? `− ${formatNaira(kobo.slice(1))}` : formatNaira(kobo);
}

function asSignedKobo(text: string): number | null {
  const negative = text.trim().startsWith("-") || text.trim().startsWith("−");
  const k = asKobo(text.replace(/^[\s−-]+/, ""));
  return k === null ? null : negative ? -k : k;
}

function ContestPanel({ c, act }: { c: CompetitionContest; act: Act }) {
  const [guess, setGuess] = useState("");
  return (
    <Panel title={`${c.build_name}: ${c.company.name} (${c.company.ticker})`} aside={`${c.quarter} · ${c.entries} ${c.entries === 1 ? "forecast" : "forecasts"}`}>
      <p className="small">Forecast {c.measure_words}.</p>
      {c.status === "judged" ? (
        <>
          <div className="row small"><span>The figure</span><span className="mono">{c.truth ? signed(c.truth) : "—"}</span></div>
          {c.entry && <div className="row small"><span>Your forecast</span><span className="mono">{signed(c.entry.guess)} · missed by {pct(c.entry.error_bps)} · place {c.entry.place}{c.entry.points ? ` · ${c.entry.points} points` : ""}</span></div>}
          {c.top.length > 0 && (
            <table className="dense">
              <thead><tr><th scope="col">Place</th><th scope="col">Analyst</th><th scope="col">Empire</th><th scope="col" className="num">Forecast</th><th scope="col" className="num">Missed by</th><th scope="col" className="num">Points</th></tr></thead>
              <tbody>{c.top.map((t, i) => (
                <tr key={i}><td>{t.place}</td><th scope="row">{t.name}</th><td>{t.empire ?? "—"}</td><td className="num mono">{signed(t.guess)}</td><td className="num mono">{pct(t.error_bps)}</td><td className="num">{t.points || ""}</td></tr>
              ))}</tbody>
            </table>
          )}
        </>
      ) : c.entry ? (
        <p className="small">● Your forecast, {signed(c.entry.guess)}, is sealed until the quarter closes.</p>
      ) : c.yours && c.open ? (
        <form className="inline-form" onSubmit={(e) => {
          e.preventDefault();
          const k = asSignedKobo(guess);
          if (k !== null) act.run(() => api.competitionForecast({ contest_id: c.id, guess_kobo: k }), "Handed in. It is sealed until the quarter closes.");
        }}>
          <label className="answer">Your forecast (₦)<input type="text" inputMode="decimal" value={guess} onChange={(e) => setGuess(e.target.value)} /></label>
          <button className="button-primary" disabled={act.busy || asSignedKobo(guess) === null}>Hand in</button>
        </form>
      ) : (
        <p className="muted small">{c.yours ? "Forecasts for this one have closed." : "For another build."}</p>
      )}
    </Panel>
  );
}

function MandateRow({ m, act, canPitch }: { m: CompetitionMandate; act: Act; canPitch: boolean }) {
  const [fee, setFee] = useState("");
  const [takeUp, setTakeUp] = useState("");
  const feeBps = Math.round(Number(fee) * 100);
  const takeBps = Math.round(Number(takeUp) * 100);
  const valid = fee !== "" && takeUp !== "" && Number.isFinite(feeBps) && Number.isFinite(takeBps);
  return (
    <div className="report">
      <div className="row small"><span><strong>{m.company.name}</strong> ({m.company.ticker}) · {m.kind === "defence" ? `defending it against a hostile bid worth ${formatNaira(m.amount)}` : `${m.kind === "rights" ? "a rights issue" : "a sale of new shares"} of ${formatNaira(m.amount)}`}</span>
        <span className="muted">{m.quarter} · {m.pitches} {m.pitches === 1 ? "pitch" : "pitches"}</span></div>
      <p className="muted small">{m.reason}</p>
      {m.winner ? (
        <div className="row small"><span>Won by <strong>{m.winner.empire}</strong> at {pct(m.winner.fee_bps)}{m.taken_up_bps !== null ? `; ${pct(m.taken_up_bps)} was taken up` : ""}</span>
          <span className="mono">{m.status === "settled" ? `fee paid ${formatNaira(m.fee_paid)}` : "settles at the close"}</span></div>
      ) : m.status === "lapsed" ? (
        <p className="small muted">○ {m.words}</p>
      ) : null}
      {m.ours ? (
        <p className="small">● Your empire pitched {pct(m.ours.fee_bps)}, forecasting {pct(m.ours.take_up_bps)} taken up{m.ours.error_bps !== null ? `: it missed by ${pct(m.ours.error_bps)}` : ". It is sealed until the company chooses"}.</p>
      ) : m.open && canPitch ? (
        <form className="inline-form" onSubmit={(e) => {
          e.preventDefault();
          if (valid) act.run(() => api.competitionPitch({ mandate_id: m.id, fee_bps: feeBps, take_up_bps: takeBps }), "Pitched. It is sealed until the company chooses at the close.");
        }}>
          <label className="answer">Fee (% of what is raised)<input type="text" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} /></label>
          <label className="answer">{m.kind === "defence" ? "Forecast sold to the bidder (%)" : "Forecast taken up (%)"}<input type="text" inputMode="decimal" value={takeUp} onChange={(e) => setTakeUp(e.target.value)} /></label>
          <button className="button-primary" disabled={act.busy || !valid}>Pitch</button>
        </form>
      ) : null}
    </div>
  );
}


const CALL_MARK: Record<string, string> = { open: "○ Open", right: "● Right", wrong: "■ Wrong", void: "○ Void" };

function CallRow({ c }: { c: CompetitionCall }) {
  return (
    <tr>
      <th scope="row">{c.empire}{c.ours ? " (yours)" : ""}</th>
      <td>{c.name}: {c.company.name} ({c.company.ticker})</td>
      <td>{c.rival}{c.against_us ? " (yours)" : ""}</td>
      <td>{c.made} → {c.judged}</td>
      <td title={c.outcome ?? undefined}>{CALL_MARK[c.status] ?? c.status}{c.outcome ? ` · ${c.outcome}` : ""}</td>
    </tr>
  );
}

function MakeCall({ d, act }: { d: CompetitionPage; act: Act }) {
  const kinds = (Object.keys(d.can_call) as ("overvalued" | "weak_bank")[]).filter((k) => d.can_call[k]);
  const [kind, setKind] = useState<"overvalued" | "weak_bank">(kinds[0] ?? "overvalued");
  const targets = d.call_targets[kind] ?? [];
  const [company, setCompany] = useState("");
  if (kinds.length === 0) return <p className="muted small">An empire's Asset Manager calls a rival's company overvalued; its Risk Manager calls a rival's bank weak; its head may make either.</p>;
  return (
    <form className="inline-form" onSubmit={(e) => {
      e.preventDefault();
      if (company) act.run(() => api.competitionCall({ kind, company_id: company }), "Called. It is public now, and the record will judge it.");
    }}>
      <label className="answer">The call
        <select value={kind} onChange={(e) => { setKind(e.target.value as "overvalued" | "weak_bank"); setCompany(""); }}>
          {kinds.map((k) => <option key={k} value={k}>{k === "overvalued" ? "A rival's company is overvalued" : "A rival's bank is weak"}</option>)}
        </select>
      </label>
      <label className="answer">On
        <select value={company} onChange={(e) => setCompany(e.target.value)}>
          <option value="">{targets.length ? "choose a company" : "no rival holds enough of any"}</option>
          {targets.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.ticker}): {t.rival} holds {pct(t.rival_stake_bps)}</option>)}
        </select>
      </label>
      <button className="button-primary" disabled={act.busy || !company}>Make the call</button>
    </form>
  );
}

export function CompetitionWork({ onLoggedOut }: Props) {
  const page = useLoad(api.competition, "competition", onLoggedOut);
  const act = useAct(page.reload, onLoggedOut);
  if (page.loading && !page.data) return <Loading what="the competition" />;
  if (page.error || !page.data) return <Failed message={page.error ?? "Could not load the competition."} onRetry={page.reload} />;
  const d = page.data;
  if (!d.ready) return <Panel title="Competition"><p className="small">Competition has not opened in this world yet.</p></Panel>;
  const mine = d.contests.find((c) => c.yours && c.quarter === d.quarter);
  return (
    <>
      <PageHead title="Competition" sub="Work with a winner: against other players, and for your empire" aside={`${d.quarter} · day ${d.day}`} />
      <Band label="Where you stand" columns={4}>
        <BandCell label="Your forecast this quarter" value={mine?.entry ? "● sealed" : mine?.open ? "open" : "—"} note={`forecasts close on day ${d.contest_last_day}`} />
        <BandCell label="Your empire" value={d.empire ?? "—"} note={d.empire ? "its best entry earns its points" : "join one for its points"} />
        <BandCell label="Mandates open" value={d.mandates.filter((m) => m.open).length} note={`pitches close on day ${d.pitch_last_day}`} />
        <BandCell label="What a company trusts you for" value={d.trust_bps === null ? "—" : pct(d.trust_bps)} note={d.can_pitch ? "your level and your empire's record" : "for an empire's banker or head"} />
      </Band>
      {d.protected && <p className="small" role="status">Up to Level {d.protected_level} your work is marked alone while you learn. Competing opens at Level {d.protected_level + 1}; until then you can watch how it goes.</p>}
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      <p className="small"><strong>Ranked work.</strong> Each quarter each build forecasts one figure about one company. When the quarter closes everybody is ranked by how close they came. The best entry from each empire earns it {d.points.places[1]}, {d.points.places[2]} or {d.points.places[3]} points for first, second or third, if it missed by no more than {pct(d.points.most_error_bps)} and at least {d.points.least_empires} empires took part.</p>
      <div className="two-columns">{d.contests.map((c) => <ContestPanel key={c.id} c={c} act={act} />)}</div>
      <Panel title="Mandates" aside={`a win is worth ${d.points.mandate} points and the fee`}>
        <p className="small">A company selling new shares, or facing a hostile takeover bid, invites every empire to pitch. Name a fee and forecast how much of the sale will be taken up (for a defence: how much will be sold to the bidder; the fee is paid only if the bid fails, and wins {d.call_rules.defence} points). The company chooses the lowest fee once it allows for how far it trusts the banker: their level, and how close their empire's past forecasts came. It never chooses by who asked first.</p>
        {d.mandates.length === 0 ? <p className="muted small">No sale of shares is being arranged this quarter.</p> :
          d.mandates.map((m) => <MandateRow key={m.id} m={m} act={act} canPitch={d.can_pitch} />)}
      </Panel>
      <Panel title="Calls on rivals" aside={`judged after ${d.call_rules.quarters} quarters`}>
        <p className="small">Call a rival empire's company overvalued (its price falls by {pct(d.call_rules.fall_bps)} or more), or its bank weak (its credit rating is cut). A rival's company is one another empire holds {pct(d.call_rules.stake_bps)} or more of. A call is public at once, so the rival sees it coming. Right: your empire gains {d.call_rules.right} points and the rival loses {d.call_rules.exposed}. Wrong: your empire loses {d.call_rules.wrong}. If either empire sells the shares while the call is open, it is void. At most {d.call_rules.most_open} open at once.</p>
        <MakeCall d={d} act={act} />
        {d.calls.length > 0 && (
          <table className="dense">
            <thead><tr><th scope="col">Called by</th><th scope="col">The call</th><th scope="col">Against</th><th scope="col">Quarters</th><th scope="col">Result</th></tr></thead>
            <tbody>{d.calls.map((c) => <CallRow key={c.id} c={c} />)}</tbody>
          </table>
        )}
      </Panel>
      <Panel title="The league, by what earned it" aside="this game year">
        {d.scoreboard.length === 0 ? <p className="muted small">No empire has earned points this game year yet.</p> : (
          <table className="dense">
            <thead><tr><th scope="col">Empire</th><th scope="col" className="num">Total</th><th scope="col" className="num">Mandates</th><th scope="col" className="num">Defences</th><th scope="col" className="num">Forecasts</th><th scope="col" className="num">Calls</th><th scope="col" className="num">Exposed</th><th scope="col" className="num">Everything else</th></tr></thead>
            <tbody>{d.scoreboard.map((b) => (
              <tr key={b.empire}><th scope="row">{b.empire}</th><td className="num"><strong>{b.total}</strong></td><td className="num">{b.mandate}</td><td className="num">{b.defence}</td><td className="num">{b.contest}</td><td className="num">{b.call}</td><td className="num">{b.call_exposed}</td><td className="num">{b.other}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
      <Panel title="The sharpest analysts" aside="average miss, over every forecast judged">
        {d.analysts.length === 0 ? <p className="muted small">Nobody has enough forecasts judged yet.</p> : (
          <table className="dense">
            <thead><tr><th scope="col">Analyst</th><th scope="col">Build</th><th scope="col" className="num">Forecasts</th><th scope="col" className="num">Average miss</th><th scope="col" className="num">Firsts</th></tr></thead>
            <tbody>{d.analysts.map((a, i) => (
              <tr key={i}><th scope="row">{a.name}</th><td>{a.build_name}</td><td className="num">{a.entries}</td><td className="num mono">{pct(a.average_error_bps)}</td><td className="num">{a.wins}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
