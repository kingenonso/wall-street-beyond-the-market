import { WhatCouldHappenPanel } from "./WhatIf";
import { SavingsPanel } from "./Crisis";
import { useState } from "react";
import { api, ApiError, type Order } from "./api";
import { formatCompact, formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Gain, Loading, Panel } from "./Shell";
import { shortDate } from "./Market";
import { SingleLine } from "./TrendChart";
import { CompareChart, MixBar } from "./Charts";
import { NumberTile } from "./Parts";
import { Term } from "./Term";

/** The starting grant, paid in parts as the player does real things. Asking also collects any part that is due. */
export function GrantPanel({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const { data: g } = useLoad(() => api.grant().then((grant) => { onChanged(); return grant; }), "grant", onLoggedOut);
  if (!g || g.steps.every((s) => s.paid)) return null;
  const next = g.next_payment_at ? new Date(g.next_payment_at) : null;
  return (
    <Panel title="Your starting grant" aside={`${formatNaira(g.received_kobo)} of ${formatNaira(g.total_kobo)} received`}>
      <p className="small">
        You received ₦100,000 on joining. The rest comes in four parts of ₦100,000, one for each of these, and at most one
        part in twenty hours.
      </p>
      {g.steps.map((s) => (
        <div key={s.step} className="row">
          <span>{s.paid ? "✓" : s.earned ? "●" : "○"} {s.what}</span>
          <span className={s.paid ? "change-up" : "muted"}>{s.paid ? "Paid" : s.earned ? "Done, payment waiting" : "Not yet"}</span>
        </div>
      ))}
      {next && <p className="small muted">The next part can be paid after {next.toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "short", hour: "2-digit", minute: "2-digit" })} Lagos time.</p>}
    </Panel>
  );
}

const shares = (count: number) => count.toLocaleString("en-NG");

/** One holding's share of all the player's shares, as a bar and a figure. */
function ShareBar({ part, whole }: { part: string; whole: string }) {
  const total = BigInt(whole);
  const pct = total > 0n ? Number((BigInt(part) * 1000n) / total) / 10 : 0;
  return (
    <span className="share-of">
      <span className="share-of-track" aria-hidden="true"><span style={{ width: `${Math.min(100, pct)}%` }} /></span>
      <span className="mono small">{pct.toFixed(0)}%</span>
    </span>
  );
}

function describe(order: Order): string {
  const price = order.limit_price_kobo ? `at ${formatNaira(order.limit_price_kobo)}` : "at the best price";
  const done = order.quantity - order.remaining;
  return `${order.side === "buy" ? "Buy" : "Sell"} ${shares(order.quantity)} ${order.name} ${price}${done > 0 ? ` · ${shares(done)} done` : ""}`;
}

