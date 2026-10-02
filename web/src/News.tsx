import { useState } from "react";
import { api, type NewsItem } from "./api";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";

/** "Year 2 Q3, day 14": when an item came out, on the game's calendar. */
export const newsDate = (item: NewsItem) => `${item.period_label}, day ${item.day}`;

/** One telling of each story: when several papers carry it, the first is kept. */
function oneOfEach(items: NewsItem[]): NewsItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.story}|${item.kind}|${item.period}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function Story({ item, lead = false }: { item: NewsItem; lead?: boolean }) {
  return (
    <article className={lead ? "story story-lead" : "story"}>
      <div className="story-top">
        <span className="card-tag">{item.outlet.toUpperCase()}</span>
        <span className="mono muted">{newsDate(item)}</span>
      </div>
      <h3>{item.headline}</h3>
      <p className="muted">{item.body}</p>
      {item.tickers.length > 0 && item.tickers.length <= 6 && (
        <div className="chips">
          {item.tickers.map((ticker) => (
            <a key={ticker} className="chip mono" href={`#/companies/${ticker}`}>{ticker}</a>
          ))}
        </div>
      )}
    </article>
  );
}

export function NewsWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [outlet, setOutlet] = useState<string>("");
  const { data, error, loading, reload } = useLoad(
    () => api.news({ outlet: outlet || undefined, limit: 80 }), `news:${outlet}`, onLoggedOut,
  );
  const items = data ? (outlet ? data.items : oneOfEach(data.items)) : [];
  // The front page leads with the most important story of the latest day that has news.
  const latest = items.filter((item) => item.period === items[0]?.period && item.day === items[0]?.day);
  const lead = latest.length ? latest.reduce((best, item) => (item.importance > best.importance ? item : best)) : null;
  const rest = items.filter((item) => item !== lead);

  return (
    <>
      <div className="work-head">
        <h1>News</h1>
        <span className="muted small">Every headline comes from something that really happened in the game</span>
      </div>
      <div className="tabs tabs-inline" role="tablist" aria-label="Newspaper">
        {["", ...(data?.outlets ?? [])].map((name) => (
          <button key={name} role="tab" aria-selected={outlet === name}
                  className={outlet === name ? "tab active" : "tab"} onClick={() => setOutlet(name)}>
            {name || "All papers"}
          </button>
        ))}
      </div>
      {loading && !data && <Loading what="the news" />}
      {error && <Failed message={error} onRetry={reload} />}
      {data && items.length === 0 && (
        <Panel>
          <p className="muted">
            Nothing has been reported yet. News appears on the day something happens: a flood, a strike, a decision by the
            Central Bank, a company's results.
          </p>
        </Panel>
      )}
      {lead && <Story item={lead} lead />}
      <div className="stories">
        {rest.map((item, index) => <Story key={`${item.period}-${item.day}-${item.outlet}-${index}`} item={item} />)}
      </div>
    </>
  );
}

export function NewsRail() {
  return (
    <>
      <Panel title="The three papers">
        <div className="row"><span className="strong">The Lagoon Herald</span></div>
        <p className="muted small">A daily paper. It tells each story through the people it touches: workers, traders, families.</p>
        <div className="row"><span className="strong">Ogene News Network</span></div>
        <p className="muted small">A broadcaster. Short and fast: what happened, where, and to whom.</p>
        <div className="row"><span className="strong">The Naira Ledger</span></div>
        <p className="muted small">A financial paper. Figures first: sales, costs, lenders and investors.</p>
      </Panel>
      <Panel title="How the news works">
        <ul className="reasons">
          <li>Nothing is made up. Each item is written from a recorded event, a filed report, or a decision of the Central Bank.</li>
          <li>News comes out on the day it happens. A quarter has 90 game days.</li>
          <li>The bigger the story, the more papers carry it, each in its own words.</li>
          <li>Company results come out over the first three weeks of the next quarter.</li>
        </ul>
        <p className="muted small">Full articles behind each headline arrive in a later stage.</p>
      </Panel>
    </>
  );
}
