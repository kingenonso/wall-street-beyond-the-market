// The gap stage, Part 2: zoning and rezoning, claims, valuing a property three ways, developing a plot, selling
// outside the Auction House in twelve steps, infrastructure projects, households' home loans, and property funds.

import { useState } from "react";
import { api, ApiError, type Development, type MyLot, type PrivateSale, type PropertyFunds, type PropertyMarket, type Valuation } from "./api";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import type { Act } from "./Property";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";

const KIND_NAMES: Record<string, string> = { office: "Offices", home: "Homes", shop: "Shops", warehouse: "Warehouse", factory: "Factory",
  farmland: "Farmland", hotel: "Hotel", mall: "Shopping mall" };
const STEP_NAMES: Record<string, string> = {
  seller: "1. Confirm the seller", title: "2. Title search", claims: "3. Claims search", zoning: "4. Zoning check", valuation: "5. Valuation",
  money: "6. The money", terms: "7. The terms", consent_asked: "8. Ask the Governor's consent", consent: "9. Consent granted",
  contract: "10. The contract", registered: "11. Registered at the Land Registry", handover: "12. Handover",
};
const CHECKS = ["seller", "title", "claims", "zoning", "valuation"];

function ValuationBox({ id }: { id: number }) {
  const [v, setV] = useState<Valuation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function load() {
    try { setV(await api.valuation(id)); } catch (problem) { setErr(problem instanceof ApiError ? problem.message : "Could not reach the server."); }
  }
  if (!v) return <><button className="button-quiet" onClick={load}>Value it three ways</button>{err && <span className="error small"> {err}</span>}</>;
  return (
    <div className="small" style={{ width: "100%" }}>
      <div className="row"><span>Comparable sales <span className="muted">({v.comparable_note})</span></span><span className="mono">{formatCompact(v.comparables)}</span></div>
      <div className="row"><span>Income <span className="muted">(a year's rent {formatCompact(v.yearly_rent)}, less costs, over a {formatPercent(v.yield_bps, 1)} yield)</span></span><span className="mono">{formatCompact(v.income)}</span></div>
      <div className="row"><span>Cost <span className="muted">(land {formatCompact(v.land)} + building again {formatCompact(v.rebuild)})</span></span><span className="mono">{formatCompact(v.cost)}</span></div>
    </div>
  );
}

/** Extra actions on a property the player (or their empire) owns. */
export function LotExtras({ p, act, forEmpire, m }: { p: MyLot; act: Act; forEmpire: boolean; m: PropertyMarket }) {
  const [zone, setZone] = useState("");
  const [kind, setKind] = useState("");
  const [loan, setLoan] = useState("");
  const [bank, setBank] = useState(m.banks[0]?.id ?? "");
  const [then, setThen] = useState<"let" | "sell">("let");
  const [buyer, setBuyer] = useState("");
  const [buyerKind, setBuyerKind] = useState<"player" | "empire">("player");
  const [price, setPrice] = useState("");
  const plot = p.kind === "land" || p.status !== "standing";
  const whole = p.share_bps === 10000;
  const allowed = p.may_build ?? [];
  return (
    <div className="lot-extras">
      <div className="row small">
        <span><Term word="Zoning">Zone</Term>: {p.zone_name ?? "—"}{p.beside_works ? " · beside public works" : ""}{p.right_of_way ? " · a right of way crosses it" : ""}</span>
        <span className="muted">{allowed.length ? `may build: ${allowed.map((k) => KIND_NAMES[k]?.toLowerCase() ?? k).join(", ")}` : ""}</span>
      </div>
      {(p.claims ?? []).length > 0 && <ul className="plain-list small">{(p.claims ?? []).map((c) => <li key={c.id}>▲ {c.words}</li>)}</ul>}
      {p.frozen && (
        <p className="error small">■ Frozen by a family dispute: nothing may be done with it and its rent is held back.{" "}
          <button className="button-outline" disabled={act.busy} onClick={() => act.run(`/property/${p.id}/settle-dispute`, { for_empire: forEmpire }, "Settled: the property is free again.")}>Settle the dispute</button></p>
      )}
      <div className="inline-form">
        <ValuationBox id={p.id} />
        <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/${p.id}/claims-search`, { for_empire: forEmpire }, (r) => `The Land Registry: ${r.words ?? "no answer"}`)}>Search for claims</button>
        {whole && !p.frozen && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (zone) act.run(`/property/${p.id}/rezone`, { for_empire: forEmpire, to_zone: zone }, "Asked: the planning office decides at the quarter's close."); }}>
            <label className="answer">Ask to rezone<select value={zone} onChange={(e) => setZone(e.target.value)}><option value="">Choose a zone…</option>
              {(m.zones ?? []).filter((z) => z.zone !== p.zone).map((z) => <option key={z.zone} value={z.zone}>{z.name}</option>)}</select></label>
            <button className="button-quiet" disabled={act.busy || !zone}>Ask (₦500,000)</button>
          </form>
        )}
      </div>
      {whole && plot && !p.frozen && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run(`/property/${p.id}/develop`, { for_empire: forEmpire, kind: kind || null, loan_kobo: asKobo(loan) ?? 0, loan_bank: asKobo(loan) ? bank : null, then_what: then }, "Permit asked for: building starts once it comes."); }}>
          <label className="answer">Develop it as<select value={kind} onChange={(e) => setKind(e.target.value)}><option value="">the usual for the zone</option>
            {allowed.map((k) => <option key={k} value={k}>{KIND_NAMES[k] ?? k}</option>)}</select></label>
          <label className="answer"><Term word="Construction loan">Construction loan</Term> (₦, up to 70%)<input type="text" inputMode="decimal" value={loan} onChange={(e) => setLoan(e.target.value)} /></label>
          {asKobo(loan) !== null && <label className="answer">From<select value={bank} onChange={(e) => setBank(e.target.value)}>{m.banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
          <label className="answer">When done<select value={then} onChange={(e) => setThen(e.target.value as "let" | "sell")}><option value="let">let it</option><option value="sell">sell it at auction</option></select></label>
          <button className="button-outline" disabled={act.busy}>Start: ask for the permit</button>
        </form>
      )}
      {whole && !p.frozen && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(price); if (k && buyer.trim()) act.run(`/property/${p.id}/offer`, { for_empire: forEmpire, price_kobo: k, [buyerKind === "player" ? "buyer_player" : "buyer_empire"]: buyer.trim() }, "Offered: the buyer goes through the twelve steps."); }}>
          <label className="answer">Sell privately to<select value={buyerKind} onChange={(e) => setBuyerKind(e.target.value as "player" | "empire")}><option value="player">a player</option><option value="empire">an empire</option></select></label>
          <label className="answer">Their name<input type="text" maxLength={60} value={buyer} onChange={(e) => setBuyer(e.target.value)} /></label>
          <label className="answer">Price (₦)<input type="text" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <button className="button-quiet" disabled={act.busy || !asKobo(price) || !buyer.trim()}>Offer it</button>
        </form>
      )}
    </div>
  );
}

function SaleRow({ s, act, forEmpire, m }: { s: PrivateSale; act: Act; forEmpire: boolean; m: PropertyMarket }) {
  const [mortgage, setMortgage] = useState("");
  const [bank, setBank] = useState(m.banks[0]?.id ?? "");
  const open = ["offered", "agreed", "consent"].includes(s.status);
  const body = { for_empire: forEmpire };
  return (
    <article className="lot">
      <div className="lot-head">
        <div><h3 className="lot-title">{s.name}</h3><div className="muted small">{s.role === "buyer" ? "You are buying" : "You are selling"} · {s.status}</div></div>
        <div className="mono figure-small">{formatNaira(s.price)}</div>
      </div>
      <ol className="plain-list small">
        {s.steps.map((st) => <li key={st.step}>{st.done ? "✓" : "○"} {STEP_NAMES[st.step] ?? st.step}{st.words ? <span className="muted"> — {st.words}</span> : null}</li>)}
      </ol>
      {s.role === "buyer" && open && (
        <div className="inline-form">
          {s.status !== "consent" && CHECKS.filter((c) => !s.steps.find((st) => st.step === c)?.done).map((c) => (
            <button key={c} className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/sales/${s.id}/check`, { ...body, step: c }, (r) => r.words ?? "Done.")}>{STEP_NAMES[c]}</button>
          ))}
          {s.status === "offered" && (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(mortgage); act.run(`/property/sales/${s.id}/accept`, { ...body, mortgage_kobo: k ?? 0, mortgage_bank: k ? bank : null }, "Terms agreed."); }}>
              <label className="answer">Mortgage (₦, blank for none)<input type="text" inputMode="decimal" value={mortgage} onChange={(e) => setMortgage(e.target.value)} /></label>
              {asKobo(mortgage) !== null && <label className="answer">From<select value={bank} onChange={(e) => setBank(e.target.value)}>{m.banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
              <button className="button-outline" disabled={act.busy}>Agree the terms</button>
            </form>
          )}
          {s.status === "agreed" && <button className="button-outline" disabled={act.busy} onClick={() => act.run(`/property/sales/${s.id}/consent`, body, "Consent asked: it takes about two days.")}>Ask the Governor's consent (0.5%)</button>}
          {s.status === "consent" && (s.consent_ready
            ? <button className="button-primary" disabled={act.busy} onClick={() => act.run(`/property/sales/${s.id}/sign`, body, "Signed, registered and handed over.")}>Sign, register and take it</button>
            : <span className="muted small">Consent is due {s.consent_due ? new Date(s.consent_due).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "soon"}.</span>)}
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/sales/${s.id}/decline`, body, "Declined.")}>Decline</button>
        </div>
      )}
      {s.role === "seller" && open && <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/sales/${s.id}/decline`, body, "Withdrawn.")}>Withdraw the offer</button>}
      {s.role === "buyer" && open && <p className="muted small">The checks (steps 1 to 5) are yours to choose: skipping one never stops the purchase, but what it would have found can show up later.</p>}
    </article>
  );
}

