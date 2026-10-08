// Deals and the companies an empire owns (private equity stage, part 2A).
// Deals: companies on sale, the empire's file on each (the confidentiality agreement, the data room,
// the six checks, the sale agreement clause by clause, partners, the bid), and the purchases made.
// Companies: what the empire controls, run by its dials; assets, the managing director, routes,
// the 100-day plan, the bank's promises, and the ways out.
// The server marks every check and decides every sale; the website only asks.

import { useState, type FormEvent } from "react";
import { asKobo } from "./Empire";
import { type Act, type Any, Arrow, DutyForm, Money, pct } from "./Firm";
import { formatCompact, formatNaira } from "./format";
import { NumberTile } from "./Parts";
import { Panel } from "./Shell";

const CITIES = ["Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"];
const STARS = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);
const WAYS: Record<string, string> = { sealed: "Sealed bids", auction: "Auction" };

function Tag({ status }: { status: string }) {
  return <span className={`tag tag-${status}`}>{status.replace(/_/g, " ")}</span>;
}

// ---------------------------------------------------------------------------
// Deals
// ---------------------------------------------------------------------------

export function DealsTab({ f, act }: { f: Any; act: Act }) {
  const d = f.deals;
  if (!d) return <Panel title="Deals"><p className="muted">Only an empire run by players buys companies.</p></Panel>;
  return (
    <>
      {d.invitations.length > 0 && (
        <Panel title="Invitations to co-invest" aside="Another empire asks yours to put money into its bid">
          {d.invitations.map((i: Any) => (
            <div key={i.id} className="row">
              <span>{i.from}: {formatNaira(i.amount)} towards {i.company} <Tag status={i.status} /></span>
              {i.status === "invited" && (
                <span className="inline-form">
                  <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/deals/partners/${i.id}`, { accept: true })}>Pledge it</button>
                  <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/deals/partners/${i.id}`, { accept: false })}>Decline</button>
                </span>
              )}
            </div>
          ))}
          <p className="muted small">A pledge is held in escrow until the sale is decided: handed back if the bid loses, turned into shares if it wins.</p>
        </Panel>
      )}
      <Panel title="Companies for sale" aside="Decided as the quarter closes. A deal needs all three: the Banker brings it, the Accountant checks it, the Risk Manager signs its risks">
        {d.sales.length === 0 && <p className="muted">Nothing is on sale at the moment. The founders put companies up for sale as quarters close.</p>}
        {d.sales.map((s: Any) => <Sale key={s.id} s={s} d={d} act={act} />)}
      </Panel>
      {d.deals.length > 0 && (
        <Panel title="Companies bought" aside="A seller's false promise can be claimed against, while the time for claims lasts">
          {d.deals.map((x: Any) => <Bought key={x.id} x={x} act={act} />)}
        </Panel>
      )}
    </>
  );
}

