// The currency desk (the talent and funds stage, Part 4a), a tab inside Money. Two naira rates and the gap between them; the
// Central Bank's reserves; dollar, pound and euro balances; the street, the official window and the bureaux de change;
// Eurobonds; the companies carrying money sent home; an empire head's bureau and transfer company. The website only asks;
// the server decides.

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type FxAlert, type FxPage, type FxWallet } from "./api";
import { AreaChart } from "./Charts";
import { formatCompact } from "./format";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";
import { SingleLine } from "./TrendChart";

const CUR = ["USD", "GBP", "EUR"] as const;
type Cur = (typeof CUR)[number];
const SYMBOL: Record<Cur, string> = { USD: "$", GBP: "£", EUR: "€" };
const PLURAL: Record<Cur, string> = { USD: "dollars", GBP: "pounds", EUR: "euros" };
const naira = (kobo: string | number) => `₦${(Number(kobo) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const cash = (cents: string | number, c: Cur = "USD") => `${SYMBOL[c]}${(Number(cents) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const bigUsd = (cents: string | number) => {
  const d = Number(cents) / 100;
  return d >= 1e9 ? `$${(d / 1e9).toFixed(2)}bn` : d >= 1e6 ? `$${(d / 1e6).toFixed(1)}m` : cash(cents);
};
const pct = (bps: number) => `${(bps / 100).toFixed(bps % 100 === 0 ? 0 : 2)}%`;
const day = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "UTC" });
const toCents = (text: string) => Math.round(Number(text.replace(/[,\s$£€]/g, "")) * 100);

type Run = (path: string, body?: unknown) => Promise<boolean>;

function useRun(onChanged: () => void, reload: () => void, onLoggedOut: () => void): [Run, boolean, string | null, string | null] {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run: Run = async (path, body) => {
    setBusy(true); setError(null); setDone(null);
    try { await api.fxAct(path, body); setDone("Done."); onChanged(); reload(); return true; }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) { onLoggedOut(); return false; }
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
      return false;
    }
    finally { setBusy(false); }
  };
  return [run, busy, error, done];
}

function Said({ error, done }: { error: string | null; done: string | null }) {
  if (error) return <p className="error small" role="alert">{error}</p>;
  if (done) return <p className="small change-up" role="status">{done}</p>;
  return null;
}

/** The Money section's "Currencies" tab. */
export function CurrenciesWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const page = useLoad(api.fx, "fx", onLoggedOut);
  const [run, busy, error, done] = useRun(onChanged, page.reload, onLoggedOut);
  const [forEmpire, setForEmpire] = useState(false);
  if (page.error) return <Failed message={page.error} onRetry={page.reload} />;
  if (!page.data) return <Loading what="the currency desk" />;
  const d: FxPage = page.data;
  if (!d.open) {
    return (
      <>
        <div className="work-head"><h1>Currencies</h1></div>
        <Panel title="The currency desk"><p className="small">The currency desk opens at the next closing bell.</p></Panel>
      </>
    );
  }
  const wallet: FxWallet = forEmpire && d.empire ? d.empire : d.mine;
  const said = <Said error={error} done={done} />;
  return (
    <>
      <div className="work-head">
        <div>
          <h1>Currencies</h1>
          <div className="work-sub">Dollars, pounds and euros; the naira’s two rates; Eurobonds</div>
        </div>
        <span className="muted small">{d.regime === "managed" ? "the naira is managed by the Central Bank" : "the naira floats"}</span>
      </div>
      <Rates d={d} />
      {d.empire && (
        <div className="row-gap" role="group" aria-label="Whose money">
          <button className={forEmpire ? "button-quiet" : "button-outline"} aria-pressed={!forEmpire} onClick={() => setForEmpire(false)}>My own money</button>
          <button className={forEmpire ? "button-outline" : "button-quiet"} aria-pressed={forEmpire} onClick={() => setForEmpire(true)}>{d.empire.name}'s money</button>
        </div>
      )}
      <Balances d={d} wallet={wallet} />
      <Street d={d} wallet={wallet} run={run} busy={busy} forEmpire={forEmpire} said={said} />
      <Window d={d} wallet={wallet} run={run} busy={busy} forEmpire={forEmpire} said={said} />
      <Bureaux d={d} run={run} busy={busy} forEmpire={forEmpire} said={said} />
      <Eurobonds d={d} run={run} busy={busy} forEmpire={forEmpire} said={said} />
      <Remitters d={d} />
      {d.is_head && <EmpireBusinesses d={d} run={run} busy={busy} said={said} />}
      <Panel title="Hedging with a currency forward">
        <p className="small">
          A <span className="strong">currency forward</span> fixes today the naira you will pay for a dollar in a coming quarter. At each quarter's close
          only the difference against the official rate changes hands. Arrange one with a bank or another player under <a href="#/market/derivatives">Markets, Options and futures</a> (the swaps form).
        </p>
      </Panel>
    </>
  );
}

