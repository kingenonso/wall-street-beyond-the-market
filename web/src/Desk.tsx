import type { ReactNode } from "react";
import { api, type CompanySummary, type NewsItem, type Player, type Watched } from "./api";
import { ClosingBellPanel } from "./Bell";
import { WatchlistPanel } from "./Market";
import { GrantPanel } from "./Portfolio";
import { newsDate } from "./News";
import { formatCompact, formatCountdown, formatLagosDay, formatLagosTime, formatNaira, MARKET_LABEL } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";
import type { LiveClock } from "./useClock";

type Card = { tag: string; when: string; title: string; text: string; action: string; href: string };

/** "Needs you now": built only from things that are really true for this player right now. */
function cardsFor(player: Player, latestQuarter: string | null, live: LiveClock | null, count: number | null,
                  topStory: NewsItem | null, alerts: Watched[], decisions: Card[]): Card[] {
  const all = count ? `All ${count}` : "All the";
  // A decision only this player can make comes before anything else.
  const cards: Card[] = [...decisions];
  // A professional's first need is a build, a bank and an employer: nothing else can be earned without them.
  if (!player.build) {
    cards.unshift({
      tag: "START HERE", when: "Three steps",
      title: "Choose your build",
      text: "Asset Manager or Accountant. Then choose your bank and an employer, and you are on salary with work to do.",
      action: "Start your career", href: "#/career",
    });
  } else if (!player.employer) {
    cards.unshift({
      tag: "CAREER", when: player.build_name ?? "",
      title: "Find an employer",
      text: "Work and salary come through an employer. Choose your bank first, so the employer knows where to pay you.",
      action: "Go to your career", href: "#/career",
    });
  }
  // A price you asked to be told about comes first: it is the one thing here you set yourself.
  for (const alert of alerts) {
    const target = alert.reached === "above" ? alert.alert_above_kobo : alert.alert_below_kobo;
    cards.push({
      tag: "PRICE ALERT",
      when: formatNaira(alert.price_kobo),
      title: alert.reached === "above"
        ? `${alert.name} has reached ${formatNaira(target ?? "0")}`
        : `${alert.name} has fallen to ${formatNaira(target ?? "0")}`,
      text: `You asked to be told. The share is now at ${formatNaira(alert.price_kobo)}. Change or remove the alert on the company's page when you have seen it.`,
      action: "Open the company",
      href: `#/companies/${alert.ticker}`,
    });
  }
  if (topStory) {
    cards.push({
      tag: topStory.outlet.toUpperCase(),
      when: newsDate(topStory),
      title: topStory.headline,
      text: topStory.body,
      action: "Read the news",
      href: "#/news",
    });
  }
  if (latestQuarter) {
    cards.push({
      tag: "RESULTS",
      when: latestQuarter,
      title: `The ${latestQuarter} results are out`,
      text: `${all} companies have filed their accounts. See who grew, who slipped, who lost money and who is in default.`,
      action: "Read the filings",
      href: "#/companies",
    });
  } else {
    cards.push({
      tag: "THE WORLD",
      when: live && !live.clock.world_started ? "Not open yet" : "First quarter",
      title: count ? `Get to know the ${count} companies` : "Get to know the companies",
      text: "Each has an opening balance sheet on file. Their first quarterly results arrive one real week after the world opens.",
      action: "See the companies",
      href: "#/companies",
    });
  }
  if (player.profile_icon === null) {
    cards.push({
      tag: "PROFILE",
      when: "One minute",
      title: "Choose your profile picture",
      text: "Pick the male or the female icon. It is how other players will see you.",
      action: "Choose a picture",
      href: "#/profile",
    });
  }
  return cards;
}

function NeedsYouNow({ cards }: { cards: Card[] }) {
  return (
    <section aria-labelledby="queue-heading">
      <div className="work-head">
        <h1 id="queue-heading">Needs you now</h1>
        <span className="muted small">{cards.length === 1 ? "1 item" : `${cards.length} items`}</span>
      </div>
      <div className="queue">
        {cards.map((card, index) => (
          <article key={card.title} className={index === 0 ? "card card-first" : "card"}>
            <div className="card-top">
              <span className="card-tag">{card.tag}</span>
              <span className="mono muted">{card.when}</span>
            </div>
            <h3>{card.title}</h3>
            <p className="muted">{card.text}</p>
            <a className={index === 0 ? "button-primary" : "button-outline"} href={card.href}>{card.action}</a>
          </article>
        ))}
      </div>
    </section>
  );
}

