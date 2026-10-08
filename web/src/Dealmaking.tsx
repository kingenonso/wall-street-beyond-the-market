// Firms players found, and the deal-making between empires (private equity stage, part 2B).
// Firms: the public list of audit firms, small banks, risk consultancies and advisory firms; founding one;
// the jobs waiting for your firm (checks sent out by other empires, audits, pitch books, restructurings,
// listings to stand behind); a small bank's lending.
// Takeovers: offers on the table (topping one, offering the empire's shares, writing the board's defence),
// drafting an offer, building a stake, blocks of shares between empires, the private-equity portfolio,
// mergers and spin-offs. The server checks and marks everything; the website only asks.

import { useState } from "react";
import { asKobo } from "./Empire";
import { type Act, type Any, Arrow, DutyForm, Money, pct } from "./Firm";
import { formatNaira } from "./format";
import { Panel } from "./Shell";

const JOBS: Record<string, string> = {
  deal_check: "A check on a deal", audit: "An audit", mandate: "Running a sale: the pitch book", restructuring: "Restructuring a loan",
  underwriting: "Standing behind a listing",
};

function Tag({ status }: { status: string }) {
  return <span className={`tag tag-${status}`}>{status.replace(/_/g, " ")}</span>;
}

// ---------------------------------------------------------------------------
// Firms
// ---------------------------------------------------------------------------

export function FirmsTab({ f, act }: { f: Any; act: Act }) {
  const p = f.practice;
  if (!p) return <Panel title="Firms"><p className="muted">Firms are run from a seat in an empire run by players.</p></Panel>;
  return (
    <>
      {p.loan_offers?.length > 0 && (
        <Panel title="Loans offered to the empire" aside="From small banks players run">
          {p.loan_offers.map((o: Any) => (
            <div key={o.id} className="row">
              <span>{o.bank}: <Money kobo={o.amount} /> at {pct(o.rate_bps)} a year for {o.quarters} quarters</span>
              <span className="inline-form">
                <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/firms/loans/${o.id}`, { accept: true })}>Borrow it</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/firms/loans/${o.id}`, { accept: false })}>Turn it down</button>
              </span>
            </div>
          ))}
        </Panel>
      )}
      {p.mine ? <MyFirm m={p.mine} p={p} act={act} /> : <Found p={p} act={act} />}
      <Panel title="The firms" aside="Public · ranked by reputation, which rises with good work and falls with bad">
        {p.directory.length === 0 && <p className="muted">No player has founded a firm yet.</p>}
        {p.directory.map((x: Any) => (
          <div key={x.id} className="row small">
            <span>{x.name} · {x.kind_name} · founded by {x.founder}</span>
            <span className="mono">{x.reputation >= 50 ? "▲" : "▼"} {x.reputation}/100 · {x.jobs_done} job{x.jobs_done === 1 ? "" : "s"}</span>
          </div>
        ))}
      </Panel>
    </>
  );
}

function Found({ p, act }: { p: Any; act: Act }) {
  const kind = Object.entries(p.kinds).find(([, v]: Any) => v.build === p.can_found)?.[0];
  const [name, setName] = useState("");
  const [capital, setCapital] = useState("");
  if (!kind) return null;
  const k = p.kinds[kind];
  return (
    <Panel title={`Found ${k.name.toLowerCase().startsWith("a") ? "an" : "a"} ${k.name.toLowerCase()}`} aside="Run from your seat: of every fee, 60% to your empire, 40% to you">
      <p className="small">{k.does}</p>
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/firms", { kind, name, capital_kobo: kind === "bank" ? asKobo(capital) ?? 0 : 0 }); }}>
        <input type="text" placeholder="The firm's name" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        {kind === "bank" && <input className="small-input" type="text" placeholder={`Capital, at least ${formatNaira(p.bank_capital_least)}`} value={capital} onChange={(e) => setCapital(e.target.value)} />}
        <button className="button-primary" disabled={act.busy || name.trim().length < 3}>Found it</button>
      </form>
    </Panel>
  );
}