function Sale({ s, d, act }: { s: Any; d: Any; act: Act }) {
  const [open, setOpen] = useState(false);
  const file = s.file;
  return (
    <div className="report">
      <div className="row">
        <span><strong>{s.company}</strong> · {s.sector} · {s.city}</span>
        <span className="mono">{formatCompact(s.asking)} asked</span>
      </div>
      <div className="row small muted">
        <span>{WAYS[s.mode]}{s.highest ? ` · highest bid ${formatCompact(s.highest)}` : ""} · closes as {s.closes} closes</span>
        {s.yours_to_sell ? <span className="tag">your sale</span> : file ? <Tag status={file.status} /> : null}
      </div>
      {s.can_bring && <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/deals/${s.id}/file`)}>Bring this deal to the empire</button>}
      {s.yours_to_sell && (s.asked_of_you ?? []).length > 0 && <SellerAnswers s={s} act={act} />}
      {file && <button className="button-quiet" onClick={() => setOpen(!open)}>{open ? "Close the file ▲" : "Open the file ▼"}</button>}
      {file && open && <File file={file} s={s} d={d} act={act} />}
    </div>
  );
}

function SellerAnswers({ s, act }: { s: Any; act: Act }) {
  const by: Record<string, Any[]> = {};
  for (const a of s.asked_of_you) (by[a.empire_id] ??= []).push(a);
  return (
    <div className="facts">
      <p className="field-label">Buyers ask for changes to the agreement</p>
      {Object.entries(by).map(([empire, rows]) => rows.map((a: Any) => (
        <div key={`${empire}-${a.code}`} className="row small">
          <span>{a.code.replace(/_/g, " ")}</span>
          <span className="inline-form">
            <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/deals/${s.id}/terms/${empire}`, { answers: { [a.code]: true } })}>Agree</button>
            <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/deals/${s.id}/terms/${empire}`, { answers: { [a.code]: false } })}>Refuse</button>
          </span>
        </div>
      )))}
    </div>
  );
}

function File({ file, s, d, act }: { file: Any; s: Any; d: Any; act: Act }) {
  return (
    <div className="deal-file">
      {!file.nda && (
        <div className="callout">
          <p>The data room opens once Legal Counsel signs a confidentiality agreement for the empire.</p>
          {file.can_sign_nda && <button className="button-primary" disabled={act.busy} onClick={() => act.run("POST", `/deals/files/${file.id}/nda`)}>Sign the confidentiality agreement</button>}
        </div>
      )}
      {file.data_room && <DataRoom room={file.data_room} />}
      <Checks file={file} act={act} />
      {file.terms && <Terms file={file} act={act} />}
      {file.nda && file.is_head && <Bid file={file} s={s} d={d} act={act} />}
    </div>
  );
}

function DataRoom({ room }: { room: Any }) {
  return (
    <div className="data-room">
      <p className="field-label">The data room · the seller's papers</p>
      <table className="mini-table">
        <thead><tr><th>Quarter</th><th>Sales</th><th>Operating profit</th><th>Profit</th><th>Cash</th><th>Borrowings</th></tr></thead>
        <tbody>
          {room.papers.map((p: Any) => (
            <tr key={p.period}><td>{p.label}</td><td><Money kobo={p.revenue} compact /></td><td><Money kobo={p.operating_profit} compact /></td>
              <td><Money kobo={p.net_profit} compact /></td><td><Money kobo={p.cash} compact /></td><td><Money kobo={p.borrowings} compact /></td></tr>
          ))}
        </tbody>
      </table>
      <div className="row small"><span>Share of its industry's sales</span><span className="mono">{room.market_share_bps === null ? "no listed rival publishes its sales" : pct(room.market_share_bps)}</span></div>
      {room.manager && <div className="row small"><span>Managing director</span><span>{room.manager.name} · {STARS(room.manager.quality)}</span></div>}
      {room.debts.map((x: Any, i: number) => <div key={i} className="row small"><span>{x.name} · {pct(x.rate_bps)} · due {x.due}</span><Money kobo={x.outstanding} compact /></div>)}
      <p className="field-label">Assets, as the seller states them</p>
      {room.assets.map((a: Any) => (
        <div key={a.id} className="row small"><span>{a.name}{a.base ? ` · ${a.base}` : ""} · {a.age_quarters} of {a.life_quarters} quarters</span><Condition bps={a.condition_bps} /></div>
      ))}
      {room.routes.length > 0 && <p className="small">Routes: {room.routes.map((r: Any) => `${r.from}–${r.to}`).join(", ")}</p>}
      {room.found.length > 0 && (
        <div className="callout">
          <p className="field-label">What the empire has found</p>
          {room.found.map((x: Any) => <p key={x.code} className="small">◆ {x.what} <span className="muted">({x.how})</span></p>)}
        </div>
      )}
    </div>
  );
}

function Condition({ bps }: { bps: number }) {
  const word = bps >= 7000 ? "good" : bps >= 4000 ? "fair" : bps >= 2000 ? "poor" : "unfit";
  return <span className={`mono condition-${word}`}>{bps >= 7000 ? "●" : bps >= 4000 ? "◐" : "○"} {pct(bps)} · {word}</span>;
}

function Checks({ file, act }: { file: Any; act: Act }) {
  return (
    <div className="checks">
      <p className="field-label">The checks</p>
      {file.steps.map((step: Any) => (
        <div key={step.id} className="check">
          <div className="row small">
            <span>{step.status === "done" ? "✓" : "○"} {step.title} · {step.desk}</span>
            <span className="muted">{step.status === "done" ? `${step.by ?? ""}${step.score !== null ? ` · ${step.score}/100` : ""}` : "to do"}</span>
          </div>
          {step.status === "done" && step.found.map((w: string, i: number) => <p key={i} className="small muted">{w}</p>)}
          {step.yours && !step.terms && file.nda && (
            <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/deals/steps/${step.id}/open`)}>Open this check</button>
          )}
          {step.yours && step.terms && <DutyForm duty={step} act={act} path={`/deals/steps/${step.id}/hand-in`} />}
        </div>
      ))}
    </div>
  );
}