export function SalesAndDevelopments({ sales, developments, act, forEmpire, m }: { sales: PrivateSale[]; developments: Development[]; act: Act; forEmpire: boolean; m: PropertyMarket }) {
  return (
    <>
      {sales.length > 0 && <Panel title="Private sales" aside="the twelve-step purchase">{sales.map((s) => <SaleRow key={s.id} s={s} act={act} forEmpire={forEmpire} m={m} />)}</Panel>}
      {developments.length > 0 && (
        <Panel title="Developments" aside="four phases, one at each quarter's close">
          {developments.map((d) => (
            <article key={d.id} className="lot">
              <div className="lot-head">
                <div><h3 className="lot-title">{d.name}: {d.kind}</h3><div className="muted small">{d.status} · then {d.then_what === "let" ? "let it" : "sell it"}</div></div>
                <div className="mono figure-small">{d.phase} of {d.phases}</div>
              </div>
              <div className="meter" role="img" aria-label={`${d.phase} of ${d.phases} phases built`}><div className="meter-fill" style={{ width: `${(d.phase * 100) / d.phases}%` }} /></div>
              <div className="row small"><span>Budget · spent</span><span className="mono">{formatCompact(d.budget)} · {formatCompact(d.spent)}</span></div>
              {d.loan_most !== "0" && <div className="row small"><span>Construction loan drawn</span><span className="mono">{formatCompact(d.loan_drawn)} of {formatCompact(d.loan_most)}</span></div>}
              <ul className="plain-list small">{d.log.slice(-4).map((l, i) => <li key={i}><span className="muted">{l.label}</span> {l.words}</li>)}</ul>
            </article>
          ))}
        </Panel>
      )}
    </>
  );
}

