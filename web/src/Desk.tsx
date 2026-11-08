import { useState, type ReactNode } from "react";
import { api, type Career, type Market, type Movement, type NewsItem, type Player, type Portfolio, type Watched } from "./api";
import { ClosingBellPanel } from "./Bell";
import { Sparkline } from "./Charts";
import { Term } from "./Term";
import { GrantPanel } from "./Portfolio";
import { newsDate } from "./News";
import { formatCompact, formatCountdown, formatLagosDay, formatLagosTime, formatNaira, MARKET_LABEL } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";
import type { LiveClock } from "./useClock";

/**
 * The desk (November 2026).
 *
 * The player's own page is a broker's sheet. Along the top, who they are and what they hold. Down the
 * left, the queue of things only they can answer, written as ledger lines. Down the middle, the day's
 * tape: the shares that moved, the stories that were written, the money that was paid, each line
 * stamped in the margin. Under it, the board: every share, so the desk can be read without leaving it.
 *
 * Every line on this page is made from something the server really said. Nothing is calculated here
 * that the server would not stand behind.
 */

type Card = { tag: string; when: string; title: string; text: string; action: string; href: string };

/** "Needs you now": built only from things that are really true for this player right now. */
function cardsFor(player: Player, latestQuarter: string | null, live: LiveClock | null, count: number | null,
                  topStory: NewsItem | null, alerts: Watched[], decisions: Card[]): Card[] {
  const all = count ? `All ${count}` : "All the";
  // A decision only this player can make comes before anything else.
  const cards: Card[] = [...decisions];
  if (player.rank_waiting) {
    cards.unshift({
      tag: "◆ Rank case", when: player.build_name ? `Level ${player.level}` : "",
      title: "A rank case is waiting for you",
      text: "Your modules are mastered, so you can sit the case that takes you past your level gate. Or you have one in hand to finish.",
      action: "Open your rank", href: "#/rank",
    });
  }
  if ((player.margin_calls ?? 0) > 0) {
    cards.unshift({
      tag: "■ Margin call", when: "By the next Closing Bell",
      title: player.margin_calls === 1 ? "A margin call is waiting" : `${player.margin_calls} margin calls are waiting`,
      text: "A loan, a short or a contract of yours needs more cash by the next Closing Bell (22:00), or it will be closed for you at the market's price.",
      action: "See what you owe", href: "#/borrow",
    });
  }
  if ((player.press_questions ?? 0) > 0) {
    cards.unshift({
      tag: "● Press", when: "Within a day",
      title: player.press_questions === 1 ? "A journalist has asked your empire a question" : `${player.press_questions} journalists' questions are waiting`,
      text: "Answer on the record, or decline. A question left to run out of time costs the empire a little of its good name.",
      action: "Answer the press", href: "#/news/questions",
    });
  }
  if ((player.crises_due ?? 0) > 0) {
    cards.unshift({
      tag: "■ Statement", when: "Within a day",
      title: "Something has come out about your empire",
      text: "Make a statement for the empire: admitting what is true, quickly, costs least; saying nothing costs a lot.",
      action: "Open the press desk", href: "#/empire/press",
    });
  }
  if ((player.banks_uneasy ?? 0) > 0) {
    cards.unshift({
      tag: "■ Your savings", when: "Today",
      title: "Savers are leaving a bank that holds your money",
      text: "Only the first ₦5 million at each bank is guaranteed. Look at how far each bank is trusted, and decide whether to move your savings.",
      action: "Open your savings", href: "#/portfolio",
    });
  }
  if ((player.corrections_due ?? 0) > 0) {
    cards.unshift({
      tag: "■ Correction", when: "Within a day",
      title: "A story of yours must be corrected",
      text: "The record has changed since you published it. Correct it within a day; a late correction costs more reputation and readers.",
      action: "Open the newsroom", href: "#/news/newsroom",
    });
  }
  if (player.unread_messages > 0) {
    cards.push({
      tag: "● Messages", when: `${player.unread_messages} unread`,
      title: player.unread_messages === 1 ? "A player wrote to you" : `${player.unread_messages} messages waiting`,
      text: "Read and answer from your messages. You can block anyone who bothers you.",
      action: "Read your messages", href: "#/messages",
    });
  }
  if (player.build && player.employer && player.work_in_hand === 0) {
    cards.push({
      tag: "○ Work", when: "This quarter",
      title: "Take on a piece of work",
      text: "Your employer pays a quarter's salary only to staff who finish at least one piece of work in it.",
      action: "See work you can start", href: "#/work",
    });
  }
  // A professional's first need is a build, a bank and an employer: nothing else can be earned without them.
  if (!player.build) {
    cards.unshift({
      tag: "Start here", when: "Three steps",
      title: "Choose your build",
      text: "Asset Manager or Accountant. Then choose your bank and an employer, and you are on salary with work to do.",
      action: "Start your career", href: "#/career",
    });
  } else if (!player.employer) {
    cards.unshift({
      tag: "Career", when: player.build_name ?? "",
      title: "Find an employer",
      text: "Work and salary come through an employer. Choose your bank first, so the employer knows where to pay you.",
      action: "Go to your career", href: "#/career",
    });
  }
  // A price you asked to be told about comes first: it is the one thing here you set yourself.
  for (const alert of alerts) {
    const target = alert.reached === "above" ? alert.alert_above_kobo : alert.alert_below_kobo;
    cards.push({
      tag: "Price alert",
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
      tag: topStory.outlet,
      when: newsDate(topStory),
      title: topStory.headline,
      text: topStory.body,
      action: "Read the news",
      href: "#/news",
    });
  }
  if (latestQuarter) {
    cards.push({
      tag: "Results",
      when: latestQuarter,
      title: `The ${latestQuarter} results are out`,
      text: `${all} companies have filed their accounts. See who grew, who slipped, who lost money and who is in default.`,
      action: "Read the filings",
      href: "#/companies",
    });
  } else {
    cards.push({
      tag: "The world",
      when: live && !live.clock.world_started ? "Not open yet" : "First quarter",
      title: count ? `Get to know the ${count} companies` : "Get to know the companies",
      text: "Each has an opening balance sheet on file. Their first quarterly results arrive one real week after the world opens.",
      action: "See the companies",
      href: "#/companies",
    });
  }
  if (player.profile_icon === null) {
    cards.push({
      tag: "Profile",
      when: "One minute",
      title: "Choose your profile picture",
      text: "Pick the male or the female icon. It is how other players will see you.",
      action: "Choose a picture",
      href: "#/profile",
    });
  }
  return cards;
}

