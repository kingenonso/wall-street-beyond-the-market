import { api, type CourtCase, type CourtClaim } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Notices, useRun, type Run } from "./Newsroom";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";

/** Stage 11: the courts, as a docket. The claim, the number, the lines that prove it, and a settle-or-fight choice.
 * Never anybody else's private business: the docket is public, and a player's own cases are their own. */

const KIND_WORDS: Record<string, string> = {
  insider: "Dealing on confidential information",
  manipulation: "Manipulation: ramping and wash trading",
  undisclosed_stake: "An undisclosed stake",
  naked_short: "A naked short",
};
const STATUS_WORDS: Record<string, string> = { open: "Open", settled: "Settled", judged: "Judged", withdrawn: "Withdrawn" };
const pct = (bps: number) => `${(bps / 100).toFixed(1).replace(/\.0$/, "")}%`;
const day = (at: string) => new Date(at).toLocaleDateString("en-NG", { timeZone: "Africa/Lagos", day: "numeric", month: "short", year: "numeric" });

function line(l: Record<string, string | number | null>): string {
  const what = String(l.what ?? "");
  if (what === "trade") return `${l.side === "bought" ? "Bought" : "Sold"} ${l.quantity} at ${formatNaira(String(l.price))}`;
  if (what === "wash trade") return `Traded with itself: ${l.quantity} at ${formatNaira(String(l.price))}`;
  if (what === "bought") return `Bought ${l.quantity} at ${formatNaira(String(l.price))}`;
  if (what === "sold") return `Sold ${l.quantity} at ${formatNaira(String(l.price))}`;
  if (what === "holding") return `Held ${pct(Number(l.held_bps))} of ${l.ticker}, made public ${pct(Number(l.disclosed_bps))}`;
  if (what === "short") return `${l.shares} shares of ${l.ticker}, bought in at ${formatNaira(String(l.bought_in_at))}`;
  return what;
}

function Evidence({ c }: { c: CourtCase }) {
  const lines = c.evidence?.lines ?? [];
  if (!lines.length) return null;
  return (
    <details className="court-evidence">
      <summary className="small muted">The lines that prove it ({lines.length})</summary>
      <ul className="small">
        {lines.map((l, i) => (
          <li key={i}>{line(l)}{l.at ? ` · ${day(String(l.at))}` : ""}</li>
        ))}
      </ul>
    </details>
  );
}

function CaseCard({ c, mine, act }: { c: CourtCase; mine: boolean; act: Run }) {
  return (
    <div className="fact-row court-case">
      <div>
        <div className="strong">
          {KIND_WORDS[c.kind] ?? c.kind} <span className="muted small">· {c.ticker ?? "the market"}</span>{" "}
          <span className={c.status === "open" ? "tag" : c.status === "judged" ? "tag-bad" : "tag-good"}>{STATUS_WORDS[c.status] ?? c.status}</span>
        </div>
        <div className="small">{c.words}</div>
        <div className="small muted">
          {c.claimant} against {c.defendant} · claim {formatNaira(c.amount)}
          {c.status === "open" ? ` · settling costs ${formatNaira(c.settle_price)}` : ""}
          {c.owed !== "0" ? ` · still owed ${formatNaira(c.owed)}` : ""}
          {c.ban_quarters ? ` · banned from trading for ${c.ban_quarters} quarters` : ""}
        </div>
        <Evidence c={c} />
      </div>
      {mine && c.status === "open" && (
        <div className="intel-actions">
          <button className="button-outline" disabled={act.busy}
                  onClick={() => act.run(async () => ({ result: await api.courtAnswer(c.id, "settle") }), "Settled.")}>
            Settle for {formatNaira(c.settle_price)}
          </button>
          <button className="button-quiet" disabled={act.busy}
                  onClick={() => act.run(async () => ({ result: await api.courtAnswer(c.id, "fight") }), "Judged.")}>
            Fight it
          </button>
        </div>
      )}
    </div>
  );
}

function ClaimCard({ claim, act }: { claim: CourtClaim; act: Run }) {
  return (
    <div className="fact-row">
      <div>
        <div className="strong">{KIND_WORDS[claim.kind] ?? claim.kind} <span className="muted small">· {claim.ticker ?? "the market"}</span></div>
        <div className="small">{claim.words}</div>
        <div className="small muted">Against {claim.defendant} · claim {formatNaira(claim.amount)} · bond {formatNaira(claim.bond)}</div>
      </div>
      <div className="intel-actions">
        <button className="button-outline" disabled={act.busy}
                onClick={() => act.run(async () => ({
                  result: await api.courtBring({ kind: claim.kind, defendant_id: claim.defendant_id, ...(claim.company_id ? { company_id: claim.company_id } : {}) }),
                }), "The case is on the docket.")}>
          Bring it
        </button>
      </div>
    </div>
  );
}

