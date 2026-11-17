import { useState } from "react";
import { api, type CourtCase, type CourtClaim, type JuryDuty } from "./api";
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
  insurance_fraud: "Insurance fraud",
  front_running: "Trading ahead of a client on the Floor",
  order_leak: "Passing on a client's order on the Floor",
  collusion: "Banks agreeing their prices on the Floor",
  union_bribery: "Paying a union leader",
  jury_tampering: "Tampering with a jury",
};
const STATUS_WORDS: Record<string, string> = { open: "Open", jury: "Before a jury", verdict: "Verdict, open to appeal", appeal: "Before an appeal jury",
  settled: "Settled", judged: "Judged", withdrawn: "Withdrawn" };
const PROVED_WORDS: Record<number, string> = { 0: "not proved", 2500: "a quarter proved", 5000: "half proved", 7500: "three quarters proved", 10000: "all proved" };
const when = (iso: string) => new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "short", hour: "2-digit", minute: "2-digit" });
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
        <JuryLine c={c} />
        {mine && c.status === "open" && <Answer c={c} act={act} />}
        {c.panel && <PartyPanel c={c} act={act} />}
      </div>
    </div>
  );
}

/** Where the jury stands on a case, for everybody: how many have voted, then every vote and its reason. */
function JuryLine({ c }: { c: CourtCase }) {
  const j = c.jury;
  return (
    <>
      {c.defence && <div className="small"><span className="strong">The defence:</span> "{c.defence}"</div>}
      {c.claim_note && <div className="small"><span className="strong">The claim:</span> "{c.claim_note}"</div>}
      {j && j.first && (
        <div className="small">The first jury found the claim {PROVED_WORDS[j.first.proved_bps]}{j.first.proved_bps ? `, with a ${j.first.penalty} penalty` : ""}; the {j.appealed_by} appealed.
          {j.first_votes && <ul className="jury-votes">{j.first_votes.map((v) => <li key={v.seat}>Juror {v.seat}: {PROVED_WORDS[v.proved_bps]}, {v.penalty}{v.reason ? `. "${v.reason}"` : ""}</li>)}</ul>}
        </div>
      )}
      {j && j.sitting && <div className="small">{j.round === 2 ? "An appeal jury" : "A jury"} of {j.seats} is sitting: {j.voted} ha{j.voted === 1 ? "s" : "ve"} voted. Votes close {when(j.until)} Lagos time.{j.struck ? ` ${j.struck} juror${j.struck === 1 ? " was" : "s were"} challenged and replaced.` : ""}</div>}
      {j && !j.sitting && (
        <div className="small">
          {c.status === "verdict"
            ? `The jury found the claim ${PROVED_WORDS[c.proved_bps ?? 10000]}${c.proved_bps ? `, with a ${c.penalty} penalty` : ""}. It takes effect ${when(c.appeal_until!)} Lagos time unless the side that lost appeals.`
            : c.outcome === "acquitted" ? `The ${j.round === 2 ? "appeal " : ""}jury acquitted.` : `The ${j.round === 2 ? "appeal " : ""}jury found the claim ${PROVED_WORDS[c.proved_bps ?? 10000]}, with a ${c.penalty} penalty.`}
          <ul className="jury-votes">{j.votes.map((v) => <li key={v.seat}>Juror {v.seat}: {PROVED_WORDS[v.proved_bps]}, {v.penalty}{v.reason ? `. "${v.reason}"` : ""}</li>)}</ul>
        </div>
      )}
      {!j && c.outcome === "acquitted" && <div className="small">Acquitted.</div>}
    </>
  );
}

/** The defendant's answer: settle, let the judge decide, or ask for a jury with a statement. */
function Answer({ c, act }: { c: CourtCase; act: Run }) {
  const [defence, setDefence] = useState("");
  return (
    <div className="court-answer">
      <div className="intel-actions">
        <button className="button-outline" disabled={act.busy}
                onClick={() => act.run(async () => ({ result: await api.courtAnswer(c.id, "settle") }), "Settled.")}>
          Settle for {money(c.settle_price)}
        </button>
        <button className="button-quiet" disabled={act.busy}
                onClick={() => act.run(async () => ({ result: await api.courtAnswer(c.id, "fight") }), "Judged.")}>
          Let the judge decide
        </button>
        <button className="button-quiet" disabled={act.busy}
                onClick={() => act.run(async () => ({ result: await api.courtAnswer(c.id, "jury", defence) }), "A jury is summoned.")}>
          Ask for a jury
        </button>
      </div>
      <textarea className="court-statement" maxLength={600} rows={2} value={defence} onChange={(e) => setDefence(e.target.value)}
                placeholder="Your statement to the jury, if you ask for one (optional, up to 600 characters)" aria-label="Your statement to the jury" />
      <p className="small muted">The judge finds the whole claim proved, at the standard penalty. A jury of players may find all of it proved, part of it, or
        none, and may ask for a lenient or a harsh penalty. Acquitted, you owe nothing, and a player who brought it loses the bond to you.</p>
    </div>
  );
}