/** The head of the sheet: who you are, and how much of the trading day is left. */
function DeskHead({ player, live, career }: { player: Player; live: LiveClock | null; career: Career | null }) {
  const me = career?.career;
  const date = live?.clock.game_date;
  return (
    <header className="desk-head">
      <div>
        <h1>My desk</h1>
        <div className="desk-who">
          {player.build_name
            ? <span className="mono strong">{player.build_name}{player.level ? ` · L${player.level}` : ""}</span>
            : <span>No build chosen yet</span>}
          {me?.rank_name && <><span className="dot-sep">·</span><span>{me.rank_name}</span></>}
          {career?.job && <><span className="dot-sep">·</span><span>{career.job.name}</span></>}
          {player.empire && <><span className="dot-sep">·</span><span>{player.empire.name}{player.empire.is_head ? " (head)" : ""}</span></>}
          {career?.bank && <span className="desk-who-bank"><span className="dot-sep">·</span> banking at {career.bank.name}</span>}
        </div>
      </div>
      <div className="desk-clock">
        {live ? (
          <>
            {date && (
              <div>
                <span className="mono">Year {date.year} · Q{date.quarter} · Day {date.day_of_quarter}</span>
                <span className="dot-sep"> · </span>
                <span>{MARKET_LABEL[live.clock.market_state]}</span>
              </div>
            )}
            <div>
              {MARKET_LABEL[live.clock.next_state]}{" "}
              <span className="mono">{formatCountdown(live.msToNextChange)}</span>
              {date && <span className="muted"> · at {formatLagosTime(new Date(live.clock.next_change_at), false)} Lagos</span>}
            </div>
          </>
        ) : <div>Connecting to Lagos…</div>}
      </div>
    </header>
  );
}