function Terms({ file, act }: { file: Any; act: Act }) {
  const [marks, setMarks] = useState<Record<string, string>>({});
  const asked = new Set(file.terms.map((t: Any) => t.code));
  return (
    <div className="terms">
      <p className="field-label">The sale agreement · each change has a price the seller adds ({pct(file.charge_bps)} so far)</p>
      {file.terms.map((t: Any) => (
        <div key={t.code} className="row small">
          <span>{t.escape ? "⚠ " : t.protection ? "＋ " : ""}{t.words}</span>
          <span className="inline-form">
            <Tag status={t.status} />
            {file.can_negotiate && t.status === "in" && !t.protection && (
              <label className="pick"><input type="checkbox" checked={marks[t.code] === "strike"} onChange={(e) => setMarks({ ...marks, [t.code]: e.target.checked ? "strike" : "keep" })} /> strike</label>
            )}
          </span>
        </div>
      ))}
      {file.can_negotiate && file.protections.filter((p: Any) => !asked.has(p.code)).map((p: Any) => (
        <div key={p.code} className="row small">
          <span>＋ {p.words}</span>
          <label className="pick"><input type="checkbox" checked={marks[p.code] === "ask"} onChange={(e) => setMarks({ ...marks, [p.code]: e.target.checked ? "ask" : "drop" })} /> ask for it</label>
        </div>
      ))}
      {file.can_negotiate && Object.keys(marks).length > 0 && (
        <button className="button-outline" disabled={act.busy} onClick={() => act.run("PUT", `/deals/files/${file.id}/terms`, { changes: marks }).then((ok) => ok && setMarks({}))}>
          Send these changes to the seller
        </button>
      )}
      <p className="muted small">⚠ marks the seller's escape clauses. A fair promise struck out costs money and gains nothing.</p>
    </div>
  );
}