function Movers({ companies, quarter }: { companies: CompanySummary[]; quarter: string }) {
  const ranked = companies
    .filter((c) => c.revenue_change_bps !== null)
    .sort((a, b) => (b.revenue_change_bps ?? 0) - (a.revenue_change_bps ?? 0));
  if (ranked.length === 0) return null;
  const rows = [...ranked.slice(0, 3), ...ranked.slice(-3)];
  return (
    <Panel title={`Biggest moves in sales, ${quarter}`} aside={<a href="#/companies">All {companies.length} companies</a>}>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col" className="num">Sales</th>
              <th scope="col" className="num">Against last quarter</th>
              <th scope="col" className="num">Net profit</th>
              <th scope="col">Rating</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.ticker}>
                <th scope="row"><a href={`#/companies/${c.ticker}`}>{c.name}</a></th>
                <td className="num mono">{formatCompact(c.revenue_kobo)}</td>
                <td className="num"><Change bps={c.revenue_change_bps} /></td>
                <td className={c.net_profit_kobo.startsWith("-") ? "num mono change-down" : "num mono"}>{formatCompact(c.net_profit_kobo)}</td>
                <td><Rating value={c.credit_rating} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">The three strongest and the three weakest against last quarter. Open a company to see why its sales moved.</p>
    </Panel>
  );
}

