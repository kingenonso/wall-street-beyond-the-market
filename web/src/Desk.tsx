import type { ReactNode } from "react";
import { api, type CompanySummary, type NewsItem, type Player, type Watched } from "./api";
import { ClosingBellPanel } from "./Bell";
import { shortDate } from "./Market";
import { AreaChart, Sparkline } from "./Charts";
import { Term } from "./Term";
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
  if (player.rank_waiting) {
    cards.unshift({
      tag: "◆ RANK CASE", when: player.build_name ? `Level ${player.level}` : "",
      title: "A rank case is waiting for you",
      text: "Your modules are mastered, so you can sit the case that takes you past your level gate. Or you have one in hand to finish.",
      action: "Open your rank", href: "#/rank",
    });
  }
  if ((player.margin_calls ?? 0) > 0) {
    cards.unshift({
      tag: "■ MARGIN CALL", when: "By the next Closing Bell",
      title: player.margin_calls === 1 ? "A margin call is waiting" : `${player.margin_calls} margin calls are waiting`,
      text: "A loan, a short or a contract of yours needs more cash by the next Closing Bell (22:00), or it will be closed for you at the market's price.",
      action: "See what you owe", href: "#/borrow",
    });
  }
  if ((player.press_questions ?? 0) > 0) {
    cards.unshift({
      tag: "● PRESS", when: "Within a day",
      title: player.press_questions === 1 ? "A journalist has asked your empire a question" : `${player.press_questions} journalists' questions are waiting`,
      text: "Answer on the record, or decline. A question left to run out of time costs the empire a little of its good name.",
      action: "Answer the press", href: "#/news/questions",
    });
  }
  if ((player.crises_due ?? 0) > 0) {
    cards.unshift({
      tag: "■ STATEMENT", when: "Within a day",
      title: "Something has come out about your empire",
      text: "Make a statement for the empire: admitting what is true, quickly, costs least; saying nothing costs a lot.",
      action: "Open the press desk", href: "#/empire/press",
    });
  }
  if ((player.banks_uneasy ?? 0) > 0) {
    cards.unshift({
      tag: "■ YOUR SAVINGS", when: "Today",
      title: "Savers are leaving a bank that holds your money",
      text: "Only the first ₦5 million at each bank is guaranteed. Look at how far each bank is trusted, and decide whether to move your savings.",
      action: "Open your savings", href: "#/portfolio",
    });
  }
  if ((player.corrections_due ?? 0) > 0) {
    cards.unshift({
      tag: "■ CORRECTION", when: "Within a day",
      title: "A story of yours must be corrected",
      text: "The record has changed since you published it. Correct it within a day; a late correction costs more reputation and readers.",
      action: "Open the newsroom", href: "#/news/newsroom",
    });
  }
  if (player.unread_messages > 0) {
    cards.push({
      tag: "● MESSAGES", when: `${player.unread_messages} unread`,
      title: player.unread_messages === 1 ? "A player wrote to you" : `${player.unread_messages} messages waiting`,
      text: "Read and answer from your messages. You can block anyone who bothers you.",
      action: "Read your messages", href: "#/messages",
    });
  }
  if (player.build && player.employer && player.work_in_hand === 0) {
    cards.push({
      tag: "○ WORK", when: "This quarter",
      title: "Take on a piece of work",
      text: "Your employer pays a quarter's salary only to staff who finish at least one piece of work in it.",
      action: "See work you can start", href: "#/work",
    });
  }
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
            <h2 className="h3-look">{card.title}</h2>
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
      <div className="scroll" tabIndex={0}>
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


  return (
    <>
      <NeedsYouNow cards={cardsFor(player, quarter, live, status.data?.companies ?? null, top && top.importance >= 60 ? top : null, alerts, decisions)} />

      <MoneyTiles player={player} onLoggedOut={onLoggedOut} />

      <WatchTable onLoggedOut={onLoggedOut} />

      <GrantPanel onLoggedOut={onLoggedOut} onChanged={() => undefined} />

      <ClosingBellPanel onLoggedOut={onLoggedOut} brief />

      {quarter && companies.data && (
        <Movers companies={companies.data.sectors.flatMap((s) => s.companies)} quarter={quarter} />
      )}

      <Panel title="Your account" aside="Every naira in and out, newest first">
        <details open={false}>
        <summary className="small" style={{ cursor: "pointer", color: "var(--gold)", marginBottom: 8 }}>Show every naira in and out</summary>
        <div className="headline">
          <span className="mono figure">{formatNaira(player.cash.amount_kobo)}</span>
          <span className="muted">cash</span>
        </div>
        {movements.loading && <Loading what="your account" />}
        {movements.error && <Failed message={movements.error} onRetry={movements.reload} />}
        {movements.data && (
          <div className="scroll" tabIndex={0}>
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
        </details>
      </Panel>
    </>
  );
}

/** Four figures across the desk: what the player owns, their cash, their shares and bonds, their retirement savings. */
function MoneyTiles({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const portfolio = useLoad(api.portfolio, "portfolio", onLoggedOut);
  const career = useLoad(api.career, "desk-career", onLoggedOut);
  const p = portfolio.data;
  const last = p && p.net_worth.length ? p.net_worth[p.net_worth.length - 1].total_kobo : null;
  const moved = p && last ? BigInt(p.total_kobo) - BigInt(last) : null;
  const invested = p ? (BigInt(p.shares_value_kobo) + BigInt(p.bonds_value_kobo)).toString() : null;
  const retirement = career.data?.retirement?.value_kobo ?? null;
  const days = (p?.net_worth ?? []).slice(-30);
  return (
    <>
      <div className="tiles money-tiles">
        <div className="tile"><div className="lbl"><Term word="Net worth">What you own</Term></div>
          <div className="mono figure-small">{p ? formatCompact(p.total_kobo) : "…"}</div>
          <div className="small">{moved === null ? <span className="muted">first figure at tonight’s Closing Bell</span>
            : <span className={`mono change-${moved > 0n ? "up" : moved < 0n ? "down" : "flat"}`}>{moved > 0n ? "▲" : moved < 0n ? "▼" : "–"} {formatCompact((moved < 0n ? -moved : moved).toString())} since the last bell</span>}</div></div>
        <div className="tile"><div className="lbl">Cash</div><div className="mono figure-small">{formatCompact(player.cash.amount_kobo)}</div><div className="small muted">money you can spend now</div></div>
        <div className="tile"><div className="lbl">Shares and bonds</div><div className="mono figure-small">{invested ? formatCompact(invested) : "…"}</div><div className="small muted">at today’s prices · <a href="#/portfolio">portfolio</a></div></div>
        <div className="tile"><div className="lbl">Retirement savings</div><div className="mono figure-small">{retirement ? formatCompact(retirement) : "–"}</div><div className="small muted">{retirement ? "locked until retirement" : "starts with your first salary"}</div></div>
      </div>
      {days.length >= 2 && (
        <Panel title="What you own, day by day">
          <AreaChart points={days.map((d) => ({ label: shortDate(d.session_date), value: Number(BigInt(d.total_kobo) / 100n) }))}
                     format={(v) => formatCompact((BigInt(Math.round(v)) * 100n).toString())} height={150} color="var(--gold)"
                     label={`What you own went from ${formatCompact(days[0].total_kobo)} to ${formatCompact(days[days.length - 1].total_kobo)} over ${days.length} Closing Bells.`} />
        </Panel>
      )}
    </>
  );
}

/** The watchlist as a dense table, with each share's last five days as a small line. */
function WatchTable({ onLoggedOut }: { onLoggedOut: () => void }) {
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const market = useLoad(api.market, "market", onLoggedOut);
  const list = watched.data ?? [];
  const closes = new Map((market.data?.shares ?? []).map((s) => [s.ticker, s.closes.map(Number)]));
  return (
    <Panel title="Your watchlist" aside={<a href="#/market">Open the market</a>}>
      {list.length === 0 ? (
        <p className="muted small">Nothing yet. Press ☆ beside a company on the Market page, or on its own page, to keep an eye on it here.</p>
      ) : (
        <div className="scroll" tabIndex={0}>
          <table className="dense">
            <thead><tr><th scope="col">Code</th><th scope="col">Company</th><th scope="col" className="num">Price</th><th scope="col" className="num">Today</th><th scope="col">Last 5 days</th></tr></thead>
            <tbody>
              {list.map((w) => (
                <tr key={w.ticker} className={w.reached ? "row-alert" : undefined}>
                  <td className="mono strong"><a href={`#/companies/${w.ticker}`}>{w.ticker}</a></td>
                  <th scope="row">{w.name}{w.reached && <div className="small">{w.reached === "above" ? "▲ Reached" : "▼ Fell to"} your price</div>}</th>
                  <td className="num mono">{formatNaira(w.price_kobo)}</td>
                  <td className="num"><Change bps={w.change_bps} /></td>
                  <td><Sparkline values={closes.get(w.ticker) ?? []} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/** The latest stories, one line each. */
function LatestNews({ onLoggedOut }: { onLoggedOut: () => void }) {
  const news = useLoad(() => api.news({ limit: 20 }), "desk-news", onLoggedOut);
  const seen = new Set<string>();
  const items = (news.data?.items ?? []).filter((item) => {
    const key = `${item.story}|${item.kind}|${item.period}`;
    return seen.has(key) ? false : (seen.add(key), true);
  }).slice(0, 4);
  if (items.length === 0) return null;
  return (
    <Panel title="Latest news" aside={<a href="#/news">All news</a>}>
      {items.map((item, index) => (
        <a key={index} href="#/news" className="news-line plain-link" style={{ display: "block" }}>
          <div className="lbl" style={{ fontSize: 10 }}>{item.outlet} · {newsDate(item)}</div>
          <div className="small">{item.headline}</div>
        </a>
      ))}
    </Panel>
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

/** The BSX 50 today, and how many shares rose and fell. */
function MarketToday({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data } = useLoad(api.market, "market", onLoggedOut);
  if (!data) return null;
  const traded = data.shares.filter((s) => s.volume > 0);
  const up = traded.filter((s) => s.change_bps > 0).length, down = traded.filter((s) => s.change_bps < 0).length;
  return (
    <Panel title="BSX 50 today">
      <div className="headline"><span className="mono figure-small">{data.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span><Change bps={traded.length ? data.index_change_bps : null} /></div>
      <p className="small">{traded.length ? `${up} shares up ▲, ${down} down ▼, ${traded.length - up - down} unchanged.` : "Nothing has traded yet today."}</p>
    </Panel>
  );
}

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

      <MarketToday onLoggedOut={onLoggedOut} />

      <LatestNews onLoggedOut={onLoggedOut} />

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