/** The empire's shares, for a member: what they cost, what they are worth, and the gain or loss. */
function EmpireSharesPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data } = useLoad(api.empireShares, "empire-shares", onLoggedOut);
  if (!data || !data.empire) return null;
  const e = data;
  return (
    <Panel title={`${e.empire}'s shares`} aside={`${e.holdings.length} ${e.holdings.length === 1 ? "company" : "companies"}`}>
      {e.holdings.length === 0 ? (
        <p className="muted small">
          The empire owns no shares yet. Its Asset Manager buys them from the <a href="#/market">Market</a> with the empire's money.
        </p>
      ) : (
        <>
          <div className="tiles">
            <NumberTile label="Worth" value={formatCompact(e.shares_value_kobo)} />
            <NumberTile label="They cost" value={formatCompact(e.cost_kobo)} />
            <NumberTile label="Gain or loss" value={<Gain kobo={e.gain_kobo} />} />
            <NumberTile label="Dividends" value={formatCompact(e.dividends_kobo)} />
          </div>
          <div className="scroll" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col" className="num">Shares</th>
                  <th scope="col" className="num">Price</th>
                  <th scope="col" className="num">Today</th>
                  <th scope="col" className="num">Worth</th>
                  <th scope="col" className="num">They cost</th>
                  <th scope="col" className="num">Gain or loss</th>
                  <th scope="col" className="num">Dividends</th>
                  <th scope="col"><Term word="Concentration">Share of the empire's shares</Term></th>
                </tr>
              </thead>
              <tbody>
                {e.holdings.map((h) => (
                  <tr key={h.ticker}>
                    <th scope="row">
                      <a href={`#/companies/${h.ticker}`}>{h.name}</a> <span className="ticker mono">{h.ticker}</span>
                    </th>
                    <td className="num mono">{shares(h.shares)}</td>
                    <td className="num mono">{formatNaira(h.price_kobo)}</td>
                    <td className="num"><Change bps={h.change_bps} /></td>
                    <td className="num mono">{formatNaira(h.value_kobo)}</td>
                    <td className="num mono">{formatNaira(h.cost_kobo)}</td>
                    <td className="num"><Gain kobo={h.gain_kobo} /></td>
                    <td className="num mono">{formatNaira(h.dividends_kobo)}</td>
                    <td><ShareBar part={h.value_kobo} whole={e.shares_value_kobo} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="muted small">
        These shares belong to the empire, not to you, so they are not counted in what you are worth above. "They cost" is
        what the empire paid for the shares it still holds, fees included; when some are sold, the average cost of those
        shares comes off. Shares that came to the empire other than through the Market have no purchase cost on record.
      </p>
    </Panel>
  );
}

export function PortfolioWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const portfolio = useLoad(api.portfolio, "portfolio", onLoggedOut);
  const market = useLoad(api.market, "market", onLoggedOut);
  const orders = useLoad(api.myOrders, "orders", onLoggedOut);
  const [problem, setProblem] = useState<string | null>(null);
  if (portfolio.loading && !portfolio.data) return <Loading what="your portfolio" />;
  if (portfolio.error) return <Failed message={portfolio.error} onRetry={portfolio.reload} />;
  if (!portfolio.data) return null;
  const p = portfolio.data;
  const waiting = (orders.data ?? []).filter((o) => o.status === "open");
  const lastTwo = p.net_worth.length >= 1 ? p.net_worth[p.net_worth.length - 1].total_kobo : null;
  // What the player owns and the BSX 50 on the same Closing Bells, both started at 100.
  const levels = new Map((market.data?.index_history ?? []).map((d) => [d.session_date, d.level]));
  const shared = p.net_worth.filter((d) => levels.has(d.session_date) && BigInt(d.total_kobo) > 0n);
  const compare = shared.length >= 2 ? {
    you: shared.map((d) => Number(BigInt(d.total_kobo) / 100n)),
    market: shared.map((d) => levels.get(d.session_date)!),
    labels: [shortDate(shared[0].session_date), shortDate(shared[shared.length - 1].session_date)] as [string, string],
  } : null;
  const finished = (orders.data ?? []).filter((o) => o.status !== "open").slice(0, 8);

  async function cancel(id: number) {
    setProblem(null);
    try {
      await api.cancelOrder(id);
    } catch (failure) {
      setProblem(failure instanceof ApiError ? failure.message : "Could not reach the server.");
    }
    portfolio.reload();
    orders.reload();
    onChanged();
  }

  return (
    <>
      <div className="work-head">
        <div>
          <h1>Portfolio</h1>
          <div className="work-sub">
            What you own, what it cost and what it is worth now
            {p.holdings.length > 0 && <><span className="dot-sep"> · </span>{p.holdings.length} {p.holdings.length === 1 ? "company" : "companies"} · {shares(p.holdings.reduce((n, h) => n + h.shares, 0))} shares</>}
          </div>
        </div>
        {waiting.length > 0 && <a href="#/portfolio" className="muted small">{waiting.length} {waiting.length === 1 ? "order" : "orders"} waiting</a>}
      </div>

      <section className="band band-4" aria-label="What you own">
        <div className="band-cell">
          <div className="band-label"><Term word="Net worth">Everything you own</Term></div>
          <div className="band-value">{formatCompact(p.total_kobo)}</div>
          <div className="band-note">
            {lastTwo ? <><Gain kobo={(BigInt(p.total_kobo) - BigInt(lastTwo)).toString()} /> since the last Closing Bell</> : "written down at each Closing Bell"}
          </div>
        </div>
        <div className="band-cell">
          <div className="band-label">Shares</div>
          <div className="band-value">{formatCompact(p.shares_value_kobo)}</div>
          <div className="band-note">at today’s prices</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Cash you can use now</div>
          <div className="band-value">{formatCompact(p.cash_kobo)}</div>
          <div className="band-note">
            {BigInt(p.held_for_orders_kobo) > 0n ? `plus ${formatCompact(p.held_for_orders_kobo)} held for your buy orders` : "nothing held for orders"}
          </div>
        </div>
        <div className="band-cell">
          <div className="band-label">Dividends received</div>
          <div className="band-value">{formatCompact(p.dividends_kobo)}</div>
          <div className="band-note">cash paid to you by the companies you own</div>
        </div>
      </section>

      <GrantPanel onLoggedOut={onLoggedOut} onChanged={onChanged} />

      <Panel title="What you own, by kind">
        <MixBar label="What you own, by kind" parts={[
          { label: "Shares", value: Number(BigInt(p.shares_value_kobo) / 100n), color: "var(--info)", note: formatCompact(p.shares_value_kobo) },
          { label: "Bonds and bills", value: Number(BigInt(p.bonds_value_kobo) / 100n), color: "var(--build-am)", note: formatCompact(p.bonds_value_kobo) },
          ...(BigInt(p.property_kobo ?? "0") !== 0n ? [{ label: "Property, after what is owed", value: Math.max(Number(BigInt(p.property_kobo ?? "0") / 100n), 0), color: "var(--build-ib)", note: formatCompact(p.property_kobo ?? "0") }] : []),
          ...(BigInt(p.funds_kobo ?? "0") > 0n ? [{ label: "Investment funds", value: Number(BigInt(p.funds_kobo ?? "0") / 100n), color: "var(--build-rm)", note: formatCompact(p.funds_kobo ?? "0") }] : []),
          { label: "Cash", value: Number((BigInt(p.cash_kobo) + BigInt(p.held_for_orders_kobo)) / 100n), color: "var(--border-strong)", note: formatCompact((BigInt(p.cash_kobo) + BigInt(p.held_for_orders_kobo)).toString()) },
        ]} />
        <p className="muted small" style={{ marginTop: 8 }}>
          Cash you can use now: {formatNaira(p.cash_kobo)}{BigInt(p.held_for_orders_kobo) > 0n ? `, plus ${formatNaira(p.held_for_orders_kobo)} held for your buy orders` : ""}.
          {BigInt(p.held_for_offers_kobo) + BigInt(p.offered_to_bidders_kobo) > 0n && <> Held for <a href="#/market/offers">offers you have answered</a>: {formatNaira((BigInt(p.held_for_offers_kobo) + BigInt(p.offered_to_bidders_kobo)).toString())}.</>}
          {BigInt(p.funds_kobo ?? "0") > 0n && <> In <a href="#/market/funds">investment funds</a>: {formatNaira(p.funds_kobo ?? "0")}.</>}
          {BigInt(p.held_for_bids_kobo ?? "0") > 0n && <> Held for your <a href="#/property/auctions">bids at the Auction House</a>: {formatNaira(p.held_for_bids_kobo ?? "0")}.</>}
        </p>
      </Panel>

      <SavingsPanel onLoggedOut={onLoggedOut} />

      <Panel title="What you own against the BSX 50" aside={<Term word="BSX 50">both started at 100</Term>}>
        {compare
          ? <CompareChart first={compare.you} second={compare.market} names={["You", "BSX 50"]} labels={compare.labels} />
          : <p className="muted small">This chart appears after two Closing Bells (22:00 Lagos time): what you own and the BSX 50, both started at 100, so you can see which grew faster.</p>}
        {compare && <p className="muted small" style={{ marginTop: 6 }}>What you own includes salary, rewards and grants paid in, not only what your investments earned. To judge your investing alone, look at the gain or loss on each share below.</p>}
        {p.net_worth.length >= 2 && (
          <details style={{ marginTop: 10 }}>
            <summary className="small" style={{ cursor: "pointer", color: "var(--gold)" }}>What you own, in naira, day by day</summary>
            <SingleLine name="What you are worth" format={(v) => formatCompact((BigInt(Math.round(v)) * 100n).toString())}
                        data={p.net_worth.map((d) => ({ label: shortDate(d.session_date), value: Number(BigInt(d.total_kobo) / 100n) }))} />
          </details>
        )}
      </Panel>

      <Panel title="Your shares" aside={p.holdings.length > 0 ? <><Term word="Concentration">Share of your shares</Term> shown beside each company</> : undefined}>
        {p.holdings.length === 0 ? (
          <p className="muted">
            You own no shares yet. Open the <a href="#/market">Market</a>, pick a company and place a buy order.
          </p>
        ) : (
          <div className="scroll scroll-sticky" tabIndex={0}>
            <table className="dense tape-table">
              <thead>
                <tr>
                  <th scope="col" className="sr-only">Code</th>
                  <th scope="col">Company</th>
                  <th scope="col" className="num">Shares</th>
                  <th scope="col" className="num">Price</th>
                  <th scope="col" className="num">Today</th>
                  <th scope="col" className="num">Worth</th>
                  <th scope="col" className="num">They cost you</th>
                  <th scope="col" className="num">Gain or loss</th>
                  <th scope="col" className="num">Dividends</th>
                  <th scope="col" className="num"><Term word="Concentration">Share of your shares</Term></th>
                </tr>
              </thead>
              <tbody>
                {p.holdings.map((h) => (
                  <tr key={h.ticker}>
                    <td className="mono strong"><a href={`#/companies/${h.ticker}`}>{h.ticker}</a></td>
                    <th scope="row">
                      {h.name}
                      {h.held_for_orders > 0 && <div className="small muted">{shares(h.held_for_orders)} held for your sell orders</div>}
                    </th>
                    <td className="num mono">{shares(h.shares)}</td>
                    <td className="num mono">{formatNaira(h.price_kobo)}</td>
                    <td className="num"><Change bps={h.change_bps} /></td>
                    <td className="num mono">{formatNaira(h.value_kobo)}</td>
                    <td className="num mono">{formatNaira(h.cost_kobo)}</td>
                    <td className="num"><Gain kobo={h.gain_kobo} /></td>
                    <td className="num mono">{formatNaira(h.dividends_kobo)}</td>
                    <td className="num"><ShareBar part={h.value_kobo} whole={p.shares_value_kobo} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          “They cost you” is what you paid for the shares you still hold, fees included. When you sell some, the average
          cost of those shares comes off. Inside the market’s trading hours, a figure can change before you finish reading it.
        </p>
      </Panel>

      <EmpireSharesPanel onLoggedOut={onLoggedOut} />

      <Panel title="Your orders waiting" aside={waiting.length > 0 ? `${waiting.length} of 50` : undefined}>
        {problem && <div className="error" role="alert">{problem}</div>}
        {waiting.length === 0 && <p className="muted small">No orders are waiting.</p>}
        {waiting.map((order) => (
          <div key={order.id} className="order-line">
            <span>
              <a href={`#/companies/${order.ticker}`}>{describe(order)}</a>
              {BigInt(order.held_kobo) > 0n && <span className="muted small"> · {formatCompact(order.held_kobo)} held</span>}
            </span>
            <button className="button-quiet" onClick={() => cancel(order.id)}>Cancel</button>
          </div>
        ))}
        {finished.length > 0 && (
          <>
            <div className="why-title" style={{ marginTop: 14 }}>Your latest finished orders</div>
            {finished.map((order) => (
              <div key={order.id} className="order-line">
                <span>{describe(order)}</span>
                <span className="muted small">
                  {order.status === "filled" ? `Done for ${formatNaira(order.value_traded_kobo)}` : order.status === "expired" ? "Handed back after 7 days" : "Cancelled"}
                </span>
              </div>
            ))}
          </>
        )}
      </Panel>
    </>
  );
}

export function PortfolioRail({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data } = useLoad(api.portfolio, "portfolio", onLoggedOut);
  return (
    <>
      <WhatCouldHappenPanel what="portfolio" title="What could happen to what you own?" onLoggedOut={onLoggedOut} />
      {data && data.advice.length > 0 && (
        <Panel title="Your money, in plain words" aside="Observations, never tips">
          <ul className="reasons advice">{data.advice.map((line) => <li key={line}>{line}</li>)}</ul>
        </Panel>
      )}
      <Panel>
        <details>
          <summary className="strong" style={{ cursor: "pointer" }}>? Reading this page</summary>
          <ul className="reasons" style={{ marginTop: 10 }}>
            <li>A share is worth its latest price on the exchange. That can change every minute the market is open.</li>
            <li>A gain or loss on shares you still hold is only on paper until you sell.</li>
            <li>Companies that make a profit usually pay part of it to their owners each quarter. That is a dividend, and it arrives as cash.</li>
            <li>Cash held for a buy order comes back in full if you cancel the order.</li>
            <li>What you own is written down each day when the Closing Bell rings, and charted from those figures.</li>
          </ul>
        </details>
      </Panel>
    </>
  );
}
