import { useState } from "react";
import { api } from "./api";
import { formatCompact, formatLagosDate, formatLagosTime, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Change, Panel } from "./Shell";
import { SingleLine } from "./TrendChart";

const kobo = (value: number) => (Math.abs(value) >= 100 ? `₦${(value / 100).toFixed(2)}` : `${value.toFixed(1)} kobo`);

function Fact({ label, value, meaning }: { label: string; value: React.ReactNode; meaning: React.ReactNode }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="mono figure-small">{value}</div>
      <div className="small muted">{meaning}</div>
    </div>
  );
}

/** Quick facts for an investor: profit per share, the year-on-year comparison, cash, the year's range, the next results. */
export function FactsPanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const { data: f } = useLoad(() => api.facts(ticker), `facts:${ticker}`, onLoggedOut);
  if (!f) return null;
  const eps = f.profit_per_share;
  const cashUp = BigInt(f.cash_change_year_kobo) >= 0n;
  return (
    <Panel title="Quick facts" aside={`From its ${f.filing_label} filing and the exchange's records`}>
      <div className="tiles">
        <Fact label="Profit per share, past year" value={kobo(f.yearly_profit_per_share_kobo)}
              meaning="profit after tax divided by the number of shares" />
        <Fact label="Sales against a year ago"
              value={f.sales_change_bps === null ? "n/a" : <Change bps={f.sales_change_bps} />}
              meaning={f.compared_with ? `against ${f.compared_with}${f.sales_before_kobo ? ` (${formatCompact(f.sales_before_kobo)})` : ""}` : "nothing to compare with yet"} />
        <Fact label="Profit against a year ago"
              value={f.profit_change_bps === null ? "n/a" : <Change bps={f.profit_change_bps} />}
              meaning={f.compared_with ? `against ${f.compared_with}${f.profit_before_kobo ? ` (${formatCompact(f.profit_before_kobo)})` : ""}` : "nothing to compare with yet"} />
        <Fact label="Highest and lowest price, past year"
              value={f.year_high_kobo && f.year_low_kobo ? `${formatNaira(f.year_low_kobo)} – ${formatNaira(f.year_high_kobo)}` : "n/a"}
              meaning={f.year_high_kobo ? "over the past game year (four real weeks)" : "it has not traded in the past game year"} />
        <Fact label="Next results"
              value={f.next_results ? f.next_results.label : "n/a"}
              meaning={f.next_results ? `filed ${formatLagosDate(new Date(f.next_results.at))} at ${formatLagosTime(new Date(f.next_results.at), false)} Lagos time` : "the world has not opened"} />
        <Fact label={`Place in ${f.industry.sector.toLowerCase()}`}
              value={`${f.industry.rank} of ${f.industry.of}`}
              meaning={`${formatPercent(f.industry.share_bps)} of the industry's sales over the past year`} />
      </div>

      {eps.length >= 2 && (
        <>
          <div className="why-title">Profit per share, by quarter (kobo)</div>
          <SingleLine name="Profit per share" format={(v) => v.toFixed(0)}
                      data={eps.map((p) => ({ label: p.label.replace("Year ", "Y"), value: p.kobo_per_share }))} />
        </>
      )}

      <div className="why-title">Cash outlook</div>
      <div className="tiles">
        <Fact label="Cash now" value={formatCompact(f.cash_kobo)} meaning="as filed" />
        <Fact label="Change over the past year"
              value={<span className={cashUp ? "change-up" : "change-down"}>{cashUp ? "▲" : "▼"} {formatCompact(f.cash_change_year_kobo).replace("−", "")}</span>}
              meaning={cashUp ? "cash came in" : "cash went out"} />
        <Fact label="In three months, at this pace" value={formatCompact(f.cash_in_three_months_kobo)}
              meaning="an estimate, not a promise" />
      </div>
      <p className="small">{f.cash_outlook}</p>

      <div className="why-title">Who controls it</div>
      <p className="small">{f.control}</p>

      {f.notices.length > 0 && (
        <>
          <div className="why-title">Notices from the exchange</div>
          {f.notices.map((n, i) => (
            <div key={i} className="news-line">
              <div className="small muted">{n.period_label}</div>
              <div className="strong">{n.title}</div>
              <div className="small">{n.body}</div>
            </div>
          ))}
          <p className="small"><a href="#/market/offers">Offers, votes and bids</a></p>
        </>
      )}
    </Panel>
  );
}

/** One quarter's results in words, built only from what the company filed. */
export function ResultsReportPanel({ ticker, onLoggedOut }: { ticker: string; onLoggedOut: () => void }) {
  const [period, setPeriod] = useState<number | undefined>(undefined);
  const { data: r } = useLoad(() => api.resultsReport(ticker, period), `report:${ticker}:${period}`, onLoggedOut);
  if (!r) return null;
  return (
    <Panel title="Results report" aside={
      r.available.length > 1 ? (
        <label className="small">Quarter{" "}
          <select value={r.period} onChange={(e) => setPeriod(Number(e.target.value))}>
            {[...r.available].reverse().map((q) => <option key={q.period} value={q.period}>{q.label}</option>)}
          </select>
        </label>
      ) : r.label
    }>
      <h3>{r.title}</h3>
      {r.paragraphs.map((text) => <p key={text} className="small">{text}</p>)}
      <p className="muted small">Written from the figures the company filed. Nothing here is an opinion or a forecast.</p>
    </Panel>
  );
}