function MyFirm({ m, p, act }: { m: Any; p: Any; act: Act }) {
  return (
    <Panel title={m.name} aside={`${p.kinds[m.kind].name} · reputation ${m.reputation}/100 · ${m.jobs_done} jobs done`}>
      {m.kind === "bank" && <Bank m={m} act={act} />}
      <p className="field-label">Work for clients</p>
      {m.jobs.length === 0 && <p className="muted small">No work yet. Empires send checks to firms with a good name; founders hire audit and advisory firms for their sales.</p>}
      {m.jobs.map((j: Any) => (
        <div key={j.id} className="check">
          <div className="row small">
            <span>{j.status === "done" ? "✓" : "○"} {JOBS[j.kind]}{j.company ? `: ${j.company}` : ""}</span>
            <span className="muted">{j.kind === "mandate" || j.kind === "underwriting" ? `fee ${pct(Number(j.fee))} of the price` : <Money kobo={j.fee} />} · <Tag status={j.status} /></span>
          </div>
          {j.words && <p className="small muted">{j.words}</p>}
          {j.status === "open" && j.kind === "underwriting" && (
            <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/firms/jobs/${j.id}/accept`)}>Stand behind the listing</button>
          )}
          {j.status === "open" && j.kind !== "underwriting" && !j.terms && (
            <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/firms/jobs/${j.id}/open`)}>Open the job</button>
          )}
          {j.status === "open" && j.terms && <DutyForm duty={j} act={act} path={`/firms/jobs/${j.id}/hand-in`} />}
        </div>
      ))}
    </Panel>
  );
}