function FundsPanel({ onLoggedOut, act }: { onLoggedOut: () => void; act: Act }) {
  const { data, error, loading, reload } = useLoad<PropertyFunds>(api.propertyFunds, "property-funds", onLoggedOut);
  const [amount, setAmount] = useState<Record<number, string>>({});
  const [units, setUnits] = useState<Record<number, string>>({});
  const [name, setName] = useState("");
  const [fee, setFee] = useState("1");
  const [auction, setAuction] = useState("");
  const [limit, setLimit] = useState("");
  const run = (path: string, body: unknown, done: string) => { act.run(path, body, done); setTimeout(reload, 400); };
  if (loading && !data) return <Loading what="property funds" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <Panel title="Property funds" aside="units bought and sold at the fund's value, 1% either side">
      <p className="small">A <Term word="Property fund">property fund</Term> owns buildings and cash; a unit is worth the fund's value over its units. Selling units is paid from the fund's cash.</p>
      {data.funds.map((f) => (
        <article key={f.id} className="lot">
          <div className="lot-head">
            <div><h3 className="lot-title">{f.name}</h3><div className="muted small">{f.manager} · {f.buildings} building{f.buildings === 1 ? "" : "s"} · fee {formatPercent(f.fee_bps, 2)} a year</div></div>
            <div className="mono figure-small">{formatCompact(f.value)}</div>
          </div>
          <div className="row small"><span>A unit · cash in the fund</span><span className="mono">₦{(f.unit_price_kobo / 100).toFixed(4)} · {formatCompact(f.cash)}</span></div>
          {f.my_units > 0 && <div className="row small"><span>Your units</span><span className="mono">{f.my_units.toLocaleString("en-NG")} · {formatCompact(f.my_value)}</span></div>}
          <div className="inline-form">
            <input className="small-input" type="text" inputMode="decimal" aria-label={`Naira to put into ${f.name}`} placeholder="₦ to put in" value={amount[f.id] ?? ""} onChange={(e) => setAmount({ ...amount, [f.id]: e.target.value })} />
            <button className="button-quiet" disabled={act.busy || !asKobo(amount[f.id] ?? "")} onClick={() => run(`/property-funds/${f.id}/buy`, { amount_kobo: asKobo(amount[f.id] ?? "") }, "Units bought.")}>Buy units</button>
            {f.my_units > 0 && <>
              <input className="small-input" type="number" min={1} aria-label={`Units of ${f.name} to sell`} placeholder="units" value={units[f.id] ?? ""} onChange={(e) => setUnits({ ...units, [f.id]: e.target.value })} />
              <button className="button-quiet" disabled={act.busy || !(Number(units[f.id]) > 0)} onClick={() => run(`/property-funds/${f.id}/sell`, { units: Math.floor(Number(units[f.id])) }, "Units sold back.")}>Sell units</button>
            </>}
          </div>
        </article>
      ))}
      {data.managed ? (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(limit); if (k && Number(auction) > 0) run("/property-funds/managed/bid", { auction_id: Number(auction), limit_kobo: k }, "Bid placed for your fund."); }}>
          <span className="small">Your fund bids at the Auction House (never above a tenth over a building's worth, no building over 30% of the fund, 10% kept in cash):</span>
          <label className="answer">Auction number<input className="small-input" type="number" min={1} value={auction} onChange={(e) => setAuction(e.target.value)} /></label>
          <label className="answer">Highest price (₦)<input type="text" inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
          <button className="button-outline" disabled={act.busy}>Bid for the fund</button>
        </form>
      ) : (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run("/property-funds", { name, fee_bps: Math.round(Number(fee) * 100) }, "Your property fund is open."); }}>
          <span className="small muted">An Asset Manager of Level {data.open_level} or above may open one fund (₦5m to register):</span>
          <label className="answer">Name<input type="text" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="answer">Fee (% a year, up to {data.fee_most_bps / 100})<input className="small-input" type="text" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} /></label>
          <button className="button-quiet" disabled={act.busy || name.trim().length < 3}>Open a property fund</button>
        </form>
      )}
    </Panel>
  );
}

