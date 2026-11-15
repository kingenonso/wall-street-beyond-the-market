// The desk screen (design document, section 12). Since 15 November 2026 it is the terminal (Terminal.tsx): what
// moved and what the wire wrote are its monitor and its wire, and the tape below keeps what money moved. Built for the terminal's clothes, as the redesign asks: a page head, then banded
// tape rows stamped in the margin, exactly as the company page's own tape is stamped, so the desk
// speaks one language rather than inventing a second. The right-hand rail comes from App.tsx.

import type { ReactNode } from "react";
import { api, type Player } from "./api";
import { DebtsPanel } from "./Debts";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { WatchlistPanel } from "./Market";
import { TerminalRail, TerminalWork } from "./Terminal";
import { Failed, Loading, PageHead } from "./Shell";
import { useClock, type LiveClock } from "./useClock";

type Props = { player: Player; live: LiveClock | null; onLoggedOut: () => void; onChanged?: () => void };

/** One line of the tape: a stamp in the margin, a line of text that leads somewhere, and a figure on the right. */
// The money tape's stamp column is narrow: a short word for each kind of payment, never the ledger's code.
const MONEY_WORDS: Record<string, string> = {
  starting_grant: "grant", grant_step: "grant", salary: "pay", professional_fee: "fee", fee: "fee", trade: "trade",
  dividend: "divid.", deposit_interest: "intr.", savings_interest: "intr.", bond_coupon: "coupon", tax: "tax",
  leader_pay: "pay", levy: "levy", lobbying: "lobby", premium: "insur.", claim: "claim", pension: "pension",
};
const moneyWord = (kind: string) => MONEY_WORDS[kind] ?? kind.split("_")[0].slice(0, 7);

function TapeRow({ stamp, href, text, figure }: { stamp: string; href: string; text: ReactNode; figure: ReactNode }) {
  return (
    <div className="tape-row">
      <span className="tape-stamp" title={stamp}>{stamp}</span>
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
  const paid = useLoad(api.movements, `desk-movements:${player.cash.amount_kobo}`, onLoggedOut);

  if (ticker.loading && !ticker.data) return <Loading what="the terminal" />;
  if (ticker.error && !ticker.data) return <Failed message={ticker.error} onRetry={ticker.reload} />;

  const market = ticker.data;
  const money = (paid.data ?? []).slice(0, 6);
  const today = clock?.now
    ? clock.now.toLocaleDateString("en-NG", { weekday: "short", day: "numeric", month: "short" })
    : "today";

  return (
    <>
      <PageHead title="Desk"
                sub="The terminal: one company in the middle, the whole economy around it, and why each thing moved"
                aside={market ? `BSX 50 ${market.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined} />

      {/* A debt you cannot find the way out of is a trap, not a mechanic. This sits above the tape and
          draws nothing at all when nothing is owed. */}
      <DebtsPanel player={player} onLoggedOut={onLoggedOut} onChanged={onChanged} where="desk" />

      <TerminalWork player={player} onLoggedOut={onLoggedOut} />

      <section className="tape" aria-labelledby="tape-heading">
        <div className="tape-head">
          <h2 id="tape-heading">Your money today</h2>
          <span className="muted small">{today} · {market?.market_state === "open" ? "The exchange is open" : "The exchange is closed"}</span>
        </div>

        <TapeBand gutter="ledger">
          {money.length === 0 && <p className="tape-empty">No money has moved yet. Your pay, your trades and your fees will show here.</p>}
          {money.map((m, index) => {
            const incoming = !m.amount_kobo.startsWith("-");
            const where = m.counterparty ? ` ${incoming ? "from" : "to"} ${m.counterparty}` : "";
            return (
              <TapeRow key={`${m.at}-${index}`} stamp={moneyWord(m.kind)} href="#/portfolio"
                       text={<>{incoming ? "Received" : "Paid"}{where}</>}
                       figure={<span className={incoming ? "change-up" : "change-down"}>{incoming ? "▲" : "▼"} {formatNaira(m.amount_kobo.replace("-", ""))}</span>} />
            );
          })}
        </TapeBand>
      </section>
    </>
  );
}

export function DeskRail({ player, onLoggedOut }: { player: Player; live: LiveClock | null; onLoggedOut: () => void }) {
  return (
    <>
      <TerminalRail player={player} onLoggedOut={onLoggedOut} />
      <WatchlistPanel onLoggedOut={onLoggedOut} />
    </>
  );
}