function Rates({ d }: { d: FxPage }) {
  const gapWide = d.gap_bps >= 1000;
  return (
    <Panel title="The naira">
      <section className="band band-4" aria-label="The naira today">
        <div className="band-cell">
          <div className="band-label">Official rate (a dollar)</div>
          <div className="band-value">{naira(d.official)}</div>
          <div className="band-note">at the Central Bank’s window</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Street rate (a dollar)</div>
          <div className="band-value">{naira(d.street)}</div>
          <div className="band-note">buy or sell at once</div>
        </div>
        <div className="band-cell">
          <div className="band-label">The gap</div>
          <div className={`band-value${gapWide ? " change-down" : ""}`}>{gapWide ? "▲ " : ""}{pct(d.gap_bps)}</div>
          <div className="band-note">the street over the official rate</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Central Bank’s reserves</div>
          <div className="band-value">{bigUsd(d.reserves)}</div>
          <div className="band-note">{(d.cover_bps / 10000).toFixed(1)} quarters of imports</div>
        </div>
      </section>
      <p className="small">{d.words}{BigInt(d.backlog) > 0n ? ` Foreign investors have ${formatCompact(d.backlog)} waiting for dollars to leave.` : ""}</p>
      {d.days.length >= 2 && (
        <>
          <h3 className="small strong">How far the street is above the official rate, day by day</h3>
          <SingleLine name="Gap" format={(v) => `${v.toFixed(1)}%`}
            data={d.days.map((x) => ({ label: day(x.session_date), value: x.premium_bps / 100 }))} />
        </>
      )}
      {d.quarters.length >= 2 && (
        <>
          <h3 className="small strong">The Central Bank's reserves</h3>
          <AreaChart label="The Central Bank's dollar reserves, quarter by quarter" format={(v) => `$${(v / 1e9).toFixed(2)}bn`}
            points={d.quarters.map((q) => ({ label: q.label, value: Number(q.reserves) / 100 }))} />
        </>
      )}
      <details>
        <summary className="small">How the naira is run</summary>
        <ul className="small">
          <li>While the Central Bank <span className="strong">manages</span> the naira it moves the official rate a little towards the market each quarter. When the street runs 5% or more above it, and it has two quarters of imports or more in reserve, it sells dollars on the street to pull it back.</li>
          <li>When the gap reaches 15% and its reserves are under two and a half quarters of imports, it <span className="strong">devalues</span>: the official rate jumps to the market's.</li>
          <li>Under one quarter of imports it lets the naira <span className="strong">float</span>: the official rate follows the street. Back over three quarters, it manages it again.</li>
          <li>When reserves run low the Government borrows dollars abroad with a Eurobond.</li>
        </ul>
        <div className="scroll"><table className="dense small">
          <thead><tr><th scope="col">Quarter</th><th scope="col">Official</th><th scope="col">Market</th><th scope="col">Reserves</th><th scope="col">What happened</th></tr></thead>
          <tbody>
            {d.quarters.slice(-8).reverse().map((q) => (
              <tr key={q.period}><td>{q.label}</td><td className="mono">{naira(q.official)}</td><td className="mono">{naira(q.market)}</td>
                <td className="mono">{bigUsd(q.reserves)}</td><td>{q.event ?? (q.regime === "float" ? "floating" : "managed")}</td></tr>
            ))}
          </tbody>
        </table>
        </div>
      </details>
    </Panel>
  );
}

