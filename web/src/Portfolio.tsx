import { useState } from "react";
import { api, ApiError, type Order } from "./api";
import { formatCompact, formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel } from "./Shell";
import { shortDate } from "./Market";
import { SingleLine } from "./TrendChart";

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

/** A gain or a loss in naira, with an arrow so that it reads without colour. */
function Gain({ kobo }: { kobo: string }) {
  const value = BigInt(kobo);
  if (value === 0n) return <span className="mono muted">₦0</span>;
  const up = value > 0n;
  return <span className={`mono change-${up ? "up" : "down"}`}>{up ? "▲" : "▼"} {formatNaira((up ? value : -value).toString())}</span>;
}

function describe(order: Order): string {
  const price = order.limit_price_kobo ? `at ${formatNaira(order.limit_price_kobo)}` : "at the best price";
  const done = order.quantity - order.remaining;
  return `${order.side === "buy" ? "Buy" : "Sell"} ${shares(order.quantity)} ${order.name} ${price}${done > 0 ? ` · ${shares(done)} done` : ""}`;
}

export function PortfolioWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const portfolio = useLoad(api.portfolio, "portfolio", onLoggedOut);
  const orders = useLoad(api.myOrders, "orders", onLoggedOut);
  const [problem, setProblem] = useState<string | null>(null);
  if (portfolio.loading && !portfolio.data) return <Loading what="your portfolio" />;
  if (portfolio.error) return <Failed message={portfolio.error} onRetry={portfolio.reload} />;
  if (!portfolio.data) return null;
  const p = portfolio.data;
  const waiting = (orders.data ?? []).filter((o) => o.status === "open");
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
        <h1>Your portfolio</h1>
        <span className="muted small">What you own, what it cost and what it is worth now</span>
      </div>

      <GrantPanel onLoggedOut={onLoggedOut} onChanged={onChanged} />

      <Panel title="Your advisory summary" aside="A reading of how your money is placed. Observations, never tips">
        <ul className="reasons advice">{p.advice.map((line) => <li key={line}>{line}</li>)}</ul>
      </Panel>

      <Panel title="What you are worth">
        {p.net_worth.length >= 2 ? (
          <SingleLine name="What you are worth" format={(v) => formatCompact((BigInt(Math.round(v)) * 100n).toString())}
                      data={p.net_worth.map((d) => ({ label: shortDate(d.session_date), value: Number(BigInt(d.total_kobo) / 100n) }))} />
        ) : (
          <p className="muted small">A chart of what you are worth appears here after your first Closing Bell (22:00 Lagos time).</p>
        )}
        <div className="tiles">
          <div className="tile">
            <div className="muted small">In all</div>
            <div className="mono figure-small">{formatNaira(p.total_kobo)}</div>
            <div className="small muted">cash, shares and bonds together</div>
          </div>
          <div className="tile">
            <div className="muted small">Cash you can use</div>
            <div className="mono figure-small">{formatNaira(p.cash_kobo)}</div>
            <div className="small muted">
              {BigInt(p.held_for_orders_kobo) > 0n ? `plus ${formatNaira(p.held_for_orders_kobo)} held for your buy orders` : "none held for orders"}
            </div>
          </div>
          <div className="tile">
            <div className="muted small">Your shares</div>
            <div className="mono figure-small">{formatNaira(p.shares_value_kobo)}</div>
            <div className="small muted">at today's prices</div>
          </div>
          <div className="tile">
            <div className="muted small">Your bonds and bills</div>
            <div className="mono figure-small">{formatNaira(p.bonds_value_kobo)}</div>
            <div className="small muted"><a href="#/market/bonds">at their fair value</a></div>
          </div>
          <div className="tile">
            <div className="muted small">Dividends received</div>
            <div className="mono figure-small">{formatNaira(p.dividends_kobo)}</div>
            <div className="small muted">since you began</div>
          </div>
        </div>
        {BigInt(p.held_for_offers_kobo) + BigInt(p.offered_to_bidders_kobo) > 0n && (
          <p className="small">
            Held by the exchange for <a href="#/market/offers">offers you have answered</a>:{" "}
            {BigInt(p.held_for_offers_kobo) > 0n && <>{formatNaira(p.held_for_offers_kobo)} in cash for new shares. </>}
            {BigInt(p.offered_to_bidders_kobo) > 0n && <>{formatNaira(p.offered_to_bidders_kobo)} of shares offered to a bidder.</>}
          </p>
        )}
        {BigInt(p.realised_kobo) !== 0n && (
          <p className="small">On shares you have already sold, after fees: <Gain kobo={p.realised_kobo} /></p>
        )}
      </Panel>

      <Panel title="Your shares">
        {p.holdings.length === 0 ? (
          <p className="muted">
            You own no shares yet. Open the <a href="#/market">Market</a>, pick a company and place a buy order.
          </p>
        ) : (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col" className="num">Shares</th>
                  <th scope="col" className="num">Price</th>
                  <th scope="col" className="num">Today</th>
                  <th scope="col" className="num">Worth</th>
                  <th scope="col" className="num">They cost you</th>
                  <th scope="col" className="num">Gain or loss</th>
                  <th scope="col" className="num">Dividends</th>
                </tr>
              </thead>
              <tbody>
                {p.holdings.map((h) => (
                  <tr key={h.ticker}>
                    <th scope="row">
                      <a href={`#/companies/${h.ticker}`}>{h.name}</a> <span className="ticker mono">{h.ticker}</span>
                      {h.held_for_orders > 0 && <div className="small muted">{shares(h.held_for_orders)} held for your sell orders</div>}
                    </th>
                    <td className="num mono">{shares(h.shares)}</td>
                    <td className="num mono">{formatNaira(h.price_kobo)}</td>
                    <td className="num"><Change bps={h.change_bps} /></td>
                    <td className="num mono">{formatNaira(h.value_kobo)}</td>
                    <td className="num mono">{formatNaira(h.cost_kobo)}</td>
                    <td className="num"><Gain kobo={h.gain_kobo} /></td>
                    <td className="num mono">{formatNaira(h.dividends_kobo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          "They cost you" is what you paid for the shares you still hold, fees included. When you sell some, the average
          cost of those shares comes off.
        </p>
      </Panel>

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
            <div className="why-title" style={{ marginTop: 14 }}>YOUR LATEST FINISHED ORDERS</div>
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

export function PortfolioRail() {
  return (
    <Panel title="Reading this page">
      <ul className="reasons">
        <li>A share is worth its latest price on the exchange. That can change every minute the market is open.</li>
        <li>A gain or loss on shares you still hold is only on paper until you sell.</li>
        <li>Companies that make a profit usually pay part of it to their owners each quarter. That is a dividend, and it arrives as cash.</li>
        <li>Cash held for a buy order comes back in full if you cancel the order.</li>
        <li>The advisory summary points at what a careful investor would look at. It never tells you what to buy or sell.</li>
        <li>What you are worth is written down each day when the Closing Bell rings, and charted from those figures.</li>
      </ul>
    </Panel>
  );
}