/** Six figures in one ruled row: the dealer's position, read across in a glance. */
function PositionBand({ player, portfolio, career }: { player: Player; portfolio: Portfolio | null; career: Career | null }) {
  const p = portfolio;
  const days = (p?.net_worth ?? []).slice(-30);
  const last = days.length ? days[days.length - 1].total_kobo : null;
  const before = days.length > 1 ? days[days.length - 2].total_kobo : null;
  const moved = last && before ? BigInt(last) - BigInt(before) : null;
  const invested = p ? (BigInt(p.shares_value_kobo) + BigInt(p.bonds_value_kobo)).toString() : null;
  const retirement = career?.retirement?.value_kobo ?? null;
  const up = moved !== null && moved > 0n;
  const down = moved !== null && moved < 0n;
  return (
    <section className="band" aria-label="What you stand on">
      <div className="band-cell">
        <div className="band-label">Cash</div>
        <div className="band-value">{formatCompact(player.cash.amount_kobo)}</div>
        <div className="band-note">money you can spend now</div>
      </div>
      <div className="band-cell">
        <div className="band-label"><Term word="Net worth">What you own</Term></div>
        <div className="band-value">{p ? formatCompact(p.total_kobo) : "…"}</div>
        <div className="band-note">
          {moved === null
            ? "first figure at tonight’s bell"
            : <><span className={`mono change-${up ? "up" : down ? "down" : "flat"}`}>{up ? "▲" : down ? "▼" : "–"} {formatCompact((moved < 0n ? -moved : moved).toString())}</span> since the last bell</>}
        </div>
      </div>
      <div className="band-cell">
        <div className="band-label">Shares and bonds</div>
        <div className="band-value">{invested ? formatCompact(invested) : "…"}</div>
        <div className="band-note">at today’s prices · <a href="#/portfolio">portfolio</a></div>
      </div>
      <div className="band-cell">
        <div className="band-label">Retirement savings</div>
        <div className="band-value">{retirement ? formatCompact(retirement) : "–"}</div>
        <div className="band-note">{retirement ? "locked until retirement" : "starts with your first salary"}</div>
      </div>
      <div className="band-cell">
        <div className="band-label">Reputation</div>
        <div className="band-value">{player.reputation}<span className="muted"> / 100</span></div>
        <div className="band-note">everyone starts at 50</div>
      </div>
      <div className="band-cell">
        <div className="band-label">The last 30 bells</div>
        <div className="band-spark">
          {days.length >= 2
            ? <Sparkline values={days.map((d) => Number(BigInt(d.total_kobo) / 100n))} width={110} height={22}
                         label={`What you own went from ${formatCompact(days[0].total_kobo)} to ${formatCompact(days[days.length - 1].total_kobo)} over ${days.length} Closing Bells.`} />
            : <span className="band-note">starts tonight</span>}
        </div>
        <div className="band-note">what you own, day by day</div>
      </div>
    </section>
  );
}