/** The "Projects and funds" tab: public works, households' home loans, and property funds. */
export function ProjectsTab({ m, act, onLoggedOut }: { m: PropertyMarket; act: Act; onLoggedOut: () => void }) {
  const loans = m.home_loans ?? [];
  const last = loans.length ? Math.max(...loans.map((r) => r.period)) : 0;
  const latest = loans.filter((r) => r.period === last);
  return (
    <>
      <Panel title="Public works" aside="about one big project a game year">
        {(m.infrastructure ?? []).length === 0 ? <p className="muted">No projects yet.</p> : (
          <div className="scroll" tabIndex={0}>
            <table className="dense">
              <caption className="sr-only">Infrastructure projects</caption>
              <thead><tr><th scope="col">Project</th><th scope="col">Beside</th><th scope="col">Announced · due</th><th scope="col">Status</th><th scope="col" className="num">Adds to prices now · when done</th></tr></thead>
              <tbody>{(m.infrastructure ?? []).map((p) => (
                <tr key={p.id}><th scope="row">{p.name}</th><td>{p.district}, {p.city}</td><td>{p.announced} · {p.finish}</td><td>{p.status === "done" ? "✓ Open" : "▲ Being built"}</td>
                  <td className="num mono">{formatPercent(p.gain_now_bps, 1)} · {formatPercent(p.uplift_bps, 1)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <p className="muted small">Land beside the works gains twice as much. The Government pays the cement, steel and building companies for the works each quarter.</p>
      </Panel>
      <Panel title="Households' home loans" aside={latest[0] ? `${latest[0].label} · mortgages cost ${formatPercent(latest[0].rate_bps, 1)}` : undefined}>
        {latest.length === 0 ? <p className="muted">No figures yet.</p> : (
          <div className="scroll" tabIndex={0}>
            <table className="dense">
              <caption className="sr-only">Home loans by city</caption>
              <thead><tr><th scope="col">City</th><th scope="col" className="num">Lent this quarter</th><th scope="col" className="num">Defaulted</th><th scope="col" className="num">Homes repossessed</th><th scope="col" className="num">Owed in all</th></tr></thead>
              <tbody>{latest.map((r) => (
                <tr key={r.location}><th scope="row">{r.location}</th><td className="num mono">{formatCompact(r.lent)}</td><td className="num mono">{formatCompact(r.defaulted)}</td>
                  <td className="num mono">{r.repossessed.toLocaleString("en-NG")}</td><td className="num mono">{formatCompact(r.book)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <p className="muted small">When the rate rises, fewer households borrow and more cannot pay: banks repossess and sell the homes cheaply, and prices in the homes districts fall.</p>
      </Panel>
      <FundsPanel onLoggedOut={onLoggedOut} act={act} />
    </>
  );
}