export function DeskWork({ player, live, onLoggedOut }: { player: Player; live: LiveClock | null; onLoggedOut: () => void }) {
  const status = useLoad(api.worldStatus, "status", onLoggedOut);
  const companies = useLoad(api.companies, "companies", onLoggedOut);
  const movements = useLoad(api.movements, `movements:${player.cash.amount_kobo}`, onLoggedOut);
  const news = useLoad(() => api.news({ limit: 40 }), "desk-news", onLoggedOut);
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const alerts = (watched.data ?? []).filter((w) => w.reached !== null);
  const corporate = useLoad(api.corporate, "desk-corporate", onLoggedOut);
  const decisions: Card[] = [];
  for (const bid of corporate.data?.takeovers ?? []) {
    if (bid.status === "open" && bid.free + bid.offered > 0) {
      decisions.push({
        tag: bid.hostile ? "HOSTILE BID" : "TAKEOVER OFFER", when: formatNaira(bid.price_kobo),
        title: `${bid.bidder} has offered ${formatNaira(bid.price_kobo)} a share for ${bid.target}`,
        text: `You hold shares in ${bid.target}. ${bid.offered > 0 ? `You have offered ${bid.offered.toLocaleString("en-NG")} of them.` : "You have not answered yet."} The offer closes ${bid.closes_label}.`,
        action: "Answer the offer", href: "#/market/offers",
      });
    }
  }
  for (const vote of corporate.data?.votes ?? []) {
    if (vote.status === "open" && vote.my_shares > 0 && !vote.my_choice) {
      decisions.push({
        tag: "YOUR VOTE", when: vote.name, title: vote.question,
        text: `You hold ${vote.my_shares.toLocaleString("en-NG")} shares, so you have a vote. It is counted ${vote.closes_label}.`,
        action: "Vote", href: "#/market/offers",
      });
    }
  }
  const quarter = status.data?.last_closed_label ?? null;
  // The top story: the most important item of the last three game days, if it matters enough to interrupt.
  const items = news.data?.items ?? [];
  const recent = items.filter((item) => item.period === items[0].period && item.day >= items[0].day - 2);
  const top = recent.reduce<NewsItem | null>((best, item) => (!best || item.importance > best.importance ? item : best), null);
  const seen = new Set<string>();
  const headlines = items.filter((item) => {
    const key = `${item.story}|${item.kind}|${item.period}`;
    return item === top || seen.has(key) ? false : (seen.add(key), true);
  }).slice(0, 6);

  return (
    <>
      <NeedsYouNow cards={cardsFor(player, quarter, live, status.data?.companies ?? null, top && top.importance >= 60 ? top : null, alerts, decisions)} />

      <GrantPanel onLoggedOut={onLoggedOut} onChanged={() => undefined} />

      <ClosingBellPanel onLoggedOut={onLoggedOut} brief />

      {headlines.length > 0 && (
        <Panel title="Latest news" aside={<a href="#/news">All news</a>}>
          {headlines.map((item, index) => (
            <div key={index} className="news-line">
              <div className="small muted"><span className="mono">{newsDate(item)}</span> · {item.outlet}</div>
              <div className="strong">{item.headline}</div>
            </div>
          ))}
        </Panel>
      )}

      {quarter && companies.data && (
        <Movers companies={companies.data.sectors.flatMap((s) => s.companies)} quarter={quarter} />
      )}

      <Panel title="Your account" aside="Every naira in and out, newest first">
        <div className="headline">
          <span className="mono figure">{formatNaira(player.cash.amount_kobo)}</span>
          <span className="muted">cash</span>
        </div>
        {movements.loading && <Loading what="your account" />}
        {movements.error && <Failed message={movements.error} onRetry={movements.reload} />}
        {movements.data && (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">When (Lagos)</th>
                  <th scope="col">What</th>
                  <th scope="col">Paid by / paid to</th>
                  <th scope="col" className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {movements.data.map((m, index) => {
                  const incoming = !m.amount_kobo.startsWith("-");
                  return (
                    <tr key={index}>
                      <td className="mono muted">{formatLagosDay(new Date(m.at))} {formatLagosTime(new Date(m.at), false)}</td>
                      <td>{m.memo}</td>
                      <td>{incoming ? "Paid by " : "Paid to "}{m.counterparty}</td>
                      <td className={`num mono ${incoming ? "change-up" : "change-down"}`}>
                        {incoming ? "+" : ""}{formatNaira(m.amount_kobo)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="row">
      <span>{label}</span>
      <span className="mono">{children}</span>
    </div>
  );
}

const SESSIONS = [
  { state: "opening_auction", name: "Opening auction", hours: "11:30 to 12:00" },
  { state: "open", name: "Open", hours: "12:00 to 22:00" },
  { state: "closed", name: "Closed", hours: "22:00 to 11:30" },
] as const;

export function DeskRail({ player, live, onLoggedOut }: { player: Player; live: LiveClock | null; onLoggedOut: () => void }) {
  const date = live?.clock.game_date;
  return (
    <>
      <Panel title="Broad Street Exchange">
        <div className="headline">
          <span className="figure-small">{live ? MARKET_LABEL[live.clock.market_state] : "…"}</span>
        </div>
        {live && (
          <p className="muted small">
            {MARKET_LABEL[live.clock.next_state]} {formatCountdown(live.msToNextChange)}, at{" "}
            <span className="mono">{formatLagosTime(new Date(live.clock.next_change_at), false)}</span> Lagos time.
          </p>
        )}
        {SESSIONS.map((session) => (
          <div key={session.state} className={live?.clock.market_state === session.state ? "row row-current" : "row"}>
            <span>{session.name}</span>
            <span className="mono">{session.hours}</span>
          </div>
        ))}
        <p className="muted small">
          <a href="#/market">Open the market</a> to see every share. Orders placed while it is closed wait for the opening auction.
        </p>
      </Panel>

      <WatchlistPanel onLoggedOut={onLoggedOut} />

      <Panel title="Game calendar">
        {date ? (
          <>
            <div className="headline"><span className="figure-small">Year {date.year} · Q{date.quarter}</span></div>
            <div className="meter" role="img" aria-label={`Day ${date.day_of_quarter} of 90 in this quarter`}>
              <div className="meter-fill" style={{ width: `${(date.day_of_quarter / 90) * 100}%` }} />
            </div>
            <p className="muted small">Day {date.day_of_quarter} of 90. Companies file their results when the quarter ends.</p>
          </>
        ) : (
          <p className="muted">The world has not opened yet.</p>
        )}
        <Row label="One real week">One game quarter</Row>
        <Row label="Four real weeks">One game year</Row>
      </Panel>

      <Panel title="Your standing">
        <Row label="Reputation">{player.reputation} / 100</Row>
        <p className="muted small">Everyone starts at 50. Reputation rises and falls with what you do.</p>
      </Panel>
    </>
  );
}
