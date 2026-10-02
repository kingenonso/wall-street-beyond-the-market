import { useState, type FormEvent } from "react";
import { api, ApiError, type Analysis } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { shortDate } from "./Market";
import { Panel } from "./Shell";
import { SingleLine } from "./TrendChart";

const count = (n: number) => n.toLocaleString("en-NG");
const times = (ratio: number | null) => (ratio === null ? "n/a" : `${ratio.toFixed(1)}×`);

function toKobo(text: string): number | null {
  if (text.trim() === "") return null;
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(text.trim())) return NaN;
  const [naira, kobo = ""] = text.trim().split(".");
  return Number(naira) * 100 + Number(kobo.padEnd(2, "0"));
}

function Measure({ label, value, meaning }: { label: string; value: string; meaning: string }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="mono figure-small">{value}</div>
      <div className="small muted">{meaning}</div>
    </div>
  );
}

/** Watch this company, with optional prices to be told at. */
function Watch({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const mine = watched.data?.find((w) => w.ticker === ticker);
  const [above, setAbove] = useState("");
  const [below, setBelow] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setMessage(null);
    const up = toKobo(above), down = toKobo(below);
    if (Number.isNaN(up) || Number.isNaN(down)) return setProblem("Enter prices in naira, for example 25.50, or leave them empty.");
    try {
      await api.watch(ticker, { ...(up ? { alert_above_kobo: up } : {}), ...(down ? { alert_below_kobo: down } : {}) });
      setMessage(up || down ? "Saved. You will be told on your desk when the price gets there." : "Added to your watchlist.");
      watched.reload();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) return onLoggedOut();
      setProblem(failure instanceof ApiError ? failure.message : "Could not reach the server.");
    }
  }

  async function remove() {
    await api.unwatch(ticker).catch(() => undefined);
    setMessage("Removed from your watchlist.");
    watched.reload();
  }

  return (
    <form className="watch-form" onSubmit={save}>
      <div className="why-title">{mine ? "★ ON YOUR WATCHLIST" : "KEEP AN EYE ON IT"}</div>
      {mine && (mine.alert_above_kobo || mine.alert_below_kobo) && (
        <p className="small muted">
          You will be told when the price
          {mine.alert_above_kobo ? ` reaches ${formatNaira(mine.alert_above_kobo)}` : ""}
          {mine.alert_above_kobo && mine.alert_below_kobo ? " or" : ""}
          {mine.alert_below_kobo ? ` falls to ${formatNaira(mine.alert_below_kobo)}` : ""}.
        </p>
      )}
      <div className="row-inputs">
        <label>
          <span className="field-label">Tell me if it rises to (₦)</span>
          <input inputMode="decimal" value={above} onChange={(e) => setAbove(e.target.value)} placeholder="optional" />
        </label>
        <label>
          <span className="field-label">Tell me if it falls to (₦)</span>
          <input inputMode="decimal" value={below} onChange={(e) => setBelow(e.target.value)} placeholder="optional" />
        </label>
      </div>
      {problem && <div className="error" role="alert">{problem}</div>}
      {message && <div className="notice" role="status">{message}</div>}
      <div className="button-row">
        <button className="button-outline" type="submit">{mine ? "Save" : "☆ Watch this company"}</button>
        {mine && <button className="button-quiet" type="button" onClick={remove}>Stop watching</button>}
      </div>
    </form>
  );
}

