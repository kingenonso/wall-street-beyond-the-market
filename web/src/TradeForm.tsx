// The trading form used when a player deals with somebody else's money: an empire's, or a
// pension fund's. The company is chosen by name, never typed as a code. The form shows the price,
// the range the share may trade in today, who is waiting to buy and sell, and works out the cost
// and the exchange's fee before anything is sent.

import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Bond, type Quote } from "./api";
import { asKobo } from "./Empire";
import { formatNaira, MARKET_LABEL } from "./format";
import { useLoad } from "./hooks";
import { Change } from "./Shell";
import { Book } from "./Trade";

type Side = "buy" | "sell";
const count = (text: string) => (/^\d{1,11}$/.test(text) ? Number(text) : 0);
const whole = (n: number) => n.toLocaleString("en-NG");

function SideChoice({ side, onChange }: { side: Side; onChange: (side: Side) => void }) {
  return (
    <div className="choice" role="group" aria-label="Buy or sell">
      <button type="button" aria-pressed={side === "buy"} onClick={() => onChange("buy")}>Buy</button>
      <button type="button" aria-pressed={side === "sell"} onClick={() => onChange("sell")}>Sell</button>
    </div>
  );
}

/** The sum, line by line: what the shares or bonds come to, the fee, and the total. */
function Sum({ lines, total, totalLabel, note }: { lines: [string, string][]; total: string; totalLabel: string; note: ReactNode }) {
  return (
    <div className="sum" aria-live="polite">
      <div className="why-title">THE SUM</div>
      {lines.map(([label, value]) => <div key={label} className="row"><span>{label}</span><span className="mono">{value}</span></div>)}
      <div className="row sum-total"><span className="strong">{totalLabel}</span><span className="mono strong">{total}</span></div>
      <p className="muted small">{note}</p>
    </div>
  );
}