/** The queue, written as ledger lines: the first is ruled in crimson, the rest follow in order. */
function NeedsYouNow({ cards }: { cards: Card[] }) {
  if (cards.length === 0) {
    return (
      <section className="needs">
        <div className="needs-head"><h2>Needs you now</h2><span className="needs-count">nothing</span></div>
        <p className="tape-empty">Nothing is waiting on you. The quarter is running; the market opens and closes on its own.</p>
      </section>
    );
  }
  const [first, ...rest] = cards;
  return (
    <section className="needs" aria-labelledby="queue-heading">
      <div className="needs-head">
        <h2 id="queue-heading">Needs you now</h2>
        <span className="needs-count">{cards.length === 1 ? "1 waiting" : `${cards.length} waiting`}</span>
      </div>
      <article className="needs-lead">
        <div className="card-top">
          <span className="card-tag">{first.tag}</span>
          <span className="mono muted small">{first.when}</span>
        </div>
        <h3 className="h3-look">{first.title}</h3>
        <p className="muted small">{first.text}</p>
        <a className="button-primary" href={first.href}>{first.action}</a>
      </article>
      {rest.length > 0 && (
        <ul className="needs-lines">
          {rest.map((card) => (
            <li key={`${card.tag}-${card.title}`}>
              <span className="needs-tag">{card.tag}</span>
              <a href={card.href}>{card.title}</a>
              <span className="needs-when">{card.when}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One line of the tape: a stamp in the margin, a line of fact, and the figure it comes to. */
function TapeLine({ stamp, href, text, figure, wire = false }: {
  stamp: string; href?: string; text: ReactNode; figure: ReactNode; wire?: boolean;
}) {
  return (
    <div className={wire ? "tape-row wire" : "tape-row"}>
      {href ? <a className="tape-stamp" href={href}>{stamp}</a> : <span className="tape-stamp">{stamp}</span>}
      <span className="tape-text">{text}</span>
      <span className={wire ? "tape-figure wire" : "tape-figure"}>{figure}</span>
    </div>
  );
}

/**
 * The day's tape. Three bands down one ruled column: what moved, what was written, what you were paid.
 * It is made only from what the game knows: the market's prices, the wire's stories, and the player's own
 * ledger. Where the game knows the time, the time is shown; where it only knows the day, the day is shown.
 */
function Tape({ market, news, movements }: { market: Market | null; news: NewsItem[] | null; movements: Movement[] | null }) {
  const shares = market?.shares ?? [];
  const moved = shares
    .filter((s) => s.volume > 0 && s.change_bps !== 0)
    .sort((a, b) => Math.abs(b.change_bps) - Math.abs(a.change_bps))
    .slice(0, 6);
  const seen = new Set<string>();
  const written = (news ?? []).filter((item) => {
    const key = `${item.story}|${item.kind}|${item.period}`;
    return seen.has(key) ? false : (seen.add(key), true);
  }).slice(0, 5);
  const paid = (movements ?? []).slice(0, 4);
  return (
    <section className="tape" aria-labelledby="tape-heading">
      <div className="tape-head">
        <h2 id="tape-heading">The day’s tape</h2>
        {market && (
          <div className="tape-quote">
            <span>BSX 50 <b>{market.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b></span>
            <Change bps={market.trades > 0 ? market.index_change_bps : null} />
            <span><span className="mono">{market.volume.toLocaleString("en-NG")}</span> shares traded</span>
            <span><span className="mono">{market.trades.toLocaleString("en-NG")}</span> trades</span>
          </div>
        )}
      </div>

      <div className="tape-band">
        <p className="tape-gutter">now</p>
        <div className="tape-lines">
          {market === null && <p className="tape-empty">Reading the exchange…</p>}
          {market && moved.length === 0 && <p className="tape-empty">Nothing has traded today yet. Orders placed while the market is closed wait for the opening auction.</p>}
          {moved.map((s) => (
            <TapeLine key={s.ticker} stamp={s.ticker} href={`#/companies/${s.ticker}`}
              text={<><span className="tape-name">{s.name} · </span>{s.volume.toLocaleString("en-NG")} shares</>}
              figure={<>{formatNaira(s.price_kobo)} <Change bps={s.change_bps} /></>} />
          ))}
        </div>
      </div>

      <div className="tape-band">
        <p className="tape-gutter">wire</p>
        <div className="tape-lines">
          {written.length === 0 && <p className="tape-empty">Nothing written yet today. The wire fills up as the world turns.</p>}
          {written.map((item, index) => (
            <TapeLine key={`${item.story}-${index}`} wire stamp={`d${item.day}`} href="#/news"
              text={item.headline} figure={item.outlet} />
          ))}
        </div>
      </div>

      <div className="tape-band">
        <p className="tape-gutter">ledger</p>
        <div className="tape-lines">
          {paid.length === 0 && <p className="tape-empty">No money has moved yet. Your pay, your trades and your fees will show here.</p>}
          {paid.map((m, index) => {
            const incoming = !m.amount_kobo.startsWith("-");
            return (
              <TapeLine key={`${m.at}-${index}`} stamp={formatLagosTime(new Date(m.at), false)}
                text={<>{m.memo} <span className="tape-name">· {incoming ? "paid by" : "paid to"} {m.counterparty}</span></>}
                figure={<span className={incoming ? "change-up" : "change-down"}>{incoming ? "+" : ""}{formatNaira(m.amount_kobo)}</span>} />
            );
          })}
        </div>
      </div>

      <div className="tape-foot">
        <a href="#/market">The whole market</a>
        <a href="#/news">Read the wire</a>
      </div>
    </section>
  );
}

/** The book: the shares the player asked to be told about, each with its last five days as a line. */
function Book({ watched, market }: { watched: Watched[]; market: Market | null }) {
  const closes = new Map((market?.shares ?? []).map((s) => [s.ticker, s.closes.map(Number)]));
  return (
    <Panel title="What you are watching" aside={<a href="#/market">Open the market</a>}>
      {watched.length === 0 ? (
        <p className="muted small">Nothing yet. Press ☆ beside a company on the market page, or on its own page, to keep an eye on it here.</p>
      ) : (
        <div className="scroll" tabIndex={0}>
          <table className="dense">
            <thead>
              <tr>
                <th scope="col">Code</th><th scope="col">Company</th>
                <th scope="col" className="num">Price</th><th scope="col" className="num">Today</th>
                <th scope="col">Last 5 days</th>
              </tr>
            </thead>
            <tbody>
              {watched.map((w) => (
                <tr key={w.ticker} className={w.reached ? "row-alert" : undefined}>
                  <td className="mono strong"><a href={`#/companies/${w.ticker}`}>{w.ticker}</a></td>
                  <th scope="row">{w.name}{w.reached && <div className="small">{w.reached === "above" ? "▲ Reached" : "▼ Fell to"} your price</div>}</th>
                  <td className="num mono">{formatNaira(w.price_kobo)}</td>
                  <td className="num"><Change bps={w.change_bps} /></td>
                  <td className="book-spark"><Sparkline values={closes.get(w.ticker) ?? []} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/** The board: every share on one page, sorted by what the reader asks for. */
type BoardField = "price" | "change" | "value";

function Board({ market }: { market: Market | null }) {
  const [field, setField] = useState<BoardField>("change");
  const [descending, setDescending] = useState(true);
  if (!market) return <Panel title="The board"><Loading what="the shares" /></Panel>;
  const measure = (s: Market["shares"][number]) =>
    field === "price" ? Number(s.price_kobo) : field === "value" ? Number(s.market_value_kobo) : s.change_bps;
  const rows = [...market.shares].sort((a, b) => (measure(a) - measure(b)) * (descending ? -1 : 1));
  const pick = (next: BoardField) => {
    if (next === field) setDescending((d) => !d);
    else { setField(next); setDescending(true); }
  };
  const asking = (next: BoardField) => (field === next ? (descending ? " ▼" : " ▲") : "");
  const order = (next: BoardField) => (field === next ? (descending ? "descending" : "ascending") : "none");
  return (
    <Panel title={`The board · ${rows.length} shares`} aside={<a href="#/market">Sort it every way</a>}>
      <div className="scroll" tabIndex={0}>
        <table className="dense">
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Company</th>
              <th scope="col" className="num" aria-sort={order("price")}><button className="sort-head" onClick={() => pick("price")}>Price{asking("price")}</button></th>
              <th scope="col" className="num" aria-sort={order("change")}><button className="sort-head" onClick={() => pick("change")}>Today{asking("change")}</button></th>
              <th scope="col" className="num" aria-sort={order("value")}><button className="sort-head" onClick={() => pick("value")}>Worth{asking("value")}</button></th>
              <th scope="col">Rating</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.ticker}>
                <td className="mono strong"><a href={`#/companies/${s.ticker}`}>{s.ticker}</a></td>
                <th scope="row" className="company-cell">{s.name}</th>
                <td className="num mono">{formatNaira(s.price_kobo)}</td>
                <td className="num"><Change bps={s.change_bps} /></td>
                <td className="num mono">{formatCompact(s.market_value_kobo)}</td>
                <td><Rating value={s.credit_rating ?? "—"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/** Every naira in and out, newest first: the player's own page of the ledger. */
function Account({ player, movements, loading, error, reload }: {
  player: Player; movements: Movement[] | null; loading: boolean; error: string | null; reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Panel title="Your account" aside={<span className="mono">{formatNaira(player.cash.amount_kobo)} cash</span>}>
      <button className="row-button" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="small muted">{open ? "Hide every naira in and out" : "Show every naira in and out"}</span>
      </button>
      {open && (
        <>
          {loading && <Loading what="your account" />}
          {error && <Failed message={error} onRetry={reload} />}
          {movements && (
            <div className="scroll" tabIndex={0}>
              <table className="dense">
                <thead>
                  <tr>
                    <th scope="col">When (Lagos)</th>
                    <th scope="col">What</th>
                    <th scope="col">Paid by / paid to</th>
                    <th scope="col" className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map((m, index) => {
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
        </>
      )}
    </Panel>
  );
}

export function DeskWork({ player, live, onLoggedOut }: { player: Player; live: LiveClock | null; onLoggedOut: () => void }) {
  const status = useLoad(api.worldStatus, "status", onLoggedOut);
  const market = useLoad(api.market, "market", onLoggedOut);
  const news = useLoad(() => api.news({ limit: 40 }), "desk-news", onLoggedOut);
  const watched = useLoad(api.watchlist, "watchlist", onLoggedOut);
  const alerts = (watched.data ?? []).filter((w) => w.reached !== null);
  const corporate = useLoad(api.corporate, "desk-corporate", onLoggedOut);
  const portfolio = useLoad(api.portfolio, "portfolio", onLoggedOut);
  const career = useLoad(api.career, "desk-career", onLoggedOut);
  const movements = useLoad(api.movements, `movements:${player.cash.amount_kobo}`, onLoggedOut);

  const decisions: Card[] = [];
  for (const bid of corporate.data?.takeovers ?? []) {
    if (bid.status === "open" && bid.free + bid.offered > 0) {
      decisions.push({
        tag: bid.hostile ? "Hostile bid" : "Takeover offer", when: formatNaira(bid.price_kobo),
        title: `${bid.bidder} has offered ${formatNaira(bid.price_kobo)} a share for ${bid.target}`,
        text: `You hold shares in ${bid.target}. ${bid.offered > 0 ? `You have offered ${bid.offered.toLocaleString("en-NG")} of them.` : "You have not answered yet."} The offer closes ${bid.closes_label}.`,
        action: "Answer the offer", href: "#/market/offers",
      });
    }
  }
  for (const vote of corporate.data?.votes ?? []) {
    if (vote.status === "open" && vote.my_shares > 0 && !vote.my_choice) {
      decisions.push({
        tag: "Your vote", when: vote.name, title: vote.question,
        text: `You hold ${vote.my_shares.toLocaleString("en-NG")} shares, so you have a vote. It is counted ${vote.closes_label}.`,
        action: "Vote", href: "#/market/offers",
      });
    }
  }
  const quarter = status.data?.last_closed_label ?? null;
  // The top story: the most important item of the last three game days, if it matters enough to interrupt.
  const items = news.data?.items ?? [];
  const recent = items.length ? items.filter((item) => item.period === items[0].period && item.day >= items[0].day - 2) : [];
  const top = recent.reduce<NewsItem | null>((best, item) => (!best || item.importance > best.importance ? item : best), null);
  const cards = cardsFor(player, quarter, live, status.data?.companies ?? null, top && top.importance >= 60 ? top : null, alerts, decisions);

  return (
    <div className="desk">
      <DeskHead player={player} live={live} career={career.data} />
      <PositionBand player={player} portfolio={portfolio.data} career={career.data} />
      <div className="desk-grid">
        <div className="desk-col">
          <NeedsYouNow cards={cards} />
          <Book watched={watched.data ?? []} market={market.data} />
          <GrantPanel onLoggedOut={onLoggedOut} onChanged={() => undefined} />
        </div>
        <div className="desk-col">
          <Tape market={market.data} news={news.data?.items ?? null} movements={movements.data} />
          <Board market={market.data} />
        </div>
      </div>
      <ClosingBellPanel onLoggedOut={onLoggedOut} brief />
      <Account player={player} movements={movements.data} loading={movements.loading} error={movements.error} reload={movements.reload} />
    </div>
  );
}

const SESSIONS = [
  { state: "opening_auction", name: "Opening auction", hours: "11:30 to 12:00" },
  { state: "open", name: "Open", hours: "12:00 to 22:00" },
  { state: "closed", name: "Closed", hours: "22:00 to 11:30" },
] as const;

/** The rail beside the desk: the exchange's hours, the calendar, and how the player stands. */
export function DeskRail({ player, live, onLoggedOut }: { player: Player; live: LiveClock | null; onLoggedOut: () => void }) {
  const date = live?.clock.game_date;
  const career = useLoad(api.career, "desk-career", onLoggedOut);
  const me = career.data?.career;
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
        <div className="row"><span>One real week</span><span className="mono">one game quarter</span></div>
        <div className="row"><span>Four real weeks</span><span className="mono">one game year</span></div>
      </Panel>

      <Panel title="Your standing">
        <div className="row"><span>Reputation</span><span className="mono">{player.reputation} / 100</span></div>
        {me && <div className="row"><span>Level</span><span className="mono">{me.level} · {me.rank_name}</span></div>}
        {career.data?.job && <div className="row"><span>Employer</span><span>{career.data.job.name}</span></div>}
        {career.data?.bank && <div className="row"><span>Bank</span><span>{career.data.bank.name}</span></div>}
        <p className="muted small">Reputation rises and falls with what you do. <a href="#/rank">Your rank</a> shows what comes next.</p>
      </Panel>
    </>
  );
}
