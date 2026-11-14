// Stage 12: the commodities desk — buy goods from the market, keep them in leased space, and sell them.
//
// The investor's face of the desk: the four goods, their spot prices, the space they are kept
// in, and what the player holds. The firm's face — the desk itself, the client quotes it has
// sent out, and the hedges it has placed — sits on the same page. Tabs divide the work so the
// page never asks the player to take in everything at once.

import { useState } from "react";
import {
  api,
  type CommodityDesk,
  type CommodityEvent,
  type CommodityGood,
  type CommodityHedge,
  type CommodityHolding,
  type CommodityLease,
  type CommodityPrice,
  type CommodityQuote,
  type CommodityTrade,
  type Kobo,
} from "./api";
import { formatCompact, formatNaira } from "./format";
import { useLoad } from "./hooks";
import {
  Band, BandCell, Failed, Loading, PageHead, Panel,
} from "./Shell";

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className={`tab ${active ? "active" : ""}`} onClick={onClick} aria-pressed={active}>
      {label}
    </button>
  );
}

type Props = { onLoggedOut: () => void; onChanged: () => void };

function fmt(k: Kobo) { return formatNaira(k); }

function goodPrice(prices: CommodityPrice[], code: string): CommodityPrice | null {
  const best = prices.filter((p) => p.good === code).sort((a, b) => b.period - a.period);
  return best.length ? best[0] : null;
}

const TABS = [
  { path: "market", label: "The market" },
  { path: "space", label: "Space you lease" },
  { path: "holdings", label: "What you hold" },
  { path: "desk", label: "The desk" },
  { path: "record", label: "The record" },
] as const;

type Tab = (typeof TABS)[number]["path"];

export function CommoditiesWork({ onLoggedOut, onChanged }: Props) {
  const page = useLoad(api.commodities, `commodities`, onLoggedOut);
  if (page.loading && !page.data) return <Loading what="the commodities desk" />;
  if (page.error || !page.data) return <Failed message={page.error ?? "Could not load the commodities desk."} onRetry={page.reload} />;

  const { goods, prices, leases, holdings, trades, events, desk, quotes, hedges } = page.data;
  const open = leases.filter((l) => l.status === "open");
  const [tab, setTab] = useState<Tab>("market");

  return (
    <>
      <PageHead title="Commodities" sub="Goods, the space they are kept in, and the market that deals in them" />
      <Band label="The commodities desk" columns={4}>
        <BandCell label="Goods on the market" value={goods.length} note={goods.length === 0 ? "none quoted yet" : goods.map((g) => g.name).join(", ")} />
        <BandCell label="Space leased" value={open.length} note={open.length === 0 ? "no open lease" : `${open.length} open`} />
        <BandCell label="What you hold" value={holdings.length} note={holdings.length === 0 ? "nothing yet" : `${holdings.reduce((t, h) => t + h.units, 0).toLocaleString("en-NG")} units`} />
        <BandCell label="The desk" value={desk ? desk.status : "—"} note={desk ? `limit ${formatCompact(String(desk.limit_kobo))}` : "no desk"} />
      </Band>

      <div className="tabs">
        {TABS.map((t) => (
          <TabButton key={t.path} active={tab === t.path} label={t.label} onClick={() => setTab(t.path)} />
        ))}
      </div>

      {tab === "market" && goods.length > 0 && <CommodityTable goods={goods} prices={prices} onChanged={onChanged} />}
      {tab === "market" && goods.length === 0 && (
        <Panel title="The market" aside="no prices yet">
          <p className="small">The market has not quoted any goods this quarter.</p>
        </Panel>
      )}
      {tab === "space" && <CommodityLeases leases={leases} goods={goods} onChanged={onChanged} />}
      {tab === "holdings" && (
        <>
          <CommodityHoldings holdings={holdings} />
          <CommodityTrades trades={trades} />
        </>
      )}
      {tab === "desk" && (
        <>
          {desk && <CommodityDeskPanel desk={desk} />}
          {quotes.length > 0 && <CommodityQuotes quotes={quotes} />}
          {hedges.length > 0 && <CommodityHedges hedges={hedges} />}
          {!desk && quotes.length === 0 && hedges.length === 0 && (
            <Panel title="The commodities desk" aside="no desk">
              <p className="small">The firm has no commodities desk. A desk quotes hedges to clients and covers them on the exchange.</p>
            </Panel>
          )}
        </>
      )}
      {tab === "record" && <CommodityEvents events={events} />}
    </>
  );
}