export function CourtWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.court, "court", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  if (loading && !data) return <Loading what="the docket" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  if (!data.ready) {
    return <Panel title="The courts"><p className="muted">The courts open with the next stage.</p></Panel>;
  }
  const defending = data.mine.defending.filter((c) => c.status === "open");
  return (
    <>
      <Notices act={act} />
      {data.mine.banned_until !== null && (
        <p className="error" role="alert">You are banned from trading until quarter {data.mine.banned_until}: the court's order.</p>
      )}
      <Panel title="The docket" aside={`${data.docket.length} open`}>
        {data.docket.length === 0 && <p className="muted">No case is open. The regulator reads the record each quarter.</p>}
        {data.docket.map((c) => <CaseCard key={c.id} c={c} mine={defending.some((d) => d.id === c.id)} act={act} />)}
        <p className="muted small">A case is a claim with a number, and the lines of the record that prove it. The court does not decide guilt: it
          proves the number and makes it be paid. A defendant who does not answer is judged at the next close.</p>
      </Panel>
      {data.claims.length > 0 && (
        <Panel title="Claims you could bring" aside="you were on the other side">
          {data.claims.map((claim, i) => <ClaimCard key={`${claim.kind}-${claim.defendant_id}-${i}`} claim={claim} act={act} />)}
          <p className="muted small">Bringing a case needs a <Term word="Litigation bond">bond</Term> of {pct(data.rules.bond_bps)} of the claim
            (at least {formatNaira(data.rules.bond_floor)}). It comes back if the claim is proved, and is lost if it is not.</p>
        </Panel>
      )}
      <Panel title="Your cases" aside={`${data.mine.defending.length} defending · ${data.mine.brought.length} brought`}>
        {data.mine.defending.length === 0 && data.mine.brought.length === 0 && <p className="muted">None. Keep it that way.</p>}
        {data.mine.defending.map((c) => <CaseCard key={`d${c.id}`} c={c} mine act={act} />)}
        {data.mine.brought.map((c) => <CaseCard key={`b${c.id}`} c={c} mine={false} act={act} />)}
      </Panel>
      <Panel title="The regulator" aside={`budget ${formatNaira(data.regulator.budget)}`}>
        <div className="small">
          It has brought {data.regulator.brought} case{data.regulator.brought === 1 ? "" : "s"}: {data.regulator.won} judged,
          {" "}{data.regulator.settled} settled, and {formatNaira(data.regulator.fines)} of fines ordered.
        </div>
        <div className="small muted">Proving one case costs it {formatNaira(data.regulator.cost)}, paid to the Treasury. Half of every fine it wins
          funds it, so it can only bring what it can afford to prove.</div>
        <div className="small muted">The compensation fund holds {formatNaira(data.fund)}: what the court has ordered paid to the people a wrong
          was done to.</div>
      </Panel>
      <Panel title="Your legal record" aside="public">
        {data.mine.record.length === 0 && <p className="muted">Nothing on it.</p>}
        {data.mine.record.map((r, i) => (
          <div key={i} className="fact-row small"><span>{day(r.at)} · {r.kind}</span><span>{r.words}</span></div>
        ))}
      </Panel>
    </>
  );
}

export function CourtRail() {
  const { data } = useLoad(api.court, "court", () => undefined);
  if (!data?.ready) return <></>;
  return (
    <>
      <Panel title="The court" aside="a docket, not a courtroom">
        <div className="small">The regulator's budget: <span className="strong">{formatNaira(data.regulator.budget)}</span></div>
        <div className="small">The compensation fund: <span className="strong">{formatNaira(data.fund)}</span></div>
        <div className="small muted">Open cases: {data.docket.length}</div>
        {data.mine.banned_until !== null && <div className="small error">Banned from trading until quarter {data.mine.banned_until}.</div>}
      </Panel>
      <Panel title="What the court orders">
        <div className="small">Settling costs {pct(data.rules.settle_bps)} of the claim, paid at once.</div>
        <div className="small">A judgment adds a fine and the winner's costs, paid down over quarters.</div>
        <div className="small muted">A manipulation or a naked short also carries a trading ban. A judgment costs {data.rules.reputation} points of
          reputation.</div>
      </Panel>
    </>
  );
}
