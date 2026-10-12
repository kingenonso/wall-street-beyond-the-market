import { useState } from "react";
import { api, type NewsItem } from "./api";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel } from "./Shell";

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

/** A company named in a story, with how its share price has moved since the story came out. */
function MoveChip({ ticker, bps }: { ticker: string; bps: number | undefined }) {
  return (
    <a className="chip mono" href={`#/companies/${ticker}`}
       aria-label={bps === undefined ? ticker : `${ticker}: ${bps > 0 ? "up" : bps < 0 ? "down" : "unchanged"} ${(Math.abs(bps) / 100).toFixed(1)}% since this story`}>
      {ticker}{bps !== undefined && <> <Change bps={bps} /></>}
    </a>
  );
}

export function Story({ item, lead = false }: { item: NewsItem; lead?: boolean }) {
  const moved = item.tickers.filter((t) => item.moves[t] !== undefined);
  return (
    <article className={lead ? "story story-lead" : "story"}>
      <div className={lead ? "story-lead-grid" : undefined}>
        <div>
          <div className="story-top">
            <span className="card-tag">{item.outlet.toUpperCase()}{lead ? " · LEAD STORY" : ""}</span>
            <span className="mono muted">{newsDate(item)}</span>
          </div>
          <h2 className="h3-look">{item.headline}</h2>
          <p className="muted">{item.body}</p>
          {item.tickers.length > 0 && item.tickers.length <= 6 && (
            <div className="chips">
              {item.tickers.map((ticker) => <MoveChip key={ticker} ticker={ticker} bps={item.moves[ticker]} />)}
            </div>
          )}
        </div>
        {lead && moved.length > 0 && (
          <div className="story-moves">
            <div className="lbl">What happened to prices after this story</div>
            {moved.map((t) => (
              <div key={t} className="row"><a href={`#/companies/${t}`} className="mono strong">{t}</a><Change bps={item.moves[t]} /></div>
            ))}
            <p className="muted small">From the last close before the story to the price now. A story moves prices only when investors believe it matters.</p>
          </div>
        )}
      </div>
    </article>
  );
}

type NewsFilter = "" | "mine" | "moved";

export function NewsWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [outlet, setOutlet] = useState<string>("");
  const [only, setOnly] = useState<NewsFilter>("");
  const { data, error, loading, reload } = useLoad(
    () => api.news({ outlet: outlet || undefined, limit: 80 }), `news:${outlet}`, onLoggedOut,
  );
  const holdings = useLoad(api.myHoldings, "holdings", onLoggedOut);
  const mine = new Set((holdings.data ?? []).map((h) => h.ticker));
  const all = data ? (outlet ? data.items : oneOfEach(data.items)) : [];
  const items = all.filter((item) =>
    only === "mine" ? item.tickers.some((t) => mine.has(t))
      : only === "moved" ? Object.values(item.moves).some((bps) => Math.abs(bps) >= 100) : true);
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
      <div className="filter-row" role="group" aria-label="Which news">
        {["", ...(data?.outlets ?? [])].map((name) => (
          <button key={name} className="filter-chip" aria-pressed={outlet === name} onClick={() => setOutlet(name)}>{name || "All papers"}</button>
        ))}
        <span className="filter-gap" aria-hidden="true" />
        <button className="filter-chip" aria-pressed={only === "mine"} onClick={() => setOnly(only === "mine" ? "" : "mine")}>About what I own</button>
        <button className="filter-chip" aria-pressed={only === "moved"} onClick={() => setOnly(only === "moved" ? "" : "moved")}>▲▼ Moved prices</button>
      </div>
      {loading && !data && <Loading what="the news" />}
      {error && <Failed message={error} onRetry={reload} />}
      {data && items.length === 0 && only && <Panel><p className="muted">No stories here yet{only === "mine" ? " about the companies you own" : " that moved a price by 1% or more"}.</p></Panel>}
      {data && all.length === 0 && (
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
      <Panel>
        <details>
        <summary className="strong" style={{ cursor: "pointer" }}>? How the news works</summary>
        <ul className="reasons" style={{ marginTop: 10 }}>
          <li>Nothing is made up. Each item is written from a recorded event, a filed report, or a decision of the Central Bank.</li>
          <li>News comes out on the day it happens. A quarter has 90 game days.</li>
          <li>The bigger the story, the more papers carry it, each in its own words.</li>
          <li>Company results come out over the first three weeks of the next quarter.</li>
        </ul>
        <p className="muted small">Full articles behind each headline arrive in a later stage.</p>
        </details>
      </Panel>
    </>
  );
}
