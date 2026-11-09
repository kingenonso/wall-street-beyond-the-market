import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Holding, type Order, type Quote } from "./api";
import { formatNaira, MARKET_LABEL } from "./format";
import { useLoad } from "./hooks";
import { DepthBars } from "./Charts";
import { Change, Panel } from "./Shell";
import { Term } from "./Term";
import { play } from "./sound";

const shares = (count: number) => count.toLocaleString("en-NG");

/** "20.50" typed by a player, as whole kobo. Null if it is not a price. */
export function toKobo(text: string): number | null {
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(text.trim())) return null;
  const [naira, kobo = ""] = text.trim().split(".");
  const value = Number(naira) * 100 + Number(kobo.padEnd(2, "0"));
  return value > 0 ? value : null;
}

export function Book({ quote }: { quote: Quote }) {
  const rows = Math.max(quote.bids.length, quote.offers.length, 1);
  return (
    <div className="scroll" tabIndex={0}>
      <table className="book">
        <thead>
          <tr>
            <th scope="col" className="num">Buyers want</th>
            <th scope="col" className="num">at</th>
            <th scope="col" className="num">Sellers ask</th>
            <th scope="col" className="num">for</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, i) => (
            <tr key={i}>
              <td className="num mono">{quote.bids[i] ? shares(quote.bids[i].quantity) : ""}</td>
              <td className="num mono change-up">{quote.bids[i] ? formatNaira(quote.bids[i].price_kobo) : ""}</td>
              <td className="num mono change-down">{quote.offers[i] ? formatNaira(quote.offers[i].price_kobo) : ""}</td>
              <td className="num mono">{quote.offers[i] ? shares(quote.offers[i].quantity) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {quote.bids.length === 0 && quote.offers.length === 0 && (
        <p className="muted small">Nobody is waiting to buy or sell this share right now.</p>
      )}
    </div>
  );
}

function describe(order: Pick<Order, "side" | "quantity" | "remaining" | "limit_price_kobo">): string {
  const what = `${order.side === "buy" ? "Buy" : "Sell"} ${shares(order.quantity)}`;
  const price = order.limit_price_kobo ? `at ${formatNaira(order.limit_price_kobo)}` : "at the best price";
  const done = order.quantity - order.remaining;
  return done > 0 && order.remaining > 0 ? `${what} ${price} · ${shares(done)} done` : `${what} ${price}`;
}

/** Buy or sell one company's shares, and see your own orders in it. */
export function TradePanel({ ticker, onLoggedOut, onTraded, layout = "wide" }: {
  ticker: string;
  onLoggedOut: () => void;
  onTraded: () => void;
  /** "rail": one narrow column beside a company's page, with the waiting orders as bars. */
  layout?: "wide" | "rail";
}) {
  const rail = layout === "rail";
  const quote = useLoad(() => api.quote(ticker), `quote:${ticker}`, onLoggedOut);
  const why = useLoad(() => api.why(ticker), `why:${ticker}`, onLoggedOut);
  const orders = useLoad(api.myOrders, "orders", onLoggedOut);
  const holdings = useLoad(api.myHoldings, "holdings", onLoggedOut);
  const empire = useLoad(api.empires, "trade-panel-empire", onLoggedOut);
  // An empire's Asset Manager, or its head, may trade here with the empire's money as well as their own.
  const room = empire.data?.room && empire.data.room.status === "active" && empire.data.room.can_trade ? empire.data.room : null;
  const [forEmpire, setForEmpire] = useState(false);
  const empireMode = forEmpire && room !== null;
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [kind, setKind] = useState<"limit" | "market">("limit");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  // The switch was set to the empire but the empire cannot be traded for right now (a failed read, or the
  // seat lost its trading): nothing is sent with the player's own money by mistake.
  const empireLost = forEmpire && room === null && !empire.loading;
  // An empire the computer runs deals only at a price the trader names.
  useEffect(() => {
    if (empireMode && room?.fair_dealing && kind === "market") setKind("limit");
  }, [empireMode, room?.fair_dealing, kind]);

  if (!quote.data) return null;
  const q = quote.data;
  const open = q.market_state === "open";
  const holding: Holding | undefined = holdings.data?.find((h) => h.ticker === ticker);
  const empireHeld = room?.holdings.find((h) => h.ticker === ticker)?.shares ?? 0;
  const mine = empireMode
    ? (room?.orders ?? []).filter((o) => o.ticker === ticker && o.status === "open").map((o) => ({ ...o, limit_price_kobo: o.limit_price_kobo ?? null }))
    : (orders.data ?? []).filter((o) => o.ticker === ticker && o.status === "open");
  const count = /^\d{1,11}$/.test(quantity) ? Number(quantity) : 0;
  const chosen = kind === "limit" ? toKobo(price) : Number(side === "buy" ? q.highest_today_kobo : q.lowest_today_kobo);
  const value = count > 0 && chosen ? count * chosen : null;
  const fee = value ? Math.ceil((value * q.fee_bps) / 10000) : null;

  function refresh() {
    quote.reload();
    why.reload();
    orders.reload();
    holdings.reload();
    empire.reload();
    onTraded();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setDone(null);
    if (count <= 0) return setProblem("Enter how many shares, as a whole number.");
    const limit = kind === "limit" ? toKobo(price) : null;
    if (kind === "limit" && limit === null) return setProblem("Enter your price in naira, for example 20.50.");
    if (forEmpire && !empireMode) return setProblem("Trading for your empire is not available right now. Choose Me to trade with your own money.");
    setBusy(true);
    if (empireMode) {
      try {
        const view = await api.placeEmpireOrder({ ticker, side, kind, quantity: count, ...(limit !== null ? { limit_price_kobo: limit } : {}) });
        setDone(view.notice ?? `Sent for ${room?.name}: the order is placed with the empire's money, and what it buys belongs to the empire.`);
        setQuantity("");
        refresh();
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 401) return onLoggedOut();
        setProblem(failure instanceof ApiError ? failure.message : "Could not reach the server.");
      } finally {
        setBusy(false);
      }
      return;
    }
    try {
      const result = await api.placeOrder({
        ticker, side, kind, quantity: count, ...(limit !== null ? { limit_price_kobo: limit } : {}),
      });
      const traded = result.trades.reduce((sum, trade) => sum + trade.quantity, 0);
      if (traded > 0) play("trade");
      const verb = side === "buy" ? "bought" : "sold";
      if (result.order.status === "filled") setDone(`Done: you ${verb} ${shares(traded)} shares.`);
      else if (result.order.status === "open" && traded > 0)
        setDone(`You ${verb} ${shares(traded)} shares. The other ${shares(result.order.remaining)} are waiting for a match.`);
      else if (result.order.status === "open")
        setDone(open ? "Your order is waiting for a match." : "Your order is waiting for the market to open.");
      else setDone(`${traded > 0 ? `You ${verb} ${shares(traded)} shares. ` : ""}${result.order.closed_reason ?? ""}`);
      setQuantity("");
      refresh();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) return onLoggedOut();
      setProblem(failure instanceof ApiError ? failure.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(id: number) {
    setProblem(null);
    try {
      await (empireMode ? api.cancelEmpireOrder(id) : api.cancelOrder(id));
      setDone("Order cancelled. What the exchange was holding for it has been handed back.");
    } catch (failure) {
      setProblem(failure instanceof ApiError ? failure.message : "Could not reach the server.");
    }
    refresh();
  }

  return (
    <Panel title="Trade this share" aside={`Broad Street Exchange · ${MARKET_LABEL[q.market_state]}`}>
      {room && (
        <div className="trade-for-block">
          <div className="lbl" id={`trade-for-${ticker}`}>Trade for</div>
          <div className="seg" role="group" aria-labelledby={`trade-for-${ticker}`}>
            <button type="button" aria-pressed={!forEmpire} onClick={() => setForEmpire(false)}>Me</button>
            <button type="button" aria-pressed={forEmpire} onClick={() => setForEmpire(true)}>My empire{rail ? "" : `: ${room.name}`}</button>
          </div>
        </div>
      )}
      {empireLost && (
        <p className="small notice-line" role="alert">
          ○ Trading for your empire is not available right now.{" "}
          <button type="button" className="link-button" onClick={() => setForEmpire(false)}>Trade for me instead</button>
        </p>
      )}
      {empireMode && room && (
        <p className="small notice-line">
          ◆ The empire's money: {formatNaira(room.cash_kobo)} in cash.{" "}
          {room.is_head ? "As head you trade without a limit." : `Your limit this quarter is ${formatNaira(room.trade_limit_kobo)}, of which ${formatNaira(room.trade_used_kobo)} is used.`}
          {room.fair_dealing && " An empire the computer runs deals only at a price you name, within 2% of the last session's price."}
          {" "}What you buy belongs to the empire, not to you.
        </p>
      )}
      <div className={rail ? "tiles tiles-rail" : "tiles"}>
        {!rail && <div className="tile">
          <div className="muted small">{q.last_price_kobo ? "Last price" : "Listing price (not yet traded)"}</div>
          <div className="mono figure-small">{formatNaira(q.last_price_kobo ?? q.reference_price_kobo)}</div>
          <div className="small muted">a share</div>
        </div>}
        {!rail && <div className="tile">
          <div className="muted small">Today it can trade between</div>
          <div className="mono figure-small">{formatNaira(q.lowest_today_kobo)} – {formatNaira(q.highest_today_kobo)}</div>
          <div className="small muted">a tenth either side of yesterday's last price</div>
        </div>}
        <div className="tile">
          <div className="muted small">{empireMode ? "The empire owns" : "You own"}</div>
          <div className="mono figure-small">{shares(empireMode ? empireHeld : (holding?.shares ?? 0) + (holding?.held_for_orders ?? 0))}</div>
          <div className="small muted">
            {!empireMode && holding && holding.held_for_orders > 0 ? `${shares(holding.held_for_orders)} held for your sell orders` : "shares"}
          </div>
        </div>
      </div>

      <div className={rail ? "trade-rail" : "trade-grid"}>
        <form className="trade-form" onSubmit={submit}>
          <div className="seg" role="group" aria-label="Buy or sell" style={{ marginBottom: 10 }}>
            <button type="button" className="seg-buy" aria-pressed={side === "buy"} onClick={() => setSide("buy")}>▲ Buy</button>
            <button type="button" className="seg-sell" aria-pressed={side === "sell"} onClick={() => setSide("sell")}>▼ Sell</button>
          </div>
          <div className="choice" role="group" aria-label="Price">
            <button type="button" aria-pressed={kind === "limit"} onClick={() => setKind("limit")}>At my price</button>
            <button type="button" aria-pressed={kind === "market"} disabled={!open || (empireMode && room?.fair_dealing)} onClick={() => setKind("market")}>
              At the best price now
            </button>
          </div>
          <div className="row-inputs">
            <label>
              <span className="field-label">How many shares</span>
              <input inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="100" />
            </label>
            {kind === "limit" && (
              <label>
                <span className="field-label">Your price, in naira</span>
                <input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)}
                       placeholder={(Number(q.last_price_kobo ?? q.reference_price_kobo) / 100).toFixed(2)} />
              </label>
            )}
          </div>
          {value && fee !== null && (
            <p className="small muted">
              {side === "buy"
                ? `${kind === "market" ? "At most " : ""}${formatNaira(String(value + fee))} will be held: ${formatNaira(String(value))} for the shares and ${formatNaira(String(fee))} in fees. Anything not used is handed back.`
                : `${kind === "market" ? "At least " : ""}${formatNaira(String(value - fee))} if it all sells: ${formatNaira(String(value))} less ${formatNaira(String(fee))} in fees.`}
            </p>
          )}
          {problem && <div className="error" role="alert">{problem}</div>}
          {done && <div className="notice" role="status">{done}</div>}
          <button className="button-primary" type="submit" disabled={busy || empireLost}>
            {busy ? "Sending…" : `${side === "buy" ? "Place buy order" : "Place sell order"}${empireMode ? " for the empire" : ""}`}
          </button>
          <p className="small muted">
            {open
              ? "The market is open: your order is matched at once if somebody is waiting at your price, and waits if not."
              : "The market is closed. Your order will wait and take part in the opening auction at 12:00 Lagos time."}
            {" "}Buyer and seller each pay {(q.fee_bps / 100).toFixed(1)}% in fees.
          </p>
        </form>

        <div>
          <div className="why-title">Who is waiting <Term word="Order book"><span className="sr-only">the order book</span></Term></div>
          {rail
            ? <DepthBars format={formatNaira}
                         sellers={q.offers.slice(0, 5).map((l) => ({ price: l.price_kobo, quantity: l.quantity }))}
                         buyers={q.bids.slice(0, 5).map((l) => ({ price: l.price_kobo, quantity: l.quantity }))} />
            : <Book quote={q} />}
          {!open && (q.bids.length > 0 || q.offers.length > 0) && (
            <p className="muted small">
              These orders are waiting for the opening auction. Until then a buyer's price may be above a seller's:
              the auction pairs them at one price when the market opens.
            </p>
          )}
          {mine.length > 0 && (
            <>
              <div className="why-title">{empireMode ? "The empire’s orders waiting" : "Your orders waiting"}</div>
              {mine.map((order) => (
                <div key={order.id} className="order-line">
                  <span>{describe(order)}</span>
                  <button className="button-quiet" onClick={() => cancel(order.id)}>Cancel</button>
                </div>
              ))}
            </>
          )}
          {q.trades.length > 0 && (
            <>
              <div className="why-title">Latest trades</div>
              {q.trades.slice(0, 5).map((trade, index) => (
                <div key={index} className="row">
                  <span className="mono">{shares(trade.quantity)} at {formatNaira(trade.price_kobo)}</span>
                  <span className="muted small">{trade.in_auction ? "opening auction" : new Date(trade.traded_at).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" })}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {why.data && !rail && (
        <div className="why-box">
          <div className="why-title">Why is the price where it is?</div>
          <p className="small">
            {why.data.move_bps !== 0 && <><Change bps={why.data.move_bps} />{" "}</>}
            {why.data.summary}
          </p>
          {why.data.reasons.length > 0 && (
            <ul className="reasons">{why.data.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
          )}
          {why.data.valuation_reasons.length > 0 && (
            <>
              <p className="small muted">What changed investors' view of its worth at its {why.data.valuation_label} results:</p>
              <ul className="reasons">{why.data.valuation_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </Panel>
  );
}