/** Jury duty: the cases this player sits on, with the vote; and their fair-verdict record. */
function JuryDutyPanel({ d, act }: { d: JuryDuty; act: Run }) {
  if (d.sitting.length === 0 && d.record.summoned === 0) return null;
  return (
    <Panel title="Jury duty" aside={`${d.record.voted} votes · ${d.record.agreed} matched the verdict · ${money(d.record.fees)} in fees`}>
      {d.sitting.length === 0 && <p className="muted small">You are not sitting on a jury now.</p>}
      {d.sitting.map((c) => <Juror key={c.id} c={c} act={act} />)}
      <p className="small muted">Juries of {d.rules.size} are drawn from players with no tie to either side. Each juror reads the case file and votes once:
        how much of the claim the record proves, and the penalty. The middle vote decides. Every juror who votes is paid {money(d.rules.fee)} by
        the Treasury, and a vote that matches the verdict adds a point of reputation. With fewer than {d.rules.quorum} votes in {d.rules.hours} hours,
        the judge decides. Each side may challenge one juror in the first {d.rules.challenge_hours} hours. A jury's verdict waits {d.rules.appeal_hours} hours,
        and the side that lost may pay for a fresh jury, whose verdict is final.</p>
    </Panel>
  );
}

function Juror({ c, act }: { c: JuryDuty["sitting"][number]; act: Run }) {
  const [proved, setProved] = useState(10000);
  const [penalty, setPenalty] = useState("standard");
  const [reason, setReason] = useState("");
  return (
    <div className="fact-row court-case">
      <div>
        <div className="strong">{KIND_WORDS[c.kind] ?? c.kind} <span className="muted small">· {c.ticker ?? "the market"}</span> <span className="tag">Your jury</span></div>
        <div className="small">{c.words}</div>
        <div className="small muted">{c.claimant} against {c.defendant} · claim {money(c.amount)} · votes close {when(c.jury_until)} Lagos time</div>
        <Evidence c={c} />
        {c.defence && <div className="small"><span className="strong">The defence:</span> "{c.defence}"</div>}
        {c.claim_note && <div className="small"><span className="strong">The claim:</span> "{c.claim_note}"</div>}
        {c.appeal_round && <div className="small tag">An appeal: a fresh look at the case</div>}
        {c.offers.map((o) => (
          <div key={o.id} className="small change-down">
            {o.who} offers you {money(o.amount)} to vote {o.wants === "acquit" ? "to acquit" : "to find it all proved"}. Taking it is a crime; reporting it earns you reputation.{" "}
            <button className="button-outline small" disabled={act.busy} onClick={() => act.run(async () => ({ result: await api.courtOfferAnswer(o.id, false) }), "Reported. The offer is on the record.")}>Report it</button>{" "}
            <button className="button-quiet small" disabled={act.busy} onClick={() => act.run(async () => ({ result: await api.courtOfferAnswer(o.id, true) }), "You took the money.")}>Take it</button>
          </div>
        ))}
        {c.my_vote ? (
          <div className="small strong">You voted: {PROVED_WORDS[c.my_vote.proved_bps]}, {c.my_vote.penalty}. The verdict comes when the jury closes.</div>
        ) : (
          <div className="court-answer">
            <label className="small">How much does the record prove?{" "}
              <select value={proved} onChange={(e) => setProved(Number(e.target.value))}>
                {[10000, 7500, 5000, 2500, 0].map((v) => <option key={v} value={v}>{PROVED_WORDS[v]}</option>)}
              </select>
            </label>{" "}
            <label className="small">Penalty{" "}
              <select value={penalty} onChange={(e) => setPenalty(e.target.value)} disabled={proved === 0}>
                <option value="lenient">lenient (half the fine)</option><option value="standard">standard</option><option value="harsh">harsh (half again)</option>
              </select>
            </label>
            <input className="court-statement" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)}
                   placeholder="Your reason, shown with your vote but not your name (optional)" aria-label="Your reason" />
            <button disabled={act.busy} onClick={() => act.run(async () => ({ result: await api.courtVote(c.id, proved, proved === 0 ? "standard" : penalty, reason) }), "Your vote is in.")}>Cast your vote</button>
          </div>
        )}
      </div>
    </div>
  );
}