function Balances({ d, wallet }: { d: FxPage; wallet: FxWallet }) {
  return (
    <Panel title="Money in other currencies" aside={`worth ${naira(wallet.worth)} at the street's buying price`}>
      <div className="scroll"><table className="dense">
        <thead><tr><th scope="col">Currency</th><th scope="col" className="num">Held</th><th scope="col" className="num">Street buys at</th><th scope="col" className="num">Street sells at</th></tr></thead>
        <tbody>
          {d.quotes.map((q) => (
            <tr key={q.currency}>
              <th scope="row">{d.names[q.currency]}</th>
              <td className="num mono">{cash(wallet.balances[q.currency], q.currency)}</td>
              <td className="num mono">{naira(q.buy)}</td><td className="num mono">{naira(q.sell)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {BigInt(wallet.kept) > 0n && <p className="small">{cash(wallet.kept)} came from the official window in the last two quarters. It can be sold back to the window, not on the street.</p>}
      {wallet.trades.length > 0 && (
        <details>
          <summary className="small">Recent deals</summary>
          <div className="scroll"><table className="dense small">
            <thead><tr><th scope="col">When</th><th scope="col">Where</th><th scope="col">Deal</th><th scope="col" className="num">Rate</th><th scope="col" className="num">Naira</th></tr></thead>
            <tbody>{wallet.trades.map((t, i) => (
              <tr key={i}><td>{day(t.at)}</td><td>{t.venue === "bdc" ? "bureau" : t.venue}</td>
                <td>{t.side === "buy" ? "bought" : "sold"} {cash(t.amount, t.currency as Cur)}</td><td className="num mono">{naira(t.rate)}</td><td className="num mono">{naira(t.naira)}</td></tr>
            ))}</tbody>
          </table>
          </div>
        </details>
      )}
    </Panel>
  );
}

type Part = { d: FxPage; run: Run; busy: boolean; forEmpire: boolean; said: JSX.Element };

function Street({ d, wallet, run, busy, forEmpire, said }: Part & { wallet: FxWallet }) {
  const [currency, setCurrency] = useState<Cur>("USD");
  const [amount, setAmount] = useState("");
  const q = d.quotes.find((x) => x.currency === currency)!;
  const cents = toCents(amount);
  const ok = Number.isFinite(cents) && cents >= 1000;
  return (
    <Panel title="The street" aside="at once, at the street's prices">
      <div className="form-row">
        <label>Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value as Cur)}>{CUR.map((c) => <option key={c} value={c}>{d.names[c]}</option>)}</select>
        </label>
        <label>Amount ({SYMBOL[currency]})
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="1,000" />
        </label>
      </div>
      {ok && <p className="small">Buying costs {naira(Math.ceil(cents * Number(q.sell) / 100))}. Selling pays {naira(Math.floor(cents * Number(q.buy) / 100))}. You hold {cash(wallet.balances[currency], currency)}.</p>}
      <div className="row-gap">
        <button className="button" disabled={busy || !ok} onClick={() => run("/fx/street", { side: "buy", currency, amount: cents, for_empire: forEmpire })}>Buy {PLURAL[currency]}</button>
        <button className="button-outline" disabled={busy || !ok} onClick={() => run("/fx/street", { side: "sell", currency, amount: cents, for_empire: forEmpire })}>Sell</button>
      </div>
      {said}
    </Panel>
  );
}

function Window({ d, wallet, run, busy, forEmpire, said }: Part & { wallet: FxWallet }) {
  const [amount, setAmount] = useState("");
  const cents = toCents(amount);
  const ok = Number.isFinite(cents) && cents >= 1000;
  const left = Number(wallet.window_limit) - Number(wallet.window_used);
  const waiting = wallet.requests.filter((r) => r.status === "waiting");
  return (
    <Panel title="The official window" aside={`${cash(Math.max(left, 0))} of ${cash(wallet.window_limit)} left this quarter`}>
      <p className="small">
        Dollars at the official rate ({naira(d.official)}), handed out in turn from the Central Bank's daily allocation. The naira for your request,
        and a tenth more in case the rate moves, are held until it is filled. Dollars from the window cannot be sold on the street for two quarters.
      </p>
      <div className="form-row">
        <label>Dollars ($)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="5,000" /></label>
      </div>
      <div className="row-gap">
        <button className="button" disabled={busy || !ok} onClick={() => run("/fx/window", { amount: cents, for_empire: forEmpire })}>Ask for dollars</button>
        <button className="button-outline" disabled={busy || !ok} onClick={() => run("/fx/window/sell", { amount: cents, for_empire: forEmpire })}>Sell dollars to the window</button>
      </div>
      {said}
      {wallet.requests.length > 0 && (
        <div className="scroll"><table className="dense small">
          <thead><tr><th scope="col">Asked</th><th scope="col" className="num">Dollars</th><th scope="col" className="num">Filled</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
          <tbody>{wallet.requests.map((r) => (
            <tr key={r.id}><td>{day(r.placed_at)}</td><td className="num mono">{cash(r.amount)}</td><td className="num mono">{cash(r.filled)}</td><td>{r.status}</td>
              <td>{r.status === "waiting" && <button className="button-quiet" disabled={busy} onClick={() => run(`/fx/window/${r.id}/cancel`, { for_empire: forEmpire })}>Withdraw</button>}</td></tr>
          ))}</tbody>
        </table>
        </div>
      )}
      {waiting.length > 0 && <p className="small muted">The window hands out a share of the reserves at each closing bell. Requests are filled oldest first.</p>}
    </Panel>
  );
}

function Bureaux({ d, run, busy, forEmpire, said }: Part) {
  const [chosen, setChosen] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  if (d.bdcs.length === 0) return null;
  const cents = toCents(amount);
  const ok = chosen !== null && Number.isFinite(cents) && cents >= 1000;
  return (
    <Panel title="Bureaux de change" aside="run by empires, at their own prices">
      <div className="scroll"><table className="dense">
        <thead><tr><th scope="col">Bureau</th><th scope="col">Run by</th><th scope="col" className="num">Buys a dollar at</th><th scope="col" className="num">Sells a dollar at</th><th scope="col"><span className="sr-only">Choose</span></th></tr></thead>
        <tbody>{d.bdcs.map((b) => (
          <tr key={b.id}><th scope="row">{b.name}</th><td>{b.empire}</td><td className="num mono">{naira(b.buy)}</td><td className="num mono">{naira(b.sell)}</td>
            <td><button className={chosen === b.id ? "button-outline" : "button-quiet"} aria-pressed={chosen === b.id} onClick={() => setChosen(b.id)}>Deal here</button></td></tr>
        ))}</tbody>
      </table>
      </div>
      <div className="form-row"><label>Dollars ($)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label></div>
      <div className="row-gap">
        <button className="button" disabled={busy || !ok} onClick={() => run(`/fx/bdcs/${chosen}/deal`, { side: "buy", amount: cents, for_empire: forEmpire })}>Buy dollars</button>
        <button className="button-outline" disabled={busy || !ok} onClick={() => run(`/fx/bdcs/${chosen}/deal`, { side: "sell", amount: cents, for_empire: forEmpire })}>Sell dollars</button>
      </div>
      <p className="small muted">Every deal of {cash(d.licences.report)} or more is reported to the regulator.</p>
      {said}
    </Panel>
  );
}

function Eurobonds({ d, run, busy, forEmpire, said }: Part) {
  const [units, setUnits] = useState<Record<number, string>>({});
  return (
    <Panel title="Eurobonds" aside="dollar bonds of the Government and the largest companies">
      <p className="small">Bought and sold with dollars. Interest is paid in dollars every quarter, and the face ($1,000 a bond) when it is due. Prices fall when lenders see more risk in Nigeria.</p>
      <div className="scroll"><table className="dense">
        <thead><tr><th scope="col">Bond</th><th scope="col" className="num">Interest</th><th scope="col" className="num">Yield</th><th scope="col" className="num">Buy at</th><th scope="col" className="num">Sell at</th><th scope="col" className="num">Yours</th><th scope="col">Bonds</th></tr></thead>
        <tbody>{d.eurobonds.map((b) => {
          const n = Number(units[b.id] ?? "");
          const ok = Number.isInteger(n) && n > 0;
          return (
            <tr key={b.id}>
              <th scope="row">{b.name}{b.defaulted && <span className="change-down"> (in default)</span>}</th>
              <td className="num mono">{pct(b.coupon_bps)}</td><td className="num mono">{pct(b.yield_bps)}</td>
              <td className="num mono">{cash(b.buy)}</td><td className="num mono">{cash(b.sell)}</td>
              <td className="num mono">{forEmpire ? b.empire : b.mine}</td>
              <td>
                <input aria-label={`Bonds of ${b.name}`} className="input-small" inputMode="numeric" value={units[b.id] ?? ""} onChange={(e) => setUnits({ ...units, [b.id]: e.target.value })} />
                <button className="button-quiet" disabled={busy || !ok} onClick={() => run(`/fx/eurobonds/${b.id}`, { side: "buy", units: n, for_empire: forEmpire })}>Buy</button>
                <button className="button-quiet" disabled={busy || !ok} onClick={() => run(`/fx/eurobonds/${b.id}`, { side: "sell", units: n, for_empire: forEmpire })}>Sell</button>
              </td>
            </tr>
          );
        })}</tbody>
      </table>
      </div>
      {said}
    </Panel>
  );
}

function Remitters({ d }: { d: FxPage }) {
  return (
    <Panel title="Money sent home" aside="carried by money-transfer companies">
      <p className="small">Nigerians abroad send dollars home every day, more at Easter and Christmas, and more when the street pays more naira. Families choose the cheapest and fastest companies.</p>
      <div className="scroll"><table className="dense">
        <thead><tr><th scope="col">Company</th><th scope="col" className="num">Fee</th><th scope="col" className="num">Days to arrive</th><th scope="col" className="num">Share of the last day</th></tr></thead>
        <tbody>{d.remitters.map((r) => (
          <tr key={r.id}><th scope="row">{r.name}{r.computer ? "" : " (an empire's)"}</th><td className="num mono">{pct(r.fee_bps)}</td>
            <td className="num mono">{r.days}</td><td className="num mono">{pct(r.share_bps)}</td></tr>
        ))}</tbody>
      </table>
      </div>
    </Panel>
  );
}

function EmpireBusinesses({ d, run, busy, said }: { d: FxPage; run: Run; busy: boolean; said: JSX.Element }) {
  const [name, setName] = useState("");
  const [buy, setBuy] = useState(d.my_bdc ? String(d.my_bdc.buy_bps / 100) : "1");
  const [sell, setSell] = useState(d.my_bdc ? String(d.my_bdc.sell_bps / 100) : "1");
  const [rname, setRname] = useState("");
  const [fee, setFee] = useState(d.my_remitter ? String(d.my_remitter.fee_bps / 100) : "3");
  const [days, setDays] = useState(d.my_remitter ? String(d.my_remitter.days) : "2");
  const bps = (t: string) => Math.round(Number(t) * 100);
  return (
    <Panel title="Your empire's currency businesses">
      <h3 className="small strong">A bureau de change</h3>
      {d.my_bdc ? (
        <>
          <p className="small">{d.my_bdc.name} buys a dollar at {naira(d.my_bdc.buy)} and sells at {naira(d.my_bdc.sell)}. It holds {cash(d.my_bdc.dollars)} and {naira(d.my_bdc.naira)} (the empire's money).
            It buys its dollars on the street, never at the official window.</p>
          <div className="form-row">
            <label>Buy below the street's middle (%)<input inputMode="decimal" value={buy} onChange={(e) => setBuy(e.target.value)} /></label>
            <label>Sell above it (%)<input inputMode="decimal" value={sell} onChange={(e) => setSell(e.target.value)} /></label>
          </div>
          <div className="row-gap">
            <button className="button-outline" disabled={busy} onClick={() => run("/fx/bdc/prices", { buy_bps: bps(buy), sell_bps: bps(sell) })}>Set prices</button>
            <button className="button-quiet" disabled={busy} onClick={() => run("/fx/bdc/close")}>Close the bureau</button>
          </div>
          {d.my_bdc.reports.length > 0 && (
            <details><summary className="small">Reported to the regulator</summary>
              <ul className="small">{d.my_bdc.reports.map((r, i) => <li key={i}>{day(r.at)}: {cash(r.amount)} with {r.customer}</li>)}</ul>
            </details>
          )}
        </>
      ) : (
        <>
          <p className="small">A licence costs {naira(d.licences.bdc)}, and the empire needs {naira(d.licences.bdc_capital)} behind it. Households and players deal with the cheapest bureaux.</p>
          <div className="form-row">
            <label>Name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} /></label>
            <label>Buy below the street's middle (%)<input inputMode="decimal" value={buy} onChange={(e) => setBuy(e.target.value)} /></label>
            <label>Sell above it (%)<input inputMode="decimal" value={sell} onChange={(e) => setSell(e.target.value)} /></label>
          </div>
          <button className="button" disabled={busy || name.trim().length < 3} onClick={() => run("/fx/bdc", { name, buy_bps: bps(buy), sell_bps: bps(sell) })}>Open a bureau de change</button>
        </>
      )}
      <h3 className="small strong">A money-transfer company</h3>
      {d.my_remitter ? (
        <>
          <p className="small">{d.my_remitter.name} charges {pct(d.my_remitter.fee_bps)} and delivers in {d.my_remitter.days} days. Faster costs more to run.</p>
          <div className="form-row">
            <label>Fee (%)<input inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} /></label>
            <label>Days to arrive (0 to 5)<input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} /></label>
          </div>
          <div className="row-gap">
            <button className="button-outline" disabled={busy} onClick={() => run("/fx/remitter/terms", { fee_bps: bps(fee), days: Number(days) })}>Set terms</button>
            <button className="button-quiet" disabled={busy} onClick={() => run("/fx/remitter/close")}>Close it</button>
          </div>
          {d.my_remitter.days_record.length > 0 && (
            <div className="scroll"><table className="dense small"><thead><tr><th scope="col">Day</th><th scope="col" className="num">Carried</th><th scope="col" className="num">Fees</th><th scope="col" className="num">Cost of speed</th></tr></thead>
              <tbody>{d.my_remitter.days_record.map((r) => <tr key={r.session_date}><td>{day(r.session_date)}</td><td className="num mono">{cash(r.dollars)}</td><td className="num mono">{naira(r.fee)}</td><td className="num mono">{naira(r.cost)}</td></tr>)}</tbody>
            </table>
            </div>
          )}
        </>
      ) : (
        <>
          <p className="small">A licence costs {naira(d.licences.remitter)}. Families pick the cheapest and fastest.</p>
          <div className="form-row">
            <label>Name<input value={rname} onChange={(e) => setRname(e.target.value)} maxLength={60} /></label>
            <label>Fee (%)<input inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} /></label>
            <label>Days to arrive (0 to 5)<input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} /></label>
          </div>
          <button className="button" disabled={busy || rname.trim().length < 3} onClick={() => run("/fx/remitter", { name: rname, fee_bps: bps(fee), days: Number(days) })}>Open a money-transfer company</button>
        </>
      )}
      {said}
    </Panel>
  );
}

