// Foreign markets (the talent and funds stage, Part 4b), a tab inside Markets. Three exchanges abroad with their hours in
// Lagos time and their indexes; the companies listed there; buying and selling with dollars, pounds and euros; what a holding
// has made on the share and on the currency; the Nigerian arms of foreign companies; the economies abroad. The website only
// asks; the server decides.

import { useState } from "react";
import { api, ApiError, type WorldArm, type WorldCompany, type WorldCur, type WorldEconomies, type WorldEconomy, type WorldListed,
         type WorldPage, type WorldWallet } from "./api";
import { AreaChart, Sparkline } from "./Charts";
import { useLoad } from "./hooks";
import { NumberTile } from "./Parts";
import { Change, Failed, Loading, Panel } from "./Shell";
import { LineChart } from "./TrendChart";

const SYMBOL: Record<WorldCur, string> = { USD: "$", GBP: "£", EUR: "€" };
const PLURAL: Record<WorldCur, string> = { USD: "dollars", GBP: "pounds", EUR: "euros" };
const naira = (kobo: string | number) => `₦${(Number(kobo) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const money = (cents: string | number, c: WorldCur) =>
  `${SYMBOL[c]}${(Number(cents) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const big = (cents: string | number, c: WorldCur) => {
  const v = Number(cents) / 100;
  return v >= 1e12 ? `${SYMBOL[c]}${(v / 1e12).toFixed(2)}tn` : v >= 1e9 ? `${SYMBOL[c]}${(v / 1e9).toFixed(1)}bn` : `${SYMBOL[c]}${(v / 1e6).toFixed(0)}m`;
};
const points = (hundredths: string | number | null) =>
  hundredths === null ? "–" : (Number(hundredths) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (bps: number) => `${(bps / 100).toFixed(2)}%`;
const day = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "UTC" });
const signed = (kobo: string | number) => {
  const n = Number(kobo);
  return <span className={n > 0 ? "change-up" : n < 0 ? "change-down" : ""}>{n > 0 ? "+" : n < 0 ? "−" : ""}{naira(Math.abs(n))}</span>;
};

type Run = (path: string, body?: unknown) => Promise<boolean>;

function useRun(onChanged: () => void, reload: () => void, onLoggedOut: () => void): [Run, boolean, string | null, string | null] {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run: Run = async (path, body) => {
    setBusy(true); setError(null); setDone(null);
    try { await api.worldAct(path, body); setDone("Done."); onChanged(); reload(); return true; }
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

/** The Markets section's "World markets" tab. */
export function WorldWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const page = useLoad(api.world, "world", onLoggedOut);
  const [run, busy, error, done] = useRun(onChanged, page.reload, onLoggedOut);
  const [exchange, setExchange] = useState("HSE");
  const [chosen, setChosen] = useState<string | null>(null);
  const [forEmpire, setForEmpire] = useState(false);
  if (page.error) return <Failed message={page.error} onRetry={page.reload} />;
  if (!page.data) return <Loading what="the markets abroad" />;
  const d: WorldPage = page.data;
  if (!d.open) {
    return <Panel title="World markets"><p className="small">The markets abroad open at the next closing bell after the currency desk.</p></Panel>;
  }
  const wallet = forEmpire && d.empire ? d.empire : d.mine;
  const listed = d.companies.filter((c) => c.exchange === exchange);
  const said = <Said error={error} done={done} />;
  return (
    <>
      <Exchanges d={d} exchange={exchange} onPick={(code) => { setExchange(code); setChosen(null); }} />
      <Listed rows={listed} chosen={chosen} onPick={setChosen} />
      {chosen && (
        <CompanyPanel key={chosen} ticker={chosen} d={d} wallet={wallet} forEmpire={forEmpire} run={run} busy={busy} said={said}
                      onLoggedOut={onLoggedOut} />
      )}
      {d.empire && (
        <div className="row-gap" role="group" aria-label="Whose shares">
          <button className={forEmpire ? "button-quiet" : "button-outline"} aria-pressed={!forEmpire} onClick={() => setForEmpire(false)}>My own</button>
          <button className={forEmpire ? "button-outline" : "button-quiet"} aria-pressed={forEmpire} onClick={() => setForEmpire(true)}>{d.empire.name}'s</button>
        </div>
      )}
      {wallet && <Holdings wallet={wallet} whose={forEmpire && d.empire ? d.empire.name : "You"} onPick={(t) => {
        const co = d.companies.find((c) => c.ticker === t);
        if (co) { setExchange(co.exchange); setChosen(t); }
      }} />}
      <Arms d={d} run={run} busy={busy} said={said} />
      <EconomiesPanel economies={d.economies} />
      {d.etfs.length > 0 && <Panel title="Foreign shares in naira">
        <p className="small">
          Without dollars, pounds or euros you can still hold foreign shares: the{" "}
          {d.etfs.map((e, i) => <span key={e.code}>{i ? (i === d.etfs.length - 1 ? " and " : ", ") : ""}<span className="strong">{e.name}</span></span>)}{" "}
          trade in naira on the Broad Street Exchange (<a href="#/market/etfs">Indexes &amp; ETFs</a>). Their naira go abroad through the street to buy the
          shares, so their value moves with the shares and with the naira: a weaker naira lifts them.
        </p>
      </Panel>}
    </>
  );
}

function Exchanges({ d, exchange, onPick }: { d: WorldPage; exchange: string; onPick: (code: string) => void }) {
  return (
    <Panel title="The exchanges abroad" aside="hours in Lagos time">
      <div className="world-exchanges" role="tablist" aria-label="Exchanges">
        {d.exchanges.map((ex) => {
          const level = ex.level === null ? null : Number(ex.level);
          const close = ex.close === null ? null : Number(ex.close);
          const change = level !== null && close ? Math.round((level / close - 1) * 10000) : null;
          return (
            <button key={ex.code} role="tab" aria-selected={ex.code === exchange} className={ex.code === exchange ? "world-exchange current" : "world-exchange"}
                    onClick={() => onPick(ex.code)}>
              <span className="strong">{ex.name}</span>
              <span className="muted small">{ex.city} · {PLURAL[ex.currency]}</span>
              <span className="small"><span className={ex.is_open ? "dot-open" : "dot-closed"} aria-hidden="true" /> {ex.is_open ? "Open" : "Closed"}: {ex.opens} to {ex.closes}</span>
              <span className="mono">{ex.index_name} {points(level)} {change !== null && <Change bps={change} />}</span>
              {ex.days.length >= 2 && <Sparkline values={ex.days.map((x) => Number(x.level))} label={`${ex.index_name} over the last ${ex.days.length} days`} />}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function Listed({ rows, chosen, onPick }: { rows: WorldListed[]; chosen: string | null; onPick: (t: string) => void }) {
  if (!rows.length) return null;
  const cur = rows[0].currency;
  return (
    <Panel title="Companies" aside={`prices in ${PLURAL[cur]}`}>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Company</th><th>Kind</th><th className="num">Price</th><th className="num">Today</th><th className="num">Price to profit</th>
            <th className="num">Dividend a year</th><th className="num">Whole company</th></tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.ticker} className={chosen === c.ticker ? "world-row-chosen" : ""}>
                <td>
                  <button className="link-button" onClick={() => onPick(c.ticker)} aria-expanded={chosen === c.ticker}>
                    <span className="mono">{c.ticker}</span> {c.name}
                  </button>
                  {c.arm && c.arm.status !== "left" && <div className="muted small">Parent of {c.arm.name} in Nigeria</div>}
                </td>
                <td className="small">{c.sector}</td>
                <td className="num mono">{money(Math.round(c.price), c.currency)}</td>
                <td className="num"><Change bps={c.change_bps} /></td>
                <td className="num mono">{c.pe === null ? "–" : c.pe.toFixed(1)}</td>
                <td className="num mono">{pct(c.yield_bps)}</td>
                <td className="num mono">{big(c.cap, c.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function CompanyPanel({ ticker, d, wallet, forEmpire, run, busy, said, onLoggedOut }: {
  ticker: string; d: WorldPage; wallet: WorldWallet | null; forEmpire: boolean; run: Run; busy: boolean; said: React.ReactNode; onLoggedOut: () => void;
}) {
  const page = useLoad(() => api.worldCompany(ticker), `world:${ticker}:${wallet?.worth ?? ""}`, onLoggedOut);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [count, setCount] = useState("");
  if (page.error) return <Failed message={page.error} onRetry={page.reload} />;
  if (!page.data) return <Loading what={ticker} />;
  const c: WorldCompany = page.data;
  const cur = c.currency;
  const held = Number(wallet?.holdings.find((h) => h.ticker === ticker)?.shares ?? 0);
  const n = Math.floor(Number(count.replace(/[,\s]/g, "")) || 0);
  const each = side === "buy" ? c.ask : c.bid;
  const have = Number(wallet?.balances[cur] ?? 0);
  return (
    <Panel title={`${c.name} (${c.ticker})`} aside={`${c.exchange_name}, ${c.city}`}>
      <p className="small">{c.about}</p>
      <div className="tiles">
        <NumberTile label="Price now" value={money(Math.round(c.price), cur)} change={c.change_bps} />
        <NumberTile label="Worth, on its profits" value={money(Math.round(c.fair), cur)} note="what the price is drawn towards" />
        <NumberTile label="Profit a share, last year" value={money(Math.round(c.eps_ttm), cur)} note={c.pe ? `the price is ${c.pe.toFixed(1)} times it` : undefined} />
        <NumberTile label="Dividend a quarter" value={money(Math.round(c.dps), cur)} note={`15% is kept as tax abroad`} />
      </div>
      {c.days.length >= 2 && (
        <AreaChart label={`${c.name}'s closing price, day by day`} format={(v) => money(Math.round(v), cur)}
                   points={c.days.map((x) => ({ label: day(x.day), value: x.close }))} height={180} />
      )}
      {c.results.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">{c.name}'s quarters</caption>
            <thead><tr><th>Quarter</th><th className="num">Sales</th><th className="num">Profit</th><th className="num">Dividend a share</th>
              <th className="num">Worth a share</th></tr></thead>
            <tbody>
              {c.results.slice(0, 8).map((r) => (
                <tr key={r.period}><td>{r.label}</td><td className="num mono">{big(r.revenue, cur)}</td><td className="num mono">{big(r.profit, cur)}</td>
                  <td className="num mono">{money(Math.round(r.dps), cur)}</td><td className="num mono">{money(Math.round(r.fair), cur)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {wallet && (
        <form className="form-row" onSubmit={async (e) => {
          e.preventDefault();
          if (n > 0 && await run(`/world/companies/${ticker}/deal`, { side, shares: n, for_empire: forEmpire })) setCount("");
        }}>
          <div role="group" aria-label="Buy or sell" className="row-gap">
            <button type="button" className={side === "buy" ? "button-outline" : "button-quiet"} aria-pressed={side === "buy"} onClick={() => setSide("buy")}>Buy</button>
            <button type="button" className={side === "sell" ? "button-outline" : "button-quiet"} aria-pressed={side === "sell"} onClick={() => setSide("sell")}>Sell</button>
          </div>
          <label>Shares
            <input inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} placeholder={side === "sell" ? `${held}` : "100"} />
          </label>
          <button className="button" disabled={busy || n <= 0 || !c.is_open}>{side === "buy" ? "Buy" : "Sell"}</button>
          <p className="small muted">
            {c.is_open ? <>The brokers {side === "buy" ? "sell" : "buy"} at about {money(Math.round(each), cur)} a share{n > 0 ? `: about ${money(Math.round(each * n), cur)}` : ""}.</>
              : <>Closed now. It trades from {c.opens} to {c.closes}, Lagos time.</>}
            {" "}You have {money(have, cur)}{held ? ` and ${held.toLocaleString("en-NG")} shares` : ""}. <a href="#/currencies">Get {PLURAL[cur]}</a>.
          </p>
          {said}
        </form>
      )}
      {d.arms.filter((a) => a.parent_ticker === ticker).map((a) => (
        <p key={a.ticker} className="small">It owns {pct(a.stake_bps)} of <a href={`#/companies/${a.ticker}`}>{a.name}</a> on the Broad Street Exchange.</p>
      ))}
    </Panel>
  );
}

function Holdings({ wallet, whose, onPick }: { wallet: WorldWallet; whose: string; onPick: (t: string) => void }) {
  return (
    <Panel title={`${whose === "You" ? "Your" : `${whose}'s`} foreign shares`} aside={wallet.holdings.length ? `worth ${naira(wallet.worth)}` : undefined}>
      {wallet.holdings.length === 0 ? <p className="small muted">None yet. Buy dollars, pounds or euros on the Currencies tab, then choose a company above.</p> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Company</th><th className="num">Shares</th><th className="num">Worth</th><th className="num">In naira</th>
              <th className="num">Made on the share</th><th className="num">Made on the currency</th></tr></thead>
            <tbody>
              {wallet.holdings.map((h) => (
                <tr key={h.ticker}>
                  <td><button className="link-button" onClick={() => onPick(h.ticker)}><span className="mono">{h.ticker}</span> {h.name}</button></td>
                  <td className="num mono">{Number(h.shares).toLocaleString("en-NG")}</td>
                  <td className="num mono">{money(h.value, h.currency)}</td>
                  <td className="num mono">{naira(h.value_naira)}</td>
                  <td className="num mono">{signed(h.share_gain_naira)}</td>
                  <td className="num mono">{signed(h.currency_gain_naira)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted">"Made on the share" is the price's move since you bought, at today's rate. "Made on the currency" is what the naira's move did
        to what you paid: when the naira falls, foreign money is worth more naira.</p>
    </Panel>
  );
}

function Arms({ d, run, busy, said }: { d: WorldPage; run: Run; busy: boolean; said: React.ReactNode }) {
  if (!d.arms.length) return null;
  return (
    <Panel title="Nigerian arms of foreign companies">
      <p className="small">
        These companies on the Broad Street Exchange are owned in large part by a company listed abroad. Their parents' dividends wait in naira until the
        Central Bank can spare the dollars. A parent with years of dividends stuck here, or a naira that has lost much of its value, may sell out and leave.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Company</th><th>Parent abroad</th><th className="num">Parent holds</th><th className="num">Waiting for dollars</th><th>Now</th></tr></thead>
          <tbody>
            {d.arms.map((a) => (
              <tr key={a.ticker}>
                <td><a href={`#/companies/${a.ticker}`}><span className="mono">{a.ticker}</span> {a.name}</a></td>
                <td>{a.parent} <span className="muted small">({a.parent_ticker})</span></td>
                <td className="num mono">{pct(a.stake_bps)}</td>
                <td className="num mono">{naira(a.trapped)}</td>
                <td className="small">{a.status === "parent" ? "Staying" : a.status === "leaving" ? `Selling until ${a.deadline}` : "Left"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.is_head && d.arms.filter((a) => a.status === "leaving").map((a) => <StakeForm key={a.ticker} a={a} run={run} busy={busy} said={said} />)}
    </Panel>
  );
}

function StakeForm({ a, run, busy, said }: { a: WorldArm; run: Run; busy: boolean; said: React.ReactNode }) {
  const [count, setCount] = useState("");
  const n = Math.floor(Number(count.replace(/[,\s]/g, "")) || 0);
  return (
    <form className="form-row" onSubmit={async (e) => { e.preventDefault(); if (n > 0 && await run(`/world/arms/${a.ticker}/stake`, { shares: n })) setCount(""); }}>
      <p className="small">
        <span className="strong">{a.parent} is selling {Number(a.shares).toLocaleString("en-NG")} shares of {a.name}</span> at {a.asking ? naira(a.asking) : "–"} a share
        (the market price). Your empire may buy pieces of it, staying under 30% of the company.
      </p>
      <label>Shares<input inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} placeholder="100000" /></label>
      <button className="button" disabled={busy || n <= 0}>Buy for the empire{n > 0 && a.asking ? `: ${naira(Number(a.asking) * n)}` : ""}</button>
      {said}
    </form>
  );
}

function EconomiesPanel({ economies }: { economies: WorldEconomy[] }) {
  return (
    <Panel title="The economies abroad" aside={<a href="#/economy">more on the Economy page</a>}>
      <div className="tiles">
        {economies.map((e) => (
          <NumberTile key={e.code} label={e.name[0].toUpperCase() + e.name.slice(1)} value={`${pct(e.latest.rate_bps)} rate`}
                      note={`growth ${pct(e.latest.growth_bps)}, inflation ${pct(e.latest.inflation_bps)}`} />
        ))}
      </div>
    </Panel>
  );
}

/** On the Economy page: the economies abroad, their central banks and what they do to Nigeria. */
export function WorldEconomiesPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const page = useLoad(api.worldEconomies, "world-economies", onLoggedOut);
  if (!page.data || !page.data.open) return null;
  const d: WorldEconomies = page.data;
  return (
    <Panel title="The economies abroad" aside={`a pound ${(d.gbp_usd ?? 0).toFixed(3)} dollars, a euro ${(d.eur_usd ?? 0).toFixed(3)}`}>
      <p className="small">{d.rules}</p>
      <div className="world-economies">
        {(d.economies ?? []).map((e) => (
          <div key={e.code}>
            <h3 className="small strong">{e.name[0].toUpperCase() + e.name.slice(1)}: {e.bank}</h3>
            <p className="small">{e.latest.words} Growth {pct(e.latest.growth_bps)} a year (usual {pct(e.trend_bps)}).</p>
            {e.history.length >= 2 && (
              <LineChart names={["Inflation", "Interest rate"]} format={(v) => `${v.toFixed(2)}%`}
                         data={e.history.map((h) => ({ label: h.label, first: h.inflation_bps / 100, second: h.rate_bps / 100 }))} />
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

/** On a Nigerian company's page: its parent abroad, if it has one. */
export function ArmPanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const page = useLoad(() => api.worldArm(ticker), `world-arm:${ticker}`, onLoggedOut);
  const a = page.data?.arm;
  if (!a) return null;
  return (
    <Panel title="Its parent abroad">
      <p className="small">
        {a.words} {a.status !== "left" && <>{a.parent} ({a.parent_ticker}, listed abroad) holds {pct(a.stake_bps)} of it.{" "}
        {a.status === "parent" && (Number(a.trapped) > 0 ? `${naira(a.trapped)} of its dividends are waiting here for dollars to be sent home.` : "Its dividends go home as they are paid.")}</>}
        {a.status === "leaving" && <> It is selling its stake at {a.asking ? naira(a.asking) : "–"} a share until {a.deadline}: see <a href="#/market/world">World markets</a>.</>}
      </p>
    </Panel>
  );
}
