import { useState } from "react";
import { api, type Industry, type IndustryCompany } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel } from "./Shell";

/** How strongly a tile is tinted: a move of 5% or more is the strongest. Direction is also shown by an arrow. */
function tint(bps: number): string {
  if (bps === 0) return "var(--raised)";
  const strength = Math.min(Math.abs(bps) / 500, 1) * 0.5 + 0.1;
  return bps > 0 ? `rgba(91, 227, 164, ${strength.toFixed(2)})` : `rgba(255, 138, 110, ${strength.toFixed(2)})`;
}

/** Every company as a tile, grouped by industry: the larger the company, the larger the tile. */
function HeatMap({ industries }: { industries: Industry[] }) {
  const [hover, setHover] = useState<IndustryCompany | null>(null);
  const total = industries.reduce((sum, s) => sum + Number(BigInt(s.market_value_kobo) / 100n), 0) || 1;
  return (
    <div>
      <div className="heat" role="list" aria-label="Every company, sized by what it is worth and tinted by today's move">
        {industries.map((sector) => {
          const value = Number(BigInt(sector.market_value_kobo) / 100n);
          return (
            <div key={sector.code} className="heat-sector" style={{ flexGrow: Math.max(value / total * 100, 4), flexBasis: `${Math.max(value / total * 100, 12)}%` }}>
              <div className="heat-name small"><span>{sector.name}</span> <Change bps={sector.change_bps} /></div>
              <div className="heat-tiles">
                {sector.companies.map((c) => {
                  const size = Number(BigInt(c.market_value_kobo) / 100n);
                  const arrow = c.change_bps > 0 ? "▲" : c.change_bps < 0 ? "▼" : "–";
                  return (
                    <a key={c.ticker} role="listitem" href={`#/companies/${c.ticker}`} className="heat-tile"
                       style={{ flexGrow: Math.max(size / (value || 1) * 100, 6), background: tint(c.change_bps) }}
                       onMouseEnter={() => setHover(c)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(c)} onBlur={() => setHover(null)}
                       aria-label={`${c.name}: ${c.change_bps > 0 ? "up" : c.change_bps < 0 ? "down" : "unchanged"} ${(Math.abs(c.change_bps) / 100).toFixed(1)}% today, worth ${formatCompact(c.market_value_kobo)}`}>
                      <span className="mono strong">{c.ticker}</span>
                      <span className="mono small">{arrow} {(Math.abs(c.change_bps) / 100).toFixed(1)}%</span>
                    </a>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      <p className="small muted heat-detail" role="status">
        {hover
          ? `${hover.name}: ${hover.price_kobo ? formatNaira(hover.price_kobo) : "not listed"}, ${hover.change_bps >= 0 ? "up" : "down"} ${(Math.abs(hover.change_bps) / 100).toFixed(1)}% today. The whole company is worth ${formatCompact(hover.market_value_kobo)}.`
          : "A larger tile is a larger company. Green with ▲ rose today, red with ▼ fell; the stronger the tint, the bigger the move. Point at a tile for its figures."}
      </p>
    </div>
  );
}

export function IndustriesWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const loaded = useLoad(api.industries, "industries", onLoggedOut);
  if (loaded.loading && !loaded.data) return <Loading what="the industries" />;
  if (loaded.error) return <Failed message={loaded.error} onRetry={loaded.reload} />;
  if (!loaded.data) return null;
  const industries = loaded.data;
  const ranked = [...industries].sort((a, b) => (b.sales_growth_bps ?? -1e9) - (a.sales_growth_bps ?? -1e9));
  return (
    <>
      <Panel title="The market at a glance" aside="Every company, by size and today's move">
        <HeatMap industries={industries} />
      </Panel>

      <Panel title="Growth by industry" aside="Sales over the past year against the year before, as filed">
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Industry</th>
                <th scope="col" className="num">Sales, past year</th>
                <th scope="col" className="num">Growth</th>
                <th scope="col" className="num">Worth on the exchange</th>
                <th scope="col" className="num">Today</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((s) => (
                <tr key={s.code}>
                  <th scope="row">{s.name}</th>
                  <td className="num mono">{formatCompact(s.sales_kobo)}</td>
                  <td className="num">{s.sales_growth_bps === null ? <span className="muted small">after two years of filings</span> : <Change bps={s.sales_growth_bps} />}</td>
                  <td className="num mono">{formatCompact(s.market_value_kobo)}</td>
                  <td className="num"><Change bps={s.change_bps} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Growth here includes rising prices. If prices rose 6% in the year, an industry that grew 6% sold no more than before.
        </p>
      </Panel>

      {industries.map((s) => (
        <Panel key={s.code} title={s.name} aside="Companies ranked by their share of the industry's sales">
          {s.companies.map((c) => (
            <div key={c.ticker} className="share-line">
              <span className="share-rank mono">{c.rank}</span>
              <span className="share-name"><a href={`#/companies/${c.ticker}`}>{c.name}</a></span>
              <span className="share-bar" aria-hidden="true"><span style={{ width: `${c.share_bps / 100}%` }} /></span>
              <span className="mono share-figure">{formatPercent(c.share_bps)}</span>
              <span className="share-growth">{c.sales_growth_bps === null ? "" : <Change bps={c.sales_growth_bps} />}</span>
            </div>
          ))}
        </Panel>
      ))}
    </>
  );
}