function remembered(): number | null {
  try { const v = window.localStorage.getItem("wsbm-fx-alerts"); return v === null ? null : Number(v); } catch { return null; }
}

/** The currency desk's pop-ups: a devaluation, a float, the Central Bank stepping in, reserves falling, a wide gap, the backlog. */
export function FxAlerts({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [shown, setShown] = useState<FxAlert[]>([]);
  const mark = useRef<number | null>(remembered());
  useEffect(() => {
    let stopped = false;
    function look() {
      api.fxAlerts(mark.current).then((found) => {
        if (stopped) return;
        mark.current = found.mark;
        if (found.alerts.length) setShown((now) => [...now, ...found.alerts.filter((i) => !now.some((x) => x.id === i.id))].slice(-3));
      }).catch((problem) => { if (problem instanceof ApiError && problem.status === 401) onLoggedOut(); });
    }
    look();
    const timer = window.setInterval(look, 60_000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [onLoggedOut]);
  if (shown.length === 0) return null;
  const a = shown[shown.length - 1];
  const abroad = a.kind.startsWith("world");      // Part 4b: the markets abroad share these pop-ups
  const close = () => {
    try {
      const before = Number(window.localStorage.getItem("wsbm-fx-alerts") ?? "0");
      window.localStorage.setItem("wsbm-fx-alerts", String(Math.max(before, ...shown.map((x) => x.id))));
    } catch { /* not remembered: fine */ }
    setShown((now) => now.slice(0, -1));
  };
  return (
    <div className="bank-alert-region fund-alert-region fx-alert-region">
      <div className="bank-alert fund-alert" role="alertdialog" aria-labelledby={`fx-alert-${a.id}`}>
        <div className="bank-alert-tag">● {abroad ? "Markets abroad" : "The naira"}</div>
        <div className="bank-alert-headline" id={`fx-alert-${a.id}`}>{a.headline}</div>
        <p className="small">{a.words}</p>
        <div className="bank-alert-actions">
          {abroad ? <a className="button-outline" href={a.kind === "world_rate" ? "#/economy" : "#/market/world"} onClick={close}>See the markets abroad</a>
            : <a className="button-outline" href="#/currencies" onClick={close}>See the currency desk</a>}
          <button className="button-quiet" onClick={close}>Close{shown.length > 1 ? ` (${shown.length - 1} more)` : ""}</button>
        </div>
      </div>
    </div>
  );
}
