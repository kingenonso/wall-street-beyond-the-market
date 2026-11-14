// Insurance, a page under Money (owner, 9 November 2026).
//
// Four policies: property and premises, directors' and officers', income protection and the personal umbrella. The
// page shows what each would cost on the player's own record today and what the premium is made of, the cover held,
// the losses on the record in the last year and what was decided on each claim, and what cover does for a personal
// loan. Every figure is the server's: the page names a policy and a cover, or a loss on the record, and never an amount
// to be paid.

import { useState } from "react";
import { api, ApiError, type InsurancePage, type InsurancePolicy, type Player } from "./api";
import { asKobo } from "./Empire";
import { formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Band, BandCell, Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void; onChanged?: () => void };

function useAct(reload: () => void, onLoggedOut: () => void, onChanged?: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(ask: () => Promise<InsurancePage>, done: (page: InsurancePage) => string) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const page = await ask();
      setNotice(done(page));
      reload();
      onChanged?.();
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

const DECISION: Record<string, string> = { paid: "● Paid", paying: "● Paying", declined: "○ Declined", refused: "■ Refused" };

function PolicyPanel({ p, act, barred }: { p: InsurancePolicy; act: Act; barred: boolean }) {
  const [cover, setCover] = useState("");
  const [excess, setExcess] = useState("");
  const held = p.held;
  const q = p.quote;
  return (
    <Panel title={p.name} aside={held ? `held · ${formatNaira(held.premium)} a quarter` : p.most_cover === "0" ? "nothing to insure" : "not held"}>
      <p className="small">{p.words}</p>
      {held ? (
        <>
          <div className="row small"><span>Cover, for each loss</span><span className="mono">{formatNaira(held.cover)}</span></div>
          <div className="row small"><span>Your excess, for each loss</span><span className="mono">{formatNaira(held.excess)}</span></div>
          <div className="row small"><span>Held since</span><span>{held.since} · paid to the end of {held.paid_through}</span></div>
          <div className="row small"><span>No-claims record</span><span>{Math.floor(p.clean_quarters / 4)} clean {Math.floor(p.clean_quarters / 4) === 1 ? "year" : "years"} · {formatPercent(p.no_claims_bps, 0)} off</span></div>
          <div className="inline-form">
            <button className="button-outline" disabled={act.busy}
              onClick={() => act.run(() => api.insuranceCancel({ kind: p.kind }), () => "Cancelled. The quarter already paid for is not refunded; your no-claims record is kept.")}>Cancel the policy</button>
          </div>
        </>
      ) : q ? (
        <>
          <table className="dense">
            <tbody>
              <tr><th scope="row" style={{ whiteSpace: "normal" }}>The expected loss, from the last year of the record</th><td className="num mono">{formatNaira(q.expected_loss)}</td></tr>
              <tr><th scope="row">The insurer's loading</th><td className="num mono">{formatNaira(q.loading)}</td></tr>
              <tr><th scope="row">A charge on the cover</th><td className="num mono">{formatNaira(q.on_cover)}</td></tr>
              {q.discount !== "0" && <tr><th scope="row">No-claims discount ({formatPercent(q.no_claims_bps, 0)})</th><td className="num mono">− {formatNaira(q.discount)}</td></tr>}
              <tr><th scope="row" style={{ whiteSpace: "normal" }}><strong>A quarter's premium, at the most cover</strong></th><td className="num mono"><strong>{formatNaira(q.premium)}</strong></td></tr>
            </tbody>
          </table>
          <form className="inline-form" onSubmit={(e) => {
            e.preventDefault();
            const c = asKobo(cover);
            if (c) act.run(() => api.insuranceBuy({ kind: p.kind, cover_kobo: c, excess_kobo: asKobo(excess) ?? 0 }),
                           (page) => `Bought. The first quarter's premium, ${formatNaira(String(page.result?.premium ?? "0"))}, has been paid.`);
          }}>
            <label className="answer">Cover (₦)<input type="text" inputMode="decimal" value={cover} onChange={(e) => setCover(e.target.value)} placeholder={`up to ${formatNaira(p.most_cover)}`} /></label>
            <label className="answer">Excess (₦)<input type="text" inputMode="decimal" value={excess} onChange={(e) => setExcess(e.target.value)} placeholder="0" /></label>
            <button className="button-primary" disabled={act.busy || barred || !asKobo(cover)}>Buy the policy</button>
          </form>
          <p className="muted small">The premium is worked out again at each quarter's close from the record, and taken from your cash; if you cannot pay it, the cover lapses.</p>
        </>
      ) : null}
    </Panel>
  );
}

export function InsuranceWork({ onLoggedOut, onChanged }: Props) {
  const page = useLoad(api.insurance, "insurance", onLoggedOut);
  const act = useAct(page.reload, onLoggedOut, onChanged);
  if (page.loading && !page.data) return <Loading what="your insurance" />;
  if (page.error || !page.data) return <Failed message={page.error ?? "Could not load your insurance."} onRetry={page.reload} />;
  const d = page.data;
  if (!d.ready) return <Panel title="Insurance"><p className="small">The insurers have not opened in this world yet.</p></Panel>;
  const b = d.borrowing;
  const held = d.policies.filter((p) => p.held);
  return (
    <>
      <PageHead title="Insurance" sub="Four policies, priced from the game's own record" aside={d.period} />
      <Band label="Your cover" columns={4}>
        <BandCell label="Policies held" value={held.length} note={held.length === 0 ? "no cover" : held.map((p) => p.name).join(", ")} />
        <BandCell label="Cover a lender counts" value={formatNaira(b.cover)} note={`against ${formatNaira(b.debt)} owed on loans and mortgages`} />
        <BandCell label="Your personal loan spread" value={formatPercent(b.spread_bps)}
          note={b.spread_bps < b.spread_uninsured_bps ? `${formatPercent(b.spread_uninsured_bps)} without cover` : `${formatPercent(b.step_bps, 0)} less with cover of half your debt, ${formatPercent(b.step_bps * 2, 0)} with all of it`} />
        <BandCell label="The insurers' account" value={formatNaira(d.pool)} note="it pays only what it holds" />
      </Band>
      <p className="small">{d.honest}</p>
      {d.barred && <p className="small change-down" role="status">■ No insurer will write for you again: two of your claims were refused because you caused the loss.</p>}
      {act.error && <p className="small change-down" role="alert">{act.error}</p>}
      {act.notice && <p className="small" role="status">{act.notice}</p>}
      <div className="two-columns">
        {d.policies.map((p) => <PolicyPanel key={p.kind} p={p} act={act} barred={d.barred} />)}
      </div>
      <Panel title="Losses on your record" aside="the last year">
        {d.losses.length === 0 ? <p className="small">No loss on your record in the last year that a policy could answer.</p> : (
          <table className="dense">
            <thead><tr><th scope="col">Quarter</th><th scope="col">What happened</th><th scope="col" className="num">The loss</th><th scope="col">Claim</th></tr></thead>
            <tbody>
              {d.losses.map((x) => (
                <tr key={x.key}>
                  <td>{x.quarter}</td>
                  <th scope="row">{x.words}</th>
                  <td className="num mono">{formatNaira(x.loss)}</td>
                  <td>{x.claim ? <span title={x.claim.reason}>{DECISION[x.claim.decision] ?? x.claim.decision} · {formatNaira(x.claim.paid)}</span> : (
                    <button className="button-quiet" disabled={act.busy}
                      onClick={() => act.run(() => api.insuranceClaim({ loss: x.key }), (after) => String(after.result?.words ?? "Claimed."))}>Claim</button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted small">The insurer reads the same record: whether cover was in force and paid for when the loss happened, and who caused it. A claim on a loss you caused is refused, the premium kept, and referred to the tribunal; a second ends all your cover for good.</p>
      </Panel>
      {d.claims.length > 0 && (
        <Panel title="Your claims">
          <table className="dense">
            <thead><tr><th scope="col">Quarter</th><th scope="col">Policy</th><th scope="col">Decision</th><th scope="col" className="num">Owed</th><th scope="col" className="num">Paid</th></tr></thead>
            <tbody>
              {d.claims.map((c, i) => (
                <tr key={i}><td>{c.quarter}</td><th scope="row">{c.name}</th><td>{DECISION[c.decision] ?? c.decision} · <span className="muted">{c.reason}</span></td>
                  <td className="num mono">{formatNaira(c.payable)}</td><td className="num mono">{formatNaira(c.paid)}</td></tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </>
  );
}