export function ShareOrderForm({ whose, busy, held, fairDealing, onPlace, onLoggedOut }: {
  whose: string; busy: boolean; held: { ticker: string; shares: number }[]; fairDealing: boolean; onLoggedOut: () => void;
  onPlace: (order: { ticker: string; side: Side; quantity: number; limit_price_kobo: number }) => Promise<boolean>;
}) {
  const market = useLoad(api.market, "trade-form-market", onLoggedOut);
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<Side>("buy");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const quote = useLoad<Quote | null>(() => (ticker ? api.quote(ticker) : Promise.resolve(null)), `trade-form-quote:${ticker}`, onLoggedOut);
  const shares = [...(market.data?.shares ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const chosen = shares.find((s) => s.ticker === ticker);
  const q = ticker && quote.data && quote.data.ticker === ticker ? quote.data : null;
  const n = count(quantity);
  const priceKobo = asKobo(price);
  const low = q ? Number(q.lowest_today_kobo) : 0, high = q ? Number(q.highest_today_kobo) : 0;
  const outside = q !== null && priceKobo !== null && (priceKobo < low || priceKobo > high);
  // Other people's money is dealt close to the market: a buy at most 2% above the last session's price, a sell at most 2% below.
  const reference = q ? Number(q.reference_price_kobo) : 0;
  const most = Math.floor(reference * 1.02), least = Math.ceil(reference * 0.98);
  const unfair = fairDealing && q !== null && priceKobo !== null && (side === "buy" ? priceKobo > most : priceKobo < least);
  const value = n > 0 && priceKobo !== null ? n * priceKobo : null;
  const fee = value !== null && q ? Math.ceil((value * q.fee_bps) / 10000) : null;
  const own = held.find((h) => h.ticker === ticker)?.shares ?? 0;

  function choose(code: string) {
    setTicker(code);
    const share = shares.find((s) => s.ticker === code);
    setPrice(share ? (Number(share.price_kobo) / 100).toFixed(2) : "");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ticker || n <= 0 || priceKobo === null || outside || unfair) return;
    void onPlace({ ticker, side, quantity: n, limit_price_kobo: priceKobo }).then((ok) => { if (ok) { setQuantity(""); quote.reload(); } });
  }

  return (
    <div className="trade-grid">
      <form className="trade-form" onSubmit={submit}>
        <label>
          <span className="field-label">Company</span>
          <select value={ticker} onChange={(event) => choose(event.target.value)}>
            <option value="">Choose a company…</option>
            {shares.map((s) => <option key={s.ticker} value={s.ticker}>{s.name} ({s.ticker}) · {formatNaira(s.price_kobo)}</option>)}
          </select>
        </label>
        {chosen && q && (
          <div className="tiles">
            <div className="tile">
              <div className="muted small">{q.last_price_kobo ? "Last price" : "Listing price (not yet traded)"}</div>
              <div className="mono figure-small">{formatNaira(q.last_price_kobo ?? q.reference_price_kobo)}</div>
              <div className="small"><Change bps={chosen.change_bps} /> today</div>
            </div>
            <div className="tile">
              <div className="muted small">Today it can trade between</div>
              <div className="mono figure-small">{formatNaira(q.lowest_today_kobo)} – {formatNaira(q.highest_today_kobo)}</div>
              <div className="small muted">a tenth either side of yesterday's last price</div>
            </div>
            <div className="tile">
              <div className="muted small">{whose} holds</div>
              <div className="mono figure-small">{whole(own)}</div>
              <div className="small muted">{chosen.ticker} shares · <a href={`#/companies/${chosen.ticker}`}>company page</a></div>
            </div>
          </div>
        )}
        <SideChoice side={side} onChange={setSide} />
        <div className="row-inputs">
          <label>
            <span className="field-label">How many shares</span>
            <input inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value.replace(/\D/g, ""))} placeholder="100" />
          </label>
          <label>
            <span className="field-label">Price for each share, in naira</span>
            <input inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="20.50" />
          </label>
        </div>
        {outside && <p className="small change-down">▼ That price is outside today's range. The exchange would refuse the order.</p>}
        {fairDealing && q && (
          <p className={unfair ? "small change-down" : "small muted"}>
            {unfair ? "▼ " : ""}{whose} is other people's money, so it deals close to the market: it may pay up to {formatNaira(String(most))} a
            share to buy, and accept down to {formatNaira(String(least))} to sell (2% either side of the last session's price).
          </p>
        )}
        {value !== null && fee !== null && q && (
          <Sum
            lines={[[`${whole(n)} shares at ${formatNaira(String(priceKobo))}`, formatNaira(String(value))],
                    [`Fees (${(q.fee_bps / 100).toFixed(2)}%): the exchange's fee and stamp duty`, formatNaira(String(fee))],
                    ["Tax on any gain", "₦0.00"]]}
            totalLabel={side === "buy" ? `${whose} pays, at most` : `${whose} receives, at least, if it all sells`}
            total={formatNaira(String(side === "buy" ? value + fee : value - fee))}
            note={<>Buyer and seller each pay 0.50% of the value: 0.30% to the exchange and 0.20% stamp duty to the Government. In the
              Closing Rush (the last ten minutes of the trading day) the fees are halved, so the sum above is the most it can come to.
              No tax is charged on a gain from trading yet: that arrives with the Government stage.</>} />
        )}
        <button className="button-primary" type="submit" disabled={busy || !ticker || n <= 0 || priceKobo === null || outside || unfair}>
          {side === "buy" ? "Place the buy order" : "Place the sell order"}
        </button>
        {q && <p className="small muted">Broad Street Exchange · {MARKET_LABEL[q.market_state]}. An order at your price is matched at once if somebody is waiting at it, and waits if not.</p>}
      </form>
      <div>
        <div className="why-title">WHO IS WAITING TO BUY AND SELL{chosen ? ` · ${chosen.ticker}` : ""}</div>
        {q ? <Book quote={q} /> : <p className="muted small">Choose a company to see its price, today's range, and the buyers and sellers waiting.</p>}
      </div>
    </div>
  );
}

export function BondOrderForm({ whose, busy, held, onPlace, onLoggedOut }: {
  whose: string; busy: boolean; held: { code: string; units: number }[]; onLoggedOut: () => void;
  onPlace: (order: { code: string; side: Side; units: number }) => Promise<boolean>;
}) {
  const desk = useLoad(api.bonds, "trade-form-bonds", onLoggedOut);
  const [code, setCode] = useState("");
  const [side, setSide] = useState<Side>("buy");
  const [units, setUnits] = useState("");
  const bonds: Bond[] = [...(desk.data?.bonds ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const bond = bonds.find((b) => b.code === code);
  const n = count(units);
  const each = bond ? Number(side === "buy" ? bond.ask_kobo : bond.bid_kobo) : 0;
  const own = held.find((h) => h.code === code)?.units ?? 0;
  const closed = desk.data !== null && !desk.data.desk_open;
  return (
    <form className="trade-form" onSubmit={(event) => {
      event.preventDefault();
      if (bond && n > 0 && !closed) void onPlace({ code, side, units: n }).then((ok) => { if (ok) { setUnits(""); desk.reload(); } });
    }}>
      <label>
        <span className="field-label">Bond or bill</span>
        <select value={code} onChange={(event) => setCode(event.target.value)}>
          <option value="">Choose a bond or bill…</option>
          {bonds.map((b) => <option key={b.code} value={b.code}>{b.name} · returns {(b.yield_bps / 100).toFixed(2)}% a year · ends {b.maturity_label}</option>)}
        </select>
      </label>
      {bond && (
        <div className="tiles">
          <div className="tile"><div className="muted small">To buy one</div><div className="mono figure-small">{formatNaira(bond.ask_kobo)}</div><div className="small muted">the desk's selling price</div></div>
          <div className="tile"><div className="muted small">To sell one</div><div className="mono figure-small">{formatNaira(bond.bid_kobo)}</div><div className="small muted">the desk's buying price</div></div>
          <div className="tile"><div className="muted small">{whose} holds</div><div className="mono figure-small">{whole(own)}</div><div className="small muted">{bond.kind_label} · {bond.issuer}{bond.rating ? ` · rated ${bond.rating}` : ""}</div></div>
        </div>
      )}
      <SideChoice side={side} onChange={setSide} />
      <div className="row-inputs">
        <label>
          <span className="field-label">How many</span>
          <input inputMode="numeric" value={units} onChange={(event) => setUnits(event.target.value.replace(/\D/g, ""))} placeholder="10" />
        </label>
      </div>
      {bond && n > 0 && (
        <Sum
          lines={[[`${whole(n)} at ${formatNaira(String(each))}`, formatNaira(String(n * each))], ["Fee", "₦0.00"], ["Tax on any gain", "₦0.00"]]}
          totalLabel={side === "buy" ? `${whose} pays` : `${whose} receives`} total={formatNaira(String(n * each))}
          note={<>Bonds and bills are dealt with the bond desk, not on the exchange. It charges no fee: its reward is the gap between
            its buying and its selling price. No tax is charged on a gain from trading yet.</>} />
      )}
      {closed && <p className="small change-down">▼ The bond desk is closed now. It deals while the market is open: 12:00 to 22:00, Lagos time.</p>}
      <button className="button-primary" type="submit" disabled={busy || closed || !bond || n <= 0}>
        {closed ? "The bond desk is closed" : `${side === "buy" ? "Buy" : "Sell"} for ${whose.toLowerCase()}`}
      </button>
    </form>
  );
}
