// The desk screen (design document, section 12). The day's tape: what moved, what the wire wrote, and
// what money moved. Built for the terminal's clothes, as the redesign asks: a page head, then banded
// tape rows stamped in the margin, exactly as the company page's own tape is stamped, so the desk
// speaks one language rather than inventing a second. The right-hand rail comes from App.tsx.

import type { ReactNode } from "react";
import { api, type Player } from "./api";
import { DebtsPanel } from "./Debts";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { WatchlistPanel } from "./Market";
import { Change, Failed, Loading, PageHead } from "./Shell";
import { useClock, type LiveClock } from "./useClock";

type Props = { player: Player; live: LiveClock | null; onLoggedOut: () => void; onChanged?: () => void };

/** One line of the tape: a stamp in the margin, a line of text that leads somewhere, and a figure on the right. */
function TapeRow({ stamp, href, text, figure }: { stamp: string; href: string; text: ReactNode; figure: ReactNode }) {
  return (
    <div className="tape-row">
      <span className="tape-stamp">{stamp}</span>
      <a className="tape-text" href={href}>{text}</a>
      <span className="tape-figure">{figure}</span>
    </div>
  );
}

function TapeBand({ gutter, children }: { gutter: string; children: ReactNode }) {
  return (
    <div className="tape-band">
      <p className="tape-gutter">{gutter}</p>
      <div className="tape-lines">{children}</div>
    </div>
  );
}

export function DeskWork({ player, live, onLoggedOut, onChanged }: Props) {
  const clock = live ?? useClock();     // App already keeps a clock; fall back to one of its own only when it has none
  const ticker = useLoad(api.ticker, `desk-ticker:${player.cash.amount_kobo}`, onLoggedOut);
  const news = useLoad(() => api.news({ limit: 40 }), "desk-news", onLoggedOut);
  const paid = useLoad(api.movements, `desk-movements:${player.cash.amount_kobo}`, onLoggedOut);

  if (ticker.loading && !ticker.data && news.loading && !news.data) return <Loading what="the day's tape" />;
  if (ticker.error && !ticker.data) return <Failed message={ticker.error} onRetry={ticker.reload} />;

  const market = ticker.data;
  const moved = (market?.shares ?? []).filter((s) => s.traded_today && s.change_bps !== 0).slice(0, 8);
  const written = (news.data?.items ?? []).slice(0, 6);
  const money = (paid.data ?? []).slice(0, 6);
  const today = clock?.now
    ? clock.now.toLocaleDateString("en-NG", { weekday: "short", day: "numeric", month: "short" })
    : "today";

  return (
    <>
      <PageHead title="Desk"
                sub="The day's tape: what moved on the exchange, what the wire wrote, and what money moved"
                aside={market ? `BSX 50 ${market.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined} />

      {/* A debt you cannot find the way out of is a trap, not a mechanic. This sits above the tape and
          draws nothing at all when nothing is owed. */}
      <DebtsPanel player={player} onLoggedOut={onLoggedOut} onChanged={onChanged} where="desk" />

      <section className="tape" aria-labelledby="tape-heading">
        <div className="tape-head">
          <h2 id="tape-heading">The day&rsquo;s tape</h2>
          <span className="muted small">{today} · {market?.market_state === "open" ? "The exchange is open" : "The exchange is closed"}</span>
        </div>

        <TapeBand gutter="market">
          {market && moved.length === 0 && (
            <p className="tape-empty">Nothing has moved today yet. Orders placed while the exchange is closed wait for the opening auction.</p>
          )}
          {moved.map((s) => (
            <TapeRow key={s.ticker} stamp={s.ticker} href={`#/companies/${s.ticker}`}
                     text={<span className="tape-name">{s.name}</span>}
                     figure={<>{formatNaira(s.price_kobo)} <Change bps={s.change_bps} /></>} />
          ))}
        </TapeBand>

        <TapeBand gutter="wire">
          {written.length === 0 && <p className="tape-empty">Nothing written yet today. The wire fills up as the world turns.</p>}
          {written.map((item, index) => (
            <TapeRow key={`${item.story}-${index}`} stamp={`d${item.day}`} href="#/news"
                     text={item.headline} figure={item.outlet} />
          ))}
        </TapeBand>

        <TapeBand gutter="ledger">
          {money.length === 0 && <p className="tape-empty">No money has moved yet. Your pay, your trades and your fees will show here.</p>}
          {money.map((m, index) => {
            const incoming = !m.amount_kobo.startsWith("-");
            const where = m.counterparty ? ` ${incoming ? "from" : "to"} ${m.counterparty}` : "";
            return (
              <TapeRow key={`${m.at}-${index}`} stamp={m.kind} href="#/portfolio"
                       text={<>{incoming ? "Received" : "Paid"}{where}</>}
                       figure={<span className={incoming ? "change-up" : "change-down"}>{incoming ? "▲" : "▼"} {formatNaira(m.amount_kobo.replace("-", ""))}</span>} />
            );
          })}
        </TapeBand>
      </section>
    </>
  );
}

export function DeskRail({ onLoggedOut }: { player: Player; live: LiveClock | null; onLoggedOut: () => void }) {
  return <WatchlistPanel onLoggedOut={onLoggedOut} />;
}