function Bank({ m, act }: { m: Any; act: Act }) {
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [quarters, setQuarters] = useState("4");
  const [out, setOut] = useState("");
  return (
    <div className="exits">
      <div className="row small"><span>Cash</span><Money kobo={m.cash} /></div>
      <div className="row small"><span>Capital put in</span><Money kobo={m.capital} /></div>
      {m.lent.map((l: Any, i: number) => <div key={i} className="row small"><span>Lent to {l.to} at {pct(l.rate_bps)} · {l.status}</span><Money kobo={l.outstanding} /></div>)}
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/firms/loans", { empire_id: Number(to), amount_kobo: asKobo(amount), rate_bps: Math.round(Number(rate) * 100), quarters: Number(quarters) }); }}>
        <select value={to} onChange={(e) => setTo(e.target.value)}><option value="">Lend to…</option>{m.borrowers.map((b: Any) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
        <input className="small-input" type="text" placeholder="Amount ₦" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <input className="small-input" type="text" placeholder="Rate % a year" value={rate} onChange={(e) => setRate(e.target.value)} />
        <input className="small-input" type="number" min={1} max={20} value={quarters} onChange={(e) => setQuarters(e.target.value)} aria-label="Quarters" />
        <button className="button-outline" disabled={act.busy || !to || !asKobo(amount) || !Number(rate)}>Offer the loan</button>
      </form>
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/firms/pay-out", { amount_kobo: asKobo(out) }); }}>
        <input className="small-input" type="text" placeholder="Profit to pay out ₦" value={out} onChange={(e) => setOut(e.target.value)} />
        <button className="button-quiet" disabled={act.busy || !asKobo(out)}>Pay out profit</button>
      </form>
      <p className="muted small">A bank never lends below the Central Bank's rate, nor to the empire its founder sits in. Only profit above its capital and loans can be paid out.</p>
    </div>
  );
}

// The "send to an outside firm" control used beside a check in a deal file.
export function SendOut({ step, firms, act }: { step: Any; firms: Any[]; act: Act }) {
  const [firmId, setFirmId] = useState("");
  const [fee, setFee] = useState("");
  if (!step.can_send || firms.length === 0) return null;
  return (
    <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", `/deals/steps/${step.id}/send`, { firm_id: Number(firmId), fee_kobo: asKobo(fee) }); }}>
      <select value={firmId} onChange={(e) => setFirmId(e.target.value)} aria-label="Outside firm">
        <option value="">Send to an outside firm…</option>
        {firms.map((x: Any) => <option key={x.id} value={x.id}>{x.name} · {x.reputation}/100</option>)}
      </select>
      <input className="small-input" type="text" placeholder="Fee ₦" value={fee} onChange={(e) => setFee(e.target.value)} />
      <button className="button-quiet" disabled={act.busy || !firmId || !asKobo(fee)}>Send it out</button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Takeovers, stakes, blocks, the portfolio, mergers
// ---------------------------------------------------------------------------

export function TakeoversTab({ f, act }: { f: Any; act: Act }) {
  const d = f.dealmaking;
  if (!d) return <Panel title="Takeovers"><p className="muted">Only an empire run by players makes offers.</p></Panel>;
  return (
    <>
      <Panel title="Takeover offers" aside="An offer is for control: more than half the shares. Another empire may top it by 5%">
        {d.offers.length === 0 && <p className="muted">No offer is on the table.</p>}
        {d.offers.map((o: Any) => <Offer key={o.id} o={o} act={act} />)}
        {d.may.offer && <DraftOffer d={d} act={act} />}
      </Panel>
      <Panel title="Building a stake" aside={`Bought a little at each bell, below ${pct(d.rules.must_offer_bps)}. Every ${pct(d.rules.disclose_step_bps)} held is made public`}>
        {d.programmes.map((x: Any) => (
          <div key={x.id} className="row small">
            <span>{x.company} ({x.ticker}) · target {pct(x.target_bps)} · up to <Money kobo={x.most_price} /> a share · disclosed {pct(x.disclosed_bps)}</span>
            <span>{x.status === "running" && d.may.stake ? <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/stakes/${x.id}`)}>Stop</button> : <Tag status={x.status} />}</span>
          </div>
        ))}
        {d.may.stake && <StartStake d={d} act={act} />}
        <Holdings d={d} />
      </Panel>
      {(d.may.head || d.blocks.length > 0) && <Blocks d={d} act={act} />}
      <Portfolio d={d} />
      <Combinations f={f} d={d} act={act} />
      {d.owned.length > 0 && <Shadow d={d} act={act} />}
    </>
  );
}

function Offer({ o, act }: { o: Any; act: Act }) {
  const [shares, setShares] = useState("");
  return (
    <div className="bond">
      <div className="strong">
        {o.bidder} offers for {o.target} ({o.ticker}) {" "}
        <span className={o.hostile ? "pill pill-test" : "pill pill-open"}>{o.hostile ? "Hostile: the board rejects it" : "The board recommends it"}</span>
        {o.ours && <span className="pill pill-open">Your empire's offer</span>}
      </div>
      <div className="small">
        <Money kobo={o.price} /> a share, <Arrow up={o.premium_bps >= 0} /> {pct(o.premium_bps)} above the market when made, for {Number(o.shares_sought).toLocaleString()} shares · closes as {o.closes} closes
        {o.defence_value && <> · the board says a share is worth <Money kobo={o.defence_value} /></>}
      </div>
      {o.status !== "open" && <p className="small muted">{o.outcome}</p>}
      {Number(o.our_bps) > 0 && !o.ours && <p className="small">Your empire holds {pct(o.our_bps)} ({Number(o.tendered).toLocaleString()} shares offered to the bidder).</p>}
      {o.can_tender && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("PUT", `/takeovers/${o.id}/tender`, { shares: Number(shares.replace(/,/g, "")) }); }}>
          <input className="small-input" type="text" placeholder="Shares to offer (0 takes them back)" value={shares} onChange={(e) => setShares(e.target.value)} />
          <button className="button-outline" disabled={act.busy || shares === ""}>Offer the empire's shares</button>
        </form>
      )}
      {o.can_defend && !o.defence?.terms && (
        <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/takeovers/${o.id}/defence/open`)}>Write the board's defence</button>
      )}
      {o.defence?.terms && <DutyForm duty={o.defence} act={act} path={`/takeovers/${o.id}/defence/hand-in`} />}
    </div>
  );
}

function DraftOffer({ d, act }: { d: Any; act: Act }) {
  const [company, setCompany] = useState("");
  const [price, setPrice] = useState("");
  const [shares, setShares] = useState("");
  const chosen = d.listed.find((c: Any) => c.company_id === company);
  return (
    <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/takeovers", { company_id: company, price_kobo: asKobo(price), shares: Number(shares.replace(/,/g, "")) }); }}>
      <select value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Company">
        <option value="">Make an offer for…</option>
        {d.listed.map((c: Any) => <option key={c.company_id} value={c.company_id}>{c.name} ({c.ticker})</option>)}
      </select>
      <input className="small-input" type="text" placeholder={chosen ? `₦ a share (market ${formatNaira(chosen.price)})` : "₦ a share"} value={price} onChange={(e) => setPrice(e.target.value)} />
      <input className="small-input" type="text" placeholder="Shares wanted" value={shares} onChange={(e) => setShares(e.target.value)} />
      <button className="button-primary" disabled={act.busy || !company || !asKobo(price) || !Number(shares.replace(/,/g, ""))}>Draft the offer for the head</button>
    </form>
  );
}

function StartStake({ d, act }: { d: Any; act: Act }) {
  const [company, setCompany] = useState("");
  const [target, setTarget] = useState("");
  const [most, setMost] = useState("");
  return (
    <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/stakes", { company_id: company, target_bps: Math.round(Number(target) * 100), most_price_kobo: asKobo(most) }); }}>
      <select value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Company">
        <option value="">Build a stake in…</option>
        {d.listed.map((c: Any) => <option key={c.company_id} value={c.company_id}>{c.name} ({c.ticker})</option>)}
      </select>
      <input className="small-input" type="text" placeholder="Target % (under 30)" value={target} onChange={(e) => setTarget(e.target.value)} />
      <input className="small-input" type="text" placeholder="Most ₦ a share" value={most} onChange={(e) => setMost(e.target.value)} />
      <button className="button-outline" disabled={act.busy || !company || !Number(target) || !asKobo(most)}>Ask the head</button>
    </form>
  );
}

function Holdings({ d }: { d: Any }) {
  if (d.holdings.length === 0) return null;
  return (
    <>
      <p className="field-label">Listed shares the empire holds</p>
      {d.holdings.map((h: Any) => <div key={h.company_id} className="row small"><span>{h.name} ({h.ticker}) · {Number(h.shares).toLocaleString()} shares</span><span className="mono">{pct(h.share_bps)}</span></div>)}
    </>
  );
}

function Blocks({ d, act }: { d: Any; act: Act }) {
  const [buyer, setBuyer] = useState("");
  const [company, setCompany] = useState("");
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  return (
    <Panel title="Blocks of shares between empires" aside={`Off the order book, within ${pct(d.rules.block_band_bps)} of the market price`}>
      {d.blocks.map((b: Any) => (
        <div key={b.id} className="row small">
          <span>{b.selling ? `To ${b.buyer}` : `From ${b.seller}`}: {Number(b.shares).toLocaleString()} {b.company} shares at <Money kobo={b.price} /></span>
          <span className="inline-form">
            {b.status === "offered" && !b.selling && d.may.head && <>
              <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/blocks/${b.id}`, { accept: true })}>Buy it</button>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/blocks/${b.id}`, { accept: false })}>Turn it down</button>
            </>}
            {b.status === "offered" && b.selling && d.may.head && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/blocks/${b.id}`)}>Withdraw</button>}
            {b.status !== "offered" && <Tag status={b.status} />}
          </span>
        </div>
      ))}
      {d.may.head && d.holdings.length > 0 && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/blocks", { buyer_empire_id: Number(buyer), company_id: company, shares: Number(shares.replace(/,/g, "")), price_kobo: asKobo(price) }); }}>
          <select value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Shares"><option value="">Sell a block of…</option>{d.holdings.map((h: Any) => <option key={h.company_id} value={h.company_id}>{h.name}</option>)}</select>
          <select value={buyer} onChange={(e) => setBuyer(e.target.value)} aria-label="Buyer"><option value="">to…</option>{d.others.map((o: Any) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
          <input className="small-input" type="text" placeholder="Shares" value={shares} onChange={(e) => setShares(e.target.value)} />
          <input className="small-input" type="text" placeholder="₦ a share" value={price} onChange={(e) => setPrice(e.target.value)} />
          <button className="button-outline" disabled={act.busy || !buyer || !company || !asKobo(price)}>Offer the block</button>
        </form>
      )}
    </Panel>
  );
}

function Portfolio({ d }: { d: Any }) {
  if (d.portfolio.length === 0) return null;
  return (
    <Panel title="Private-equity holdings" aside="At cost, and at the latest valuation · members only">
      <table className="mini-table">
        <thead><tr><th>Company</th><th>Share</th><th>Paid</th><th>Worth now</th><th>Multiple</th><th>Held</th></tr></thead>
        <tbody>
          {d.portfolio.map((x: Any) => (
            <tr key={x.company_id}>
              <td>{x.name}{x.controls ? " ●" : ""}</td><td>{pct(x.share_bps)}</td><td><Money kobo={x.cost} compact /></td><td><Money kobo={x.value} compact /></td>
              <td><Arrow up={(x.multiple_x100 ?? 100) >= 100} /> {x.multiple_x100 === null ? "—" : `${(x.multiple_x100 / 100).toFixed(2)}×`}</td><td>{x.quarters} q</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">● the empire controls it. The multiple is what its share is worth now for each naira paid.</p>
    </Panel>
  );
}

function Combinations({ f, d, act }: { f: Any; d: Any; act: Act }) {
  const [other, setOther] = useState("");
  const [company, setCompany] = useState("");
  const [name, setName] = useState("");
  const [head, setHead] = useState("");
  const [cash, setCash] = useState("");
  const waiting = d.combinations.find((c: Any) => c.joining_us && c.status === "voting");
  return (
    <Panel title="Mergers, splits and truces" aside="The members vote; a big item needs two-thirds when the empire's rules say so">
      {d.combinations.map((c: Any) => <div key={c.id} className="row small"><span>{c.kind === "merger" ? (c.joining_us ? `Joining ${c.with}` : `${c.with} joining us`) : `Split off into ${c.with}`}</span><Tag status={c.status} /></div>)}
      {d.others.some((o: Any) => o.truce) && <p className="small">Truce with {d.others.filter((o: Any) => o.truce).map((o: Any) => o.name).join(", ")}: no poaching, no offers or stake-building against each other's companies.</p>}
      {d.may.head && (
        <>
          {waiting && <button className="button-primary" disabled={act.busy} onClick={() => act.run("POST", "/combinations/join", { combination_id: waiting.id })}>Put joining {waiting.with} to our members' vote</button>}
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/combinations/merger", { other_empire_id: Number(other) }); }}>
            <select value={other} onChange={(e) => setOther(e.target.value)} aria-label="Empire"><option value="">Merge into us…</option>{d.others.map((o: Any) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
            <button className="button-outline" disabled={act.busy || !other}>Put the merger to the vote</button>
          </form>
          {d.owned.length > 0 && (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", "/combinations/spinoff", { company_id: company, new_name: name, new_head: head, cash_kobo: asKobo(cash) ?? 0 }); }}>
              <select value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Company"><option value="">Split off…</option>{d.owned.map((o: Any) => <option key={o.company_id} value={o.company_id}>{o.name}</option>)}</select>
              <input className="small-input" type="text" placeholder="New empire's name" value={name} onChange={(e) => setName(e.target.value)} />
              <select value={head} onChange={(e) => setHead(e.target.value)} aria-label="Its head"><option value="">led by…</option>{d.members.map((m: Any) => <option key={m.player_id} value={m.player_id}>{m.name}</option>)}</select>
              <input className="small-input" type="text" placeholder="Cash it takes ₦ (up to a tenth)" value={cash} onChange={(e) => setCash(e.target.value)} />
              <button className="button-outline" disabled={act.busy || !company || name.trim().length < 3 || !head}>Put the split to the vote</button>
            </form>
          )}
          <p className="muted small">Truces are pacts drafted by Legal Counsel (War Room). {f.name}'s members keep their part: a merger gives the joining empire's owners units worth what theirs were.</p>
        </>
      )}
    </Panel>
  );
}

function Shadow({ d, act }: { d: Any; act: Act }) {
  const [company, setCompany] = useState("");
  const [amount, setAmount] = useState("");
  return (
    <details className="panel shadow">
      <summary>Fees from a company the empire controls</summary>
      <p className="small">Pay yourself "consulting fees" out of the company's cash. It counts against your signing limit and goes in the books as a cost. An audit, the empire's own or an audit firm's, may find it; then it is repaid with a fine, and you lose your seat.</p>
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("POST", `/owned/${company}/consulting`, { amount_kobo: asKobo(amount) }); }}>
        <select value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Company"><option value="">From…</option>{d.owned.map((o: Any) => <option key={o.company_id} value={o.company_id}>{o.name}</option>)}</select>
        <input className="small-input" type="text" placeholder="₦" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <button className="button-quiet" disabled={act.busy || !company || !asKobo(amount)}>Take it</button>
      </form>
    </details>
  );
}