/** The four goods the market quotes, with the spot price and a buy/sell form. */
function CommodityTable({ goods, prices, onChanged }: { goods: CommodityGood[]; prices: CommodityPrice[]; onChanged: () => void }) {
  return (
    <Panel title="The market" aside={goods.length === 0 ? "no prices yet" : undefined}>
      {goods.length === 0 ? (
        <p className="small">The market has not quoted any goods this quarter.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Good</th><th scope="col" className="num">Spot</th><th scope="col" className="num">Unit</th><th scope="col" className="num">Least to buy</th><th scope="col" className="num">Buy</th><th scope="col" className="num">Sell</th>
            </tr>
          </thead>
          <tbody>
            {goods.map((g) => {
              const p = goodPrice(prices, g.code);
              return (
                <tr key={g.code}>
                  <th scope="row">{g.name}</th>
                  <td className="num mono">{p ? formatCompact(String(p.spot)) : "—"}</td>
                  <td className="num">{g.unit_word}</td>
                  <td className="num">{g.least_units.toLocaleString("en-NG")} {g.unit_plural}</td>
                  <td className="num"><CommodityBuy good={g} onChanged={onChanged} /></td>
                  <td className="num"><CommoditySell good={g} onChanged={onChanged} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function CommodityBuy({ good, onChanged }: { good: CommodityGood; onChanged: () => void }) {
  const [units, setUnits] = useState(String(good.least_units));
  const [error, setError] = useState<string | null>(null);
  const [going, setGoing] = useState(false);
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      setError(null);
      setGoing(true);
      api.commodityBuy({ good: good.code, units: Number(units) }).then(() => { onChanged(); }).catch((problem) => setError(problem instanceof Error ? problem.message : "That purchase did not go through.")).finally(() => setGoing(false));
    }}>
      <input type="number" min={good.least_units} value={units} onChange={(e) => setUnits(e.target.value)} aria-label={`Buy ${good.unit_plural} of ${good.name}`} />
      <button type="submit" disabled={going} className="button-quiet">Buy</button>
      {error && <p className="change-down small">{error}</p>}
    </form>
  );
}

function CommoditySell({ good, onChanged }: { good: CommodityGood; onChanged: () => void }) {
  const [units, setUnits] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [going, setGoing] = useState(false);
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      setError(null);
      setGoing(true);
      api.commoditySell({ good: good.code, units: Number(units) }).then(() => { onChanged(); }).catch((problem) => setError(problem instanceof Error ? problem.message : "That sale did not go through.")).finally(() => setGoing(false));
    }}>
      <input type="number" min={1} value={units} onChange={(e) => setUnits(e.target.value)} aria-label={`Sell ${good.unit_plural} of ${good.name}`} />
      <button type="submit" disabled={going} className="button-quiet">Sell</button>
      {error && <p className="change-down small">{error}</p>}
    </form>
  );
}

/** The player's leases: space rented from the market, with rent due each quarter, and a form to take more. */
function CommodityLeases({ leases, goods, onChanged }: { leases: CommodityLease[]; goods: CommodityGood[]; onChanged: () => void }) {
  const open = leases.filter((l) => l.status === "open");
  const closed = leases.filter((l) => l.status !== "open");
  const [newGood, setNewGood] = useState<string | null>(null);
  const [spaces, setSpaces] = useState("1");
  const [insured, setInsured] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [going, setGoing] = useState(false);

  const goodForNew = newGood ? goods.find((g) => g.code === newGood) : null;

  return (
    <Panel title="Space you lease" aside={open.length === 0 ? "no open lease" : `${open.length} open`}>
      {open.length === 0 ? (
        <p className="small">You have not leased any space. A lease holds goods of one kind, and rent is taken from your cash each quarter.</p>
      ) : (
        <table>
          <thead>
            <tr><th scope="col">Good</th><th scope="col" className="num">Capacity</th><th scope="col" className="num">Insured</th><th scope="col" className="num">Cost</th><th scope="col" className="num">Opened</th><th scope="col" className="num">Close</th></tr>
          </thead>
          <tbody>
            {open.map((l) => (
              <tr key={l.id}>
                <th scope="row">{l.good}</th>
                <td className="num">{l.capacity.toLocaleString("en-NG")}</td>
                <td className="num">{l.insured ? "yes" : "no"}</td>
                <td className="num mono">{fmt(String(l.lease_paid))}</td>
                <td className="num">{l.opened_period}</td>
                <td className="num"><button className="button-quiet" onClick={() => api.commodityCloseLease(l.id).then(onChanged).catch(() => undefined)}>Give up</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {closed.length > 0 && (
        <details><summary>{closed.length} given up or lost</summary>
          <table>
            <thead><tr><th scope="col">Good</th><th scope="col" className="num">Status</th><th scope="col" className="num">Why</th></tr></thead>
            <tbody>
              {closed.map((l) => (
                <tr key={l.id}>
                  <th scope="row">{l.good}</th>
                  <td className="num">{l.status}</td>
                  <td className="num">{l.close_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      <details>
        <summary>Take another lease</summary>
        <div className="form-row">
          <label>Good
            <select value={newGood ?? ""} onChange={(e) => setNewGood(e.target.value || null)} aria-label="Which good this space holds">
              <option value="">—</option>
              {goods.map((g) => <option key={g.code} value={g.code}>{g.name}</option>)}
            </select>
          </label>
          <label>Units of space
            <input type="number" min={1} value={spaces} onChange={(e) => setSpaces(e.target.value)} aria-label="How many units of space to lease" />
          </label>
          <label>
            <input type="checkbox" checked={insured} onChange={(e) => setInsured(e.target.checked)} aria-label="Insure the goods in this space" /> Insured
          </label>
        </div>
        {goodForNew && (
          <p className="small">
            Rent and insurance are taken from your cash each quarter. Goods that are not insured can be lost to fire, a leaking tank, rats or thieves.
          </p>
        )}
        <div className="row-gap">
          <button className="button" disabled={going || !goodForNew || !spaces || Number(spaces) < 1} onClick={(event) => {
            event.preventDefault();
            setError(null);
            setGoing(true);
            api.commodityLease({ good: goodForNew!.code, spaces: Number(spaces), insured }).then(() => { onChanged(); }).catch((problem) => setError(problem instanceof Error ? problem.message : "That lease did not go through.")).finally(() => setGoing(false));
          }}>Take the lease</button>
          {error && <p className="change-down small">{error}</p>}
        </div>
      </details>
    </Panel>
  );
}

/** What the player holds, lot by lot, with what each lot cost. */
function CommodityHoldings({ holdings }: { holdings: CommodityHolding[] }) {
  const byGood = new Map<string, CommodityHolding[]>();
  for (const h of holdings) {
    const list = byGood.get(h.good) ?? [];
    list.push(h);
    byGood.set(h.good, list);
  }
  return (
    <Panel title="What you hold" aside={holdings.length === 0 ? "nothing yet" : `${holdings.length} lots`}>
      {holdings.length === 0 ? (
        <p className="small">You do not hold any goods. Buy from the market and they are stored here, in a leased space, lot by lot.</p>
      ) : (
        <table>
          <thead>
            <tr><th scope="col">Good</th><th scope="col" className="num">Units</th><th scope="col" className="num">Cost</th><th scope="col" className="num">Bought</th></tr>
          </thead>
          <tbody>
            {Array.from(byGood.entries()).map(([good, lots]) => (
              <tr key={good}>
                <th scope="row">{good}</th>
                <td className="num">{lots.reduce((t, l) => t + l.units, 0).toLocaleString("en-NG")}</td>
                <td className="num mono">{fmt(String(lots.reduce((t, l) => t + l.cost, 0)))}</td>
                <td className="num">{lots.reduce((a, b) => a.bought_period > b.bought_period ? a : b).bought_period}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

/** Every trade the player has made with the market. */
function CommodityTrades({ trades }: { trades: CommodityTrade[] }) {
  return (
    <Panel title="Trades with the market" aside={trades.length === 0 ? "none yet" : `${trades.length} trades`}>
      {trades.length === 0 ? (
        <p className="small">Nothing bought or sold yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th scope="col">Good</th><th scope="col" className="num">Side</th><th scope="col" className="num">Units</th><th scope="col" className="num">Price</th><th scope="col" className="num">Period</th></tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id}>
                <th scope="row">{t.good}</th>
                <td className="num">{t.side}</td>
                <td className="num">{t.units.toLocaleString("en-NG")}</td>
                <td className="num mono">{fmt(String(t.price))}</td>
                <td className="num">{t.period}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

/** What happened to goods that nobody chose: rent, insurance, a loss, a delivery. */
function CommodityEvents({ events }: { events: CommodityEvent[] }) {
  return (
    <Panel title="The record" aside={events.length === 0 ? "nothing yet" : `${events.length} events`}>
      {events.length === 0 ? (
        <p className="small">The market has not recorded anything for you yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th scope="col">When</th><th scope="col">What</th><th scope="col" className="num">Amount</th><th scope="col" className="num">Units</th></tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <th scope="row">{e.period}</th>
                <td className="num">{e.words}</td>
                <td className="num mono">{e.amount > 0 ? fmt(String(e.amount)) : "—"}</td>
                <td className="num">{e.units > 0 ? e.units.toLocaleString("en-NG") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

/** The firm's desk: its limit, its status, and whether it is open for business. */
function CommodityDeskPanel({ desk }: { desk: CommodityDesk }) {
  return (
    <Panel title="The commodities desk" aside={`limit ${formatCompact(String(desk.limit_kobo))}`}>
      <table>
        <thead><tr><th scope="col">Status</th><th scope="col" className="num">Opened</th><th scope="col" className="num">Closed</th></tr></thead>
        <tbody>
          <tr>
            <th scope="row">{desk.status}</th>
            <td className="num">{desk.opened_period}</td>
            <td className="num">{desk.closed_period ?? "—"}</td>
          </tr>
        </tbody>
      </table>
    </Panel>
  );
}

/** The quotes the desk has sent out to clients: what was offered, at what price, and whether it was taken. */
function CommodityQuotes({ quotes }: { quotes: CommodityQuote[] }) {
  const open = quotes.filter((q) => q.status === "quoted");
  const done = quotes.filter((q) => q.status !== "quoted");
  return (
    <Panel title="Client quotes" aside={open.length === 0 ? "none open" : `${open.length} open`}>
      {open.length > 0 && (
        <table>
          <thead><tr><th scope="col">Client</th><th scope="col" className="num">Side</th><th scope="col" className="num">Units</th><th scope="col" className="num">Price</th><th scope="col" className="num">Expires</th></tr></thead>
          <tbody>
            {open.map((q) => (
              <tr key={q.id}>
                <th scope="row">{q.company?.name ?? "—"}</th>
                <td className="num">{q.side}</td>
                <td className="num">{q.units.toLocaleString("en-NG")}</td>
                <td className="num mono">{fmt(String(q.price))}</td>
                <td className="num">{q.expiry_period}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {done.length > 0 && (
        <details><summary>{done.length} settled or declined</summary>
          <table>
            <thead><tr><th scope="col">Client</th><th scope="col" className="num">Side</th><th scope="col" className="num">Units</th><th scope="col" className="num">Status</th></tr></thead>
            <tbody>
              {done.map((q) => (
                <tr key={q.id}>
                  <th scope="row">{q.company?.name ?? "—"}</th>
                  <td className="num">{q.side}</td>
                  <td className="num">{q.units.toLocaleString("en-NG")}</td>
                  <td className="num">{q.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </Panel>
  );
}

/** The hedges the desk has placed on the exchange to cover its quotes. */
function CommodityHedges({ hedges }: { hedges: CommodityHedge[] }) {
  return (
    <Panel title="Hedges on the exchange" aside={hedges.length === 0 ? "none yet" : `${hedges.length} placed`}>
      {hedges.length === 0 ? (
        <p className="small">The desk has not placed any hedge on the exchange.</p>
      ) : (
        <table>
          <thead><tr><th scope="col">Series</th><th scope="col" className="num">Contracts</th><th scope="col" className="num">Placed</th></tr></thead>
          <tbody>
            {hedges.map((h) => (
              <tr key={h.id}>
                <th scope="row">{String(h.series_id)}</th>
                <td className="num">{h.contracts}</td>
                <td className="num">{new Date(h.placed_at).toLocaleDateString("en-GB")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
