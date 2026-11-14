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

/** A figure the server may leave out. "null" is not a number, and BigInt("null") throws — which, with no error
 * boundary on the page, would take the whole game down rather than one line of a case. */
function money(kobo: unknown): string {
  if (kobo === null || kobo === undefined || kobo === "") return "—";
  try {
    return formatNaira(String(kobo));
  } catch {
    return "—";
  }
}

/** A count or a rate the server may leave out. */
function count(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function line(l: Record<string, string | number | null>): string {
  const what = String(l.what ?? "");
  if (what === "trade") return `${l.side === "bought" ? "Bought" : "Sold"} ${count(l.quantity)} at ${money(l.price)}`;
  if (what === "wash trade") return `Traded with itself: ${count(l.quantity)} at ${money(l.price)}`;
  if (what === "bought") return `Bought ${count(l.quantity)} at ${money(l.price)}`;
  if (what === "sold") return `Sold ${count(l.quantity)} at ${money(l.price)}`;
  if (what === "holding") return `Held ${pct(Number(l.held_bps ?? 0))} of ${l.ticker}, made public ${pct(Number(l.disclosed_bps ?? 0))}`;
  if (what === "short") return `${count(l.shares)} shares of ${l.ticker}, bought in at ${money(l.bought_in_at)}`;
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
          {c.claimant} against {c.defendant} · claim {money(c.amount)}
          {c.status === "open" ? ` · settling costs ${money(c.settle_price)}` : ""}
          {c.owed !== "0" ? ` · still owed ${money(c.owed)}` : ""}
          {c.ban_quarters ? ` · banned from trading for ${c.ban_quarters} quarters` : ""}
        </div>
        <Evidence c={c} />
      </div>
      {mine && c.status === "open" && (
        <div className="intel-actions">
          <button className="button-outline" disabled={act.busy}
                  onClick={() => act.run(async () => ({ result: await api.courtAnswer(c.id, "settle") }), "Settled.")}>
            Settle for {money(c.settle_price)}
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
        <div className="small muted">Against {claim.defendant} · claim {money(claim.amount)} · bond {money(claim.bond)}</div>
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

/** The page's head, the same ruled head every other screen opens with. */
function CourtHead({ aside }: { aside?: React.ReactNode }) {
  return (
    <div className="work-head">
      <div>
        <h1>The tribunal</h1>
        <div className="work-sub">The regulator or a player brings a case, the defendant settles or fights it, and the tribunal finds the number from the record. Modelled on Nigeria's Investments and Securities Tribunal</div>
      </div>
      {aside && <span className="muted small">{aside}</span>}
    </div>
  );
}

/** A server that has the website but not the court yet answers "Not Found" here. That is the stage not being built,
 * not the player's connection, so it is said plainly instead of being shown as a fault with a Try again button. */
function OpensLater() {
  return (
    <>
      <CourtHead />
      <Panel title="The tribunal">
        <p className="muted">The tribunal opens with the next stage. Until then no case is brought, and nothing here is owed.</p>
      </Panel>
    </>
  );
}

export function CourtWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.court, "court", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  if (loading && !data) return <Loading what="the docket" />;
  if (error && !data) {
    if (/not found/i.test(error)) return <OpensLater />;
    return <Failed message={error} onRetry={reload} />;
  }
  if (!data) return null;
  if (!data.ready) return <OpensLater />;
  const defending = data.mine.defending.filter((c) => c.status === "open");
  return (
    <>
      <CourtHead aside={data.docket.length > 0 ? `${data.docket.length} open` : "nothing open"} />
      <Notices act={act} />
      {data.mine.banned_until !== null && (
        <p className="error" role="alert">You are banned from trading until quarter {data.mine.banned_until}: the tribunal's order.</p>
      )}
      <Panel title="The docket" aside={`${data.docket.length} open`}>
        {data.docket.length === 0 && <p className="muted">No case is open. The regulator reads the record each quarter.</p>}
        {data.docket.map((c) => <CaseCard key={c.id} c={c} mine={defending.some((d) => d.id === c.id)} act={act} />)}
        <p className="muted small">A case is a claim with a number, and the lines of the record that prove it. The tribunal does not decide guilt: it
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
        <div className="small muted">The compensation fund holds {formatNaira(data.fund)}: what the tribunal has ordered paid to the people a wrong
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
      <Panel title="The tribunal" aside="a list of cases, not a courtroom">
        <div className="small">The regulator's budget: <span className="strong">{formatNaira(data.regulator.budget)}</span></div>
        <div className="small">The compensation fund: <span className="strong">{formatNaira(data.fund)}</span></div>
        <div className="small muted">Open cases: {data.docket.length}</div>
        {data.mine.banned_until !== null && <div className="small error">Banned from trading until quarter {data.mine.banned_until}.</div>}
      </Panel>
      <Panel title="What the tribunal orders">
        <div className="small">Settling costs {pct(data.rules.settle_bps)} of the claim, paid at once.</div>
        <div className="small">A judgment adds a fine and the winner's costs, paid down over quarters.</div>
        <div className="small muted">A manipulation or a naked short also carries a trading ban. A judgment costs {data.rules.reputation} points of
          reputation.</div>
      </Panel>
    </>
  );
}