function Bid({ file, s, d, act }: { file: Any; s: Any; d: Any; act: Act }) {
  const [amount, setAmount] = useState("");
  const [loan, setLoan] = useState("");
  const [partner, setPartner] = useState("");
  const [pledge, setPledge] = useState("");
  const q = file.loan_quote;
  function bid(event: FormEvent) {
    event.preventDefault();
    const a = asKobo(amount);
    if (a) act.run("POST", `/deals/files/${file.id}/bid`, { amount_kobo: a, loan_kobo: asKobo(loan) ?? 0 });
  }
  return (
    <div className="bid">
      <p className="field-label">The bid · the head decides</p>
      {file.bid && <p className="small">Your bid: <Money kobo={file.bid.amount} /> (+ <Money kobo={file.bid.charge} compact /> for clauses) · empire's cash <Money kobo={file.bid.equity} compact /> · loan <Money kobo={file.bid.loan} compact /></p>}
      {q && <p className="small muted">{q.lender ? `${q.lender} would lend up to ${formatCompact(q.most)} at ${pct(q.rate_bps)}, secured on the company. It tests every quarter that the loan stays under ${q.covenants.debt_x_most} times the company's yearly earnings, and that earnings cover the interest ${(q.covenants.cover_least_bps / 10000).toFixed(1)} times.` : "No bank will lend against it at present."}</p>}
      {file.partners.length > 0 && file.partners.map((p: Any) => <div key={p.id} className="row small"><span>Partner: {p.empire}</span><span><Money kobo={p.amount} compact /> <Tag status={p.status} /></span></div>)}
      {!file.bid && d.partners.length > 0 && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(pledge); if (k && partner) act.run("POST", `/deals/files/${file.id}/partners`, { empire_id: Number(partner), amount_kobo: k }); }}>
          <select value={partner} onChange={(e) => setPartner(e.target.value)}><option value="">Invite a partner…</option>{d.partners.map((p: Any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          <input className="small-input" type="text" placeholder="₦ they put in" value={pledge} onChange={(e) => setPledge(e.target.value)} />
          <button className="button-quiet" disabled={act.busy || !partner || !asKobo(pledge)}>Invite</button>
        </form>
      )}
      {(!file.bid || s.mode === "auction") && (
        <form className="inline-form" onSubmit={bid}>
          <label className="answer"><span className="field-label">Price (₦)</span><input type="text" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
          <label className="answer"><span className="field-label">Of it borrowed (₦)</span><input type="text" value={loan} onChange={(e) => setLoan(e.target.value)} /></label>
          <button className="button-primary" disabled={act.busy || !asKobo(amount)}>{file.bid ? "Raise the bid" : "Place the bid"}</button>
        </form>
      )}
      {file.bid && s.mode === "sealed" && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/deals/files/${file.id}/bid`)}>Withdraw the bid</button>}
      <p className="muted small">The empire's part of the price is held in escrow while the bid stands. A sealed bid is opened when the quarter closes; at auction the highest bid is shown to everyone.</p>
    </div>
  );
}

function Bought({ x, act }: { x: Any; act: Act }) {
  const claimable = ["dressed_revenue", "hidden_debt", "worn_assets", "ownership_claim"].filter((c) => x.found.some((f: Any) => f.code === c) && !x.claims.some((k: Any) => k.code === c));
  return (
    <div className="report">
      <div className="row"><span><strong>{x.company}</strong> · bought {x.period}</span><span><Money kobo={x.price} compact /> <Tag status={x.status} /></span></div>
      <p className="small muted">In force: {x.terms.map((t: string) => t.replace(/_/g, " ")).join(", ") || "nothing beyond the price"}{x.escrow !== "0" ? ` · ${formatCompact(x.escrow)} held back until ${x.claims_until}` : ""}</p>
      {x.found.map((f: Any) => <p key={f.code} className="small">◆ {f.what} <span className="muted">({f.how})</span></p>)}
      {x.claims.map((c: Any) => <p key={c.code} className="small"><Arrow up={c.paid !== "0"} />{c.words}</p>)}
      {claimable.map((c) => <button key={c} className="button-outline" disabled={act.busy} onClick={() => act.run("POST", `/deals/${x.id}/claims`, { code: c })}>Claim: {c.replace(/_/g, " ")}</button>)}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Companies the empire controls
// ---------------------------------------------------------------------------

export function CompaniesTab({ f, act }: { f: Any; act: Act }) {
  const o = f.owned;
  if (!o) return <Panel title="Companies"><p className="muted">Only an empire run by players owns companies this way.</p></Panel>;
  return (
    <>
      {o.rescues_waiting.length > 0 && (
        <Panel title="Rescue plans offered" aside="An Accountant is paid only if the rescue works">
          {o.rescues_waiting.map((r: Any) => (
            <div key={r.id} className="row">
              <span>{r.company}: {r.measures.map((m: string) => o.rescue_measures[m]?.title ?? m).join(", ")} · fee <Money kobo={r.fee} compact /></span>
              <span className="inline-form">
                <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/rescues/${r.id}`, { accept: true })}>Accept</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/rescues/${r.id}`, { accept: false })}>Refuse</button>
              </span>
            </div>
          ))}
        </Panel>
      )}
      {o.companies.length === 0 && <Panel title="Companies the empire controls"><p className="muted">None yet. Buy one from the Deals tab.</p></Panel>}
      {o.companies.map((c: Any) => <Owned key={c.id} c={c} o={o} act={act} />)}
      <League league={o.league} />
    </>
  );
}

function Owned({ c, o, act }: { c: Any; o: Any; act: Act }) {
  const last = c.results[c.results.length - 1];
  return (
    <Panel title={c.name} aside={`${c.sector} · ${c.city} · bought ${c.bought}`}>
      <div className="tiles">
        <NumberTile label="Paid" value={formatCompact(c.cost)} />
        <NumberTile label="Worth now" value={formatCompact(c.value)} note={<><Arrow up={Number(c.value) >= Number(c.cost)} />{Number(c.value) >= Number(c.cost) ? "above" : "below"} the price</>} />
        <NumberTile label="Staff morale" value={pct(c.morale_bps)} note={c.morale_bps < 8500 ? "▼ slow work" : "steady"} />
        <NumberTile label="Pay against the going rate" value={pct(c.pay_ratio_bps)} />
      </div>
      {c.failing && <p className="error">▼ It is behind on its bills or its loans. Two closes like this while owing more than it owns, and it is wound up.</p>}
      {c.loan && (
        <p className={c.loan.broken.length ? "error" : "small muted"}>
          Buyout loan from {c.loan.lender}: <Money kobo={c.loan.outstanding} compact /> at {pct(c.loan.rate_bps)} · {c.loan.status}
          {c.loan.broken.map((b: string, i: number) => <span key={i}> ▼ {b}</span>)}
        </p>
      )}
      <table className="mini-table">
        <thead><tr><th>Quarter</th><th>Sales</th><th>Profit</th><th>Cash</th><th>Owed</th><th>Staff</th></tr></thead>
        <tbody>{c.results.map((r: Any) => (
          <tr key={r.period}><td>{r.label}</td><td><Money kobo={r.revenue} compact /></td><td><Money kobo={r.net_profit} compact /></td><td><Money kobo={r.cash} compact /></td>
            <td><Money kobo={r.borrowings} compact /></td><td className="mono">{Number(r.staff).toLocaleString("en-NG")}</td></tr>))}</tbody>
      </table>
      {last && <p className="small muted">Its accounts here are the truth: the empire owns the books now.</p>}
      {c.runs && <Dials c={c} act={act} />}
      <Assets c={c} act={act} />
      {c.is_airline && <Routes c={c} act={act} />}
      {c.candidates && <Managers c={c} act={act} />}
      {c.runs && <Plans c={c} o={o} act={act} />}
      {c.candidates && <Exits c={c} act={act} />}
    </Panel>
  );
}

const DIALS: { key: string; label: string; kind: "bps" | "money" | "count"; hint: string }[] = [
  { key: "price_bps", label: "Prices (100% = in line with rivals)", kind: "bps", hint: "70% to 140%. Dearer: more per sale, fewer customers; rivals answer a cut." },
  { key: "staff_bps", label: "Staff numbers (100% = as now)", kind: "bps", hint: "70% to 130%. Cuts save money and hurt morale." },
  { key: "pay_rise_bps", label: "Pay rise this quarter", kind: "bps", hint: "0% to 30%. Pay that falls behind prices costs morale." },
  { key: "marketing", label: "Marketing (₦)", kind: "money", hint: "Wins customers; the effect fades." },
  { key: "technology", label: "Technology (₦)", kind: "money", hint: "Lowers the cost of making what it sells, for good." },
  { key: "maintenance_bps", label: "Upkeep (100% = keep assets as they are)", kind: "bps", hint: "Less and assets wear, break down and are grounded." },
  { key: "payout_bps", label: "Dividend, share of profit", kind: "bps", hint: "Paid to its owners: your empire and partners." },
  { key: "borrow", label: "Borrow from its bank (₦)", kind: "money", hint: "If the bank has room and it is rated B or better." },
  { key: "buy_assets", label: `New assets to buy`, kind: "count", hint: "Bought from other companies as the quarter closes." },
];

function Dials({ c, act }: { c: Any; act: Act }) {
  const start = c.dials ?? { price_bps: c.price_bps, staff_bps: 10000, pay_rise_bps: 0, marketing: "0", technology: "0", maintenance_bps: 10000, payout_bps: 4000, borrow: "0", buy_assets: 0 };
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(DIALS.map((d) => [d.key,
    d.kind === "bps" ? String(Number(start[d.key]) / 100) : d.kind === "money" ? String(Number(start[d.key]) / 100) : String(start[d.key])])));
  function save(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, number> = {};
    for (const d of DIALS) {
      const v = values[d.key] ?? "0";
      body[d.key] = d.kind === "bps" ? Math.round(Number(v) * 100) : d.kind === "money" ? (asKobo(v) ?? 0) : Math.round(Number(v));
    }
    act.run("PUT", `/owned/${c.id}/dials`, body);
  }
  return (
    <form className="dials" onSubmit={save}>
      <p className="field-label">The dials · for this quarter, read as it closes · one asset costs about {formatCompact(c.unit_cost)}</p>
      {DIALS.map((d) => (
        <label key={d.key} className="answer">
          <span className="field-label">{d.label}</span>
          <span className="answer-box">
            {d.kind === "money" && <span className="muted small">₦</span>}
            <input type="text" inputMode="decimal" value={values[d.key]} onChange={(e) => setValues({ ...values, [d.key]: e.target.value })} />
            {d.kind === "bps" && <span className="muted small">%</span>}
          </span>
          <span className="muted small">{d.hint}</span>
        </label>
      ))}
      <button className="button-primary" disabled={act.busy}>Set the dials</button>
    </form>
  );
}

function Assets({ c, act }: { c: Any; act: Act }) {
  return (
    <div className="assets">
      <p className="field-label">Assets · serving up to {formatCompact(c.capacity)} of sales a quarter</p>
      {c.assets.map((a: Any) => (
        <div key={a.id} className="row small">
          <span>{a.name}{a.base ? ` · ${a.base}` : ""} · {a.age_quarters} of {a.life_quarters} quarters{a.status === "grounded" ? " · ▼ grounded" : ""}</span>
          <span className="inline-form">
            <Condition bps={a.condition_bps} />
            {c.runs && a.condition_bps < 6000 && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("POST", `/owned/assets/${a.id}/repair`)}>Repair</button>}
            {c.runs && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("POST", `/owned/assets/${a.id}/sell`)}>Sell</button>}
          </span>
        </div>
      ))}
    </div>
  );
}

function Routes({ c, act }: { c: Any; act: Act }) {
  const [a, setA] = useState(CITIES[0]);
  const [b, setB] = useState(CITIES[1]);
  const [fares, setFares] = useState<Record<number, string>>({});
  const planes = c.assets.filter((x: Any) => x.kind === "plane");
  return (
    <div className="routes">
      <p className="field-label">Routes · a fare above rivals' on the same route loses travellers; below wins them</p>
      {c.routes.map((r: Any) => (
        <div key={r.id} className="row small">
          <span>{r.from} ⇄ {r.to} · {r.planes} plane{r.planes === 1 ? "" : "s"} · fare {pct(r.fare_bps)}</span>
          {c.runs && (
            <span className="inline-form">
              <input className="small-input" type="text" placeholder="%" value={fares[r.id] ?? ""} onChange={(e) => setFares({ ...fares, [r.id]: e.target.value })} />
              <button className="button-quiet" disabled={act.busy || !fares[r.id]} onClick={() => act.run("PUT", `/owned/routes/${r.id}/fare`, { fare_bps: Math.round(Number(fares[r.id]) * 100) })}>Set fare</button>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/owned/routes/${r.id}`)}>Close</button>
            </span>
          )}
        </div>
      ))}
      {c.runs && (
        <>
          <div className="inline-form">
            <select value={a} onChange={(e) => setA(e.target.value)}>{CITIES.map((x) => <option key={x}>{x}</option>)}</select> ⇄
            <select value={b} onChange={(e) => setB(e.target.value)}>{CITIES.map((x) => <option key={x}>{x}</option>)}</select>
            <button className="button-outline" disabled={act.busy || a === b} onClick={() => act.run("POST", `/owned/${c.id}/routes`, { city_a: a, city_b: b })}>Open the route</button>
          </div>
          {planes.map((p: Any) => (
            <div key={p.id} className="row small"><span>{p.name}</span>
              <select value={p.route_id ?? ""} onChange={(e) => act.run("PUT", `/owned/assets/${p.id}/route`, { route_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">No route (earns nothing)</option>
                {c.routes.map((r: Any) => <option key={r.id} value={r.id}>{r.from} ⇄ {r.to}</option>)}
              </select>
            </div>
          ))}
          <p className="muted small">A plane based where the airline has no hangar wears twice as fast.</p>
        </>
      )}
    </div>
  );
}

function Managers({ c, act }: { c: Any; act: Act }) {
  return (
    <div className="managers">
      <p className="field-label">Managing director{c.manager ? `: ${c.manager.name} · ${STARS(c.manager.quality)} · ${formatCompact(c.manager.pay)} a quarter` : ""}</p>
      {c.candidates.map((m: Any) => (
        <div key={m.n} className="row small"><span>{m.name} · {STARS(m.quality)} · {formatCompact(m.pay)} a quarter</span>
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/owned/${c.id}/manager`, { n: m.n })}>Hire</button></div>
      ))}
      <p className="muted small">A better manager costs more, cuts the cost of making what it sells, wins customers and makes plans likelier to work.</p>
    </div>
  );
}

function Plans({ c, o, act }: { c: Any; o: Any; act: Act }) {
  return (
    <div className="plans">
      <p className="field-label">The 100-day plan{c.plan_open ? " · open in the first two quarters after buying" : " · closed"}</p>
      {c.plans.map((p: Any) => <p key={p.id} className="small">{p.kind === "rescue" ? "Rescue" : o.plans[p.code]?.title ?? p.code} · <Tag status={p.status} /> {p.outcome ?? `due ${p.due}`}</p>)}
      {c.plan_open && Object.entries(o.plans).map(([code, p]: [string, Any]) => (
        <div key={code} className="row small">
          <span>{p.title} · costs {pct(p.cost_bps)} of a quarter's sales · {p.quarters} quarter{p.quarters === 1 ? "" : "s"} · {pct(p.chance_bps)} chance · {p.effect}</span>
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run("POST", `/owned/${c.id}/plans`, { code })}>Start</button>
        </div>
      ))}
    </div>
  );
}

function Exits({ c, act }: { c: Any; act: Act }) {
  const [asking, setAsking] = useState("");
  const [reserve, setReserve] = useState("");
  const [mode, setMode] = useState("sealed");
  return (
    <div className="exits">
      <p className="field-label">Getting out</p>
      <div className="row small">
        <span>The pension funds would pay {formatNaira(c.buyer_offer)} for the empire's shares now (partners sell alongside).</span>
        <button className="button-outline" disabled={act.busy || c.on_sale} onClick={() => act.run("POST", `/owned/${c.id}/sell-to-buyer`)}>Sell to them</button>
      </div>
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const a = asKobo(asking); const r = asKobo(reserve); if (a && r) act.run("POST", `/owned/${c.id}/sell`, { asking_kobo: a, reserve_kobo: r, mode }); }}>
        <select value={mode} onChange={(e) => setMode(e.target.value)}><option value="sealed">Sealed bids</option><option value="auction">Auction</option></select>
        <input className="small-input" type="text" placeholder="Asking ₦" value={asking} onChange={(e) => setAsking(e.target.value)} />
        <input className="small-input" type="text" placeholder="Lowest you'll take ₦" value={reserve} onChange={(e) => setReserve(e.target.value)} />
        <button className="button-outline" disabled={act.busy || c.on_sale || !asKobo(asking) || !asKobo(reserve)}>Put it up for sale</button>
      </form>
      <div className="row small">
        <span>List it on the exchange: a quarter more shares sold to the public, a tenth below its valuation.</span>
        <button className="button-outline" disabled={act.busy || c.failing} onClick={() => act.run("POST", `/owned/${c.id}/list`)}>List it</button>
      </div>
      <p className="muted small">On a gain, the empire pays deal fees to the banker who brought it and to each player who did a check.</p>
    </div>
  );
}

function League({ league }: { league: Any }) {
  if (!league) return null;
  return (
    <Panel title={`Deal league · Year ${league.year}`} aside="Public">
      <p className="field-label">Largest sales</p>
      {league.biggest.length === 0 && <p className="muted small">None yet this year.</p>}
      {league.biggest.map((x: Any, i: number) => <div key={i} className="row small"><span>{i + 1}. {x.company}{x.empire ? ` → ${x.empire}` : ""}</span><Money kobo={x.price} compact /></div>)}
      <p className="field-label">Best exits</p>
      {league.exits.map((x: Any, i: number) => <div key={i} className="row small"><span>{i + 1}. {x.empire}: {x.company}</span><span><Arrow up={Number(x.gain) >= 0} /><Money kobo={x.gain} compact /></span></div>)}
      <p className="field-label">Bankers</p>
      {league.bankers.map((x: Any, i: number) => <div key={i} className="row small"><span>{i + 1}. {x.banker} · {x.deals} deal{x.deals === 1 ? "" : "s"}</span><Money kobo={x.value} compact /></div>)}
      {league.exits.length > 0 && <p className="muted small">The best exit of the year is the Deal of the Year. A gain is what an empire got out, less what it paid.</p>}
    </Panel>
  );
}