/** What a side sees of its jury: who sits, a challenge, an appeal, and the crime of approaching a juror. */
function PartyPanel({ c, act }: { c: CourtCase; act: Run }) {
  const p = c.panel!;
  const [seat, setSeat] = useState(p.jurors?.[0]?.seat ?? 1);
  const [amount, setAmount] = useState("1000000");
  const [wants, setWants] = useState<"acquit" | "convict">(p.side === "defendant" ? "acquit" : "convict");
  const [sure, setSure] = useState(false);
  const canChallenge = !!p.jurors && !p.challenged && !!p.challenge_until && new Date(p.challenge_until) > new Date();
  const naira = Number(amount.replace(/[,\s]/g, ""));
  return (
    <div className="court-answer jury-panel">
      {p.jurors && (
        <div className="small">
          <span className="strong">Your jury:</span>{" "}
          {p.jurors.map((j) => (
            <span key={j.seat} className="jury-seat">
              {j.seat}. {j.name}{j.voted ? " (voted)" : ""}
              {canChallenge && !j.voted && (
                <button className="button-quiet small" disabled={act.busy}
                        onClick={() => act.run(async () => ({ result: await api.courtChallenge(c.id, j.seat) }), `Juror ${j.seat} is struck out; another is drawn.`)}>challenge</button>
              )}
            </span>
          ))}
          <div className="muted">{p.challenged ? "You have used your challenge." : canChallenge ? `You may strike out one juror who has not voted, until ${when(p.challenge_until!)}.` : "The time to challenge has passed."}</div>
        </div>
      )}
      {p.jurors && (
        <details className="union-quiet">
          <summary className="small">Approach a juror</summary>
          <p className="small change-down">Offering a juror money for a vote is a crime. The juror may report it at once. One who takes it may tell later,
            and the chance rises every time you do it. Once it is out, the regulator or the other side can bring a case, with a fine of twice the offer and a
            trading ban.</p>
          <select value={seat} onChange={(e) => setSeat(Number(e.target.value))} aria-label="Which juror">
            {p.jurors.filter((j) => !j.voted).map((j) => <option key={j.seat} value={j.seat}>{j.seat}. {j.name}</option>)}
          </select>{" "}
          <input className="mono" inputMode="numeric" aria-label="How much, in naira" value={amount} onChange={(e) => setAmount(e.target.value)} />{" "}
          <select value={wants} onChange={(e) => setWants(e.target.value as "acquit" | "convict")} aria-label="For what vote">
            <option value="acquit">to acquit</option><option value="convict">to find it all proved</option>
          </select>{" "}
          <label className="small"><input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} /> I understand the risk</label>{" "}
          <button className="button-outline small" disabled={act.busy || !sure || !(naira > 0)}
                  onClick={() => act.run(async () => ({ result: await api.courtOffer(c.id, seat, Math.round(naira * 100), wants) }), "The offer is made. The juror will take it or report it.")}>Make the offer</button>
        </details>
      )}
      {p.can_appeal && (
        <div className="small">
          <button className="button-outline" disabled={act.busy}
                  onClick={() => act.run(async () => ({ result: await api.courtAppeal(c.id) }), "Appealed: a fresh jury is summoned.")}>Appeal for {money(p.appeal_fee)}</button>{" "}
          <span className="muted">A fresh jury, none of the first, hears the case, and its verdict is final. The fee comes back if the appeal wins you anything.</span>
        </div>
      )}
    </div>
  );
}

function ClaimantNote({ c, act }: { c: CourtCase; act: Run }) {
  const [note, setNote] = useState(c.claim_note ?? "");
  return (
    <div className="court-answer">
      <textarea className="court-statement" maxLength={600} rows={2} value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="Your statement to the jury for the claim" aria-label="Your statement to the jury" />
      <button className="button-outline" disabled={act.busy || !note.trim()} onClick={() => act.run(async () => ({ result: await api.courtNote(c.id, note) }), "Your statement is before the jury.")}>Put it to the jury</button>
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
        <div className="work-sub">The regulator or a player brings a case, the defendant settles, lets the judge decide, or asks for a jury of players. Modelled on Nigeria's Investments and Securities Tribunal</div>
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
      {data.jury_duty && <JuryDutyPanel d={data.jury_duty} act={act} />}
      <Panel title="The docket" aside={`${data.docket.length} open`}>
        {data.docket.length === 0 && <p className="muted">No case is open. The regulator reads the record each quarter.</p>}
        {data.docket.map((c) => <CaseCard key={c.id} c={c} mine={defending.some((d) => d.id === c.id)} act={act} />)}
        <p className="muted small">A case is a claim with a number, and the lines of the record that prove it. The tribunal does not decide guilt: it
          proves the number and makes it be paid. A defendant may settle, let the judge decide, or ask for a jury of players. One who does not
          answer is judged at the next close.</p>
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
        {data.mine.brought.map((c) => (
          <div key={`b${c.id}`}>
            <CaseCard c={c} mine={false} act={act} />
            {c.status === "jury" && <ClaimantNote c={c} act={act} />}
          </div>
        ))}
      </Panel>
      {(data.verdicts ?? []).length > 0 && (
        <Panel title="Recent jury verdicts" aside="every vote in the open, no names">
          {data.verdicts!.map((c) => <CaseCard key={`v${c.id}`} c={c} mine={false} act={act} />)}
        </Panel>
      )}
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