function Verdict({ a }: { a: Analysis }) {
  const tone = a.verdict === "looks cheap" ? "up" : a.verdict === "looks expensive" ? "down" : "flat";
  const mark = tone === "up" ? "▼ price below worth" : tone === "down" ? "▲ price above worth" : "";
  return (
    <div className="advice">
      <div className="why-title">ADVISORY SUMMARY</div>
      <p className="advice-head">
        <span className={`verdict verdict-${tone}`}>{a.name} {a.verdict}</span>
        {mark && <span className="small muted"> · {mark}</span>}
      </p>
      <ul className="reasons">{a.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
      <div className="why-title">WHAT COULD GO WRONG</div>
      <ul className="reasons">{a.risks.map((risk, i) => <li key={i}>{risk}</li>)}</ul>
      <p className="small muted">
        This note is worked out from public figures: the company's filed accounts, its credit rating, the Central Bank's
        rate and prices on the exchange. It is a view, not a promise. Investors each take their own view, and so can you.
      </p>
    </div>
  );
}

/** What an investor wants to know about one company. */
export function InvestorPanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const analysis = useLoad(() => api.analysis(ticker), `analysis:${ticker}`, onLoggedOut);
  const days = useLoad(() => api.priceHistory(ticker), `history:${ticker}`, onLoggedOut);
  if (!analysis.data) return null;
  const a = analysis.data;
  const largest = Math.max(1, ...a.shareholders.map((h) => h.share_bps));
  const history = days.data ?? [];

  return (
    <Panel title="For investors" aside={`From its ${a.filing_label} filing and today's price`}>
      <div className="tiles">
        <Measure label="The whole company costs" value={formatCompact(a.market_value_kobo)}
                 meaning={`${count(a.shares_in_issue)} shares at ${formatNaira(a.price_kobo)}`} />
        <Measure label="Price against profit" value={times(a.price_to_profit)}
                 meaning={a.price_to_profit === null ? "it made no profit over the past year"
                   : `years of today's profit to pay for it${a.market_price_to_profit ? `; the market: ${times(a.market_price_to_profit)}` : ""}`} />
        <Measure label="Dividend, as a share of the price" value={formatPercent(a.dividend_yield_bps)}
                 meaning="what owners were paid over the past year, for each ₦100 of shares" />
        <Measure label="Price against owners' funds" value={times(a.price_to_owners_funds)}
                 meaning={`owners' funds are ${formatNaira(a.book_per_share_kobo)} a share`} />
      </div>

      {history.length >= 2 && (
        <>
          <div className="why-title">SHARE PRICE, DAY BY DAY</div>
          <SingleLine name="Closing price" format={(value) => `₦${value.toFixed(2)}`}
                      data={history.map((d) => ({ label: shortDate(d.session_date), value: Number(d.close_kobo) / 100 }))} />
        </>
      )}

      <div className="trade-grid">
        <div>
          <div className="why-title">WHAT ITS PROFITS ARE WORTH TODAY (NPV)</div>
          <div className="row"><span>Worth, by this sum</span><span className="mono strong">{formatNaira(a.npv_per_share_kobo)} a share</span></div>
          <div className="row"><span>Price on the exchange</span><span className="mono">{formatNaira(a.price_kobo)} a share</span></div>
          <div className="row">
            <span>The price is</span>
            <span className="mono">
              {a.npv_gap_bps === 0 ? "the same" : `${formatPercent(Math.abs(a.npv_gap_bps))} ${a.npv_gap_bps > 0 ? "above ▲" : "below ▼"}`}
            </span>
          </div>
          {a.schedule.length > 0 ? (
            <>
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">When</th>
                      <th scope="col" className="num">Profit expected</th>
                      <th scope="col" className="num">Worth today</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <th scope="row">The past year, as filed</th>
                      <td className="num mono">{formatCompact(a.yearly_profit_kobo)}</td>
                      <td className="num mono muted">–</td>
                    </tr>
                    {a.schedule.map((year) => (
                      <tr key={year.label}>
                        <th scope="row">{year.label}</th>
                        <td className="num mono">{formatCompact(year.profit_kobo)}</td>
                        <td className="num mono">{formatCompact(year.value_today_kobo)}</td>
                      </tr>
                    ))}
                    <tr>
                      <th scope="row">Added up</th>
                      <td className="num mono muted">–</td>
                      <td className="num mono strong">{formatCompact(a.npv_total_kobo)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="small muted">
                NPV means net present value. Profit is expected to grow {formatPercent(a.growth_bps)} a year for five years,
                then {formatPercent(a.long_run_bps)} a year for ever. Each future naira counts for less today: investors
                want {formatPercent(a.discount_bps)} a year for the risk of holding this share. The total, divided by{" "}
                {count(a.shares_in_issue)} shares, is the worth of one share.
              </p>
            </>
          ) : (
            <p className="small muted">
              The company is not making a profit to value, so it is taken to be worth half the owners' funds left in it,
              and never less than ₦1 a share.
            </p>
          )}
        </div>
        <div>
          <Verdict a={a} />
        </div>
      </div>

      <div className="trade-grid">
        <div>
          <div className="why-title">SHARES IN CIRCULATION</div>
          <div className="row"><span>Shares in issue</span><span className="mono strong">{count(a.shares_in_issue)}</span></div>
          {a.shareholders.map((holder) => (
            <div key={holder.holder} className="bar-row">
              <div className="row">
                <span>{holder.holder}</span>
                <span className="mono">{count(holder.shares)} <span className="muted">{formatPercent(holder.share_bps)}</span></span>
              </div>
              <div className="meter" aria-hidden="true"><div className="meter-fill" style={{ width: `${(holder.share_bps / largest) * 100}%` }} /></div>
            </div>
          ))}
        </div>
        <Watch ticker={ticker} onLoggedOut={onLoggedOut} />
      </div>
    </Panel>
  );
}
