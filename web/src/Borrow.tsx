// Stage 9, Part A: borrowing and short selling. A personal loan against salary; a loan against shares and bonds
// with its margin-call levels shown on a meter; borrowing shares from the pension funds to sell short; and, for an
// empire's Asset Manager or head, the same inside the Risk Manager's limits. The server checks every limit.

import { useState } from "react";
import { api, ApiError, type BorrowingDesk as Borrowing, type LendingBook, type Player } from "./api";
import { DebtsPanel } from "./Debts";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";
import { WhatCouldHappenPanel } from "./WhatIf";

type Props = { player: Player; onLoggedOut: () => void; onChanged?: () => void };
type Tab = "loans" | "shorts" | "empire";

function useAct(reload: () => void, onLoggedOut: () => void, onChanged?: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(path: string, body: unknown, done: string, waiting = "Above the Risk Manager's limit: it has gone to the head to decide.") {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await api.post(path, body);
      const result = answer.result as { waiting?: boolean } | null;
      setNotice(result && result.waiting ? waiting : done);
      reload();
      onChanged?.();
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
type Act = ReturnType<typeof useAct>;

const pct = (bps: number) => formatPercent(bps, 0);

/** The loan against holdings on a meter: where it stands, and the call and forced-sale marks. Shapes and words, not colour alone. */
function MarginMeter({ ratio, call, sell }: { ratio: number; call: number; sell: number }) {
  const width = Math.min(ratio / 100, 100);
  const state = ratio >= sell ? "■ Shares will be sold" : ratio >= call ? "▲ Margin call" : "● Safe";
  return (
    <div className="margin-meter">
      <div className="row small"><span>The loan, against shares, bonds and cash</span><span className="mono">{pct(ratio)} · {state}</span></div>
      <div className="meter meter-marked" role="img" aria-label={`The loan is ${pct(ratio)} of what is held. A margin call at ${pct(call)}; shares are sold at ${pct(sell)}.`}>
        <div className={`meter-fill${ratio >= call ? " meter-loss" : ""}`} style={{ width: `${width}%` }} />
        <span className="meter-mark" style={{ left: `${call / 100}%` }} title="Margin call" />
        <span className="meter-mark meter-mark-strong" style={{ left: `${sell / 100}%` }} title="Forced sale" />
      </div>
      <div className="row small muted"><span>0%</span><span>call at {pct(call)} · sale at {pct(sell)}</span><span>100%</span></div>
    </div>
  );
}

function LoansTab({ b, act, forEmpire = false, book }: { b: Borrowing; act: Act; forEmpire?: boolean; book: LendingBook }) {
  const [personal, setPersonal] = useState("");
  const [margin, setMargin] = useState("");
  const [bank, setBank] = useState("");
  return (
    <>
      <section className="band band-4" aria-label={forEmpire ? "What the empire owes" : "What you owe"}>
        <div className="band-cell">
          <div className="band-label">{forEmpire ? "The empire’s worth, after all debts" : "Your worth, after all debts"}</div>
          <div className="band-value">{formatCompact(book.equity)}</div>
          <div className="band-note">what would be left if every debt were paid</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Owed in all</div>
          <div className="band-value">{formatCompact(book.debts)}</div>
          <div className="band-note">borrowing may be at most {book.most_debt_times}× what is worth</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Borrowed against shares</div>
          <div className="band-value">{formatCompact(book.margin.owed)}</div>
          <div className="band-note">{formatCompact(book.margin.limit)} more available</div>
        </div>
        <div className="band-cell">
          <div className="band-label">The loan, against what is held</div>
          <div className={`band-value${book.margin.ratio_bps >= book.margin.call_bps ? " change-down" : ""}`}>
            {book.margin.ratio_bps >= book.margin.sell_bps ? "■ " : book.margin.ratio_bps >= book.margin.call_bps ? "▲ " : "● "}{pct(book.margin.ratio_bps)}
          </div>
          <div className="band-note">call at {pct(book.margin.call_bps)} · sale at {pct(book.margin.sell_bps)}</div>
        </div>
      </section>
      <MarginMeter ratio={book.margin.ratio_bps} call={book.margin.call_bps} sell={book.margin.sell_bps} />
      {!forEmpire && (
        <Panel title="A personal loan" aside={`${formatPercent(book.rates.personal_bps)} a year · repaid over two years`}>
          <p className="small">From your bank{b.my_bank ? ` (${b.my_bank})` : ""}, against your salary: at most a year's salary, and no more than four years' salary with any mortgage. You can borrow {formatNaira(book.personal_limit)} more now.</p>
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(personal); if (k) act.run("/borrowing/personal", { amount_kobo: k }, "Borrowed. It is repaid in eight parts, one each quarter."); }}>
            <label className="answer">Amount (₦)<input type="text" inputMode="decimal" value={personal} onChange={(e) => setPersonal(e.target.value)} /></label>
            <button className="button-primary" disabled={act.busy || !asKobo(personal)}>Borrow</button>
          </form>
        </Panel>
      )}
      <Panel title="A loan against shares and bonds" aside={`${formatPercent(book.rates.margin_bps)} a year · repay when you like`}>
        <p className="small">Up to half the value of the shares and bonds held. They stay {forEmpire ? "the empire's" : "yours"} (with their dividends and votes). At every Closing Bell the loan is measured against shares, bonds and cash: at {pct(book.margin.call_bps)} a margin call, at {pct(book.margin.sell_bps)} (or a call not met by the next bell) shares are sold at 5% below the close.</p>
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(margin); if (k && bank) act.run("/borrowing/margin", { bank, amount_kobo: k, for_empire: forEmpire }, "Borrowed against the holdings."); }}>
          <label>Bank<select value={bank} onChange={(e) => setBank(e.target.value)}><option value="">Choose…</option>{b.banks.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <label className="answer">Amount (₦)<input type="text" inputMode="decimal" value={margin} onChange={(e) => setMargin(e.target.value)} placeholder={`up to ${formatNaira(book.margin.limit)}`} /></label>
          <button className="button-primary" disabled={act.busy || !asKobo(margin) || !bank}>Borrow</button>
        </form>
      </Panel>
    </>
  );
}

function ShortsTab({ b, act, forEmpire = false, book, initialTicker }: { b: Borrowing; act: Act; forEmpire?: boolean; book: LendingBook; initialTicker?: string }) {
  const [ticker, setTicker] = useState(initialTicker ?? "");
  const [shares, setShares] = useState("");
  const [more, setMore] = useState<Record<number, string>>({});
  const chosen = b.lendable.find((l) => l.ticker === ticker);
  const count = Number(shares);
  const needed = chosen && count > 0 ? (BigInt(chosen.price) * BigInt(Math.floor(count)) * 3n / 2n).toString() : null;
  const collateral = book.shorts.reduce((n, s) => n + BigInt(s.collateral), 0n);
  const gain = book.shorts.reduce((n, s) => n + BigInt(s.gain), 0n);
  return (
    <>
      <section className="band band-4" aria-label="Short selling">
        <div className="band-cell">
          <div className="band-label">Fee to borrow shares</div>
          <div className="band-value">{formatPercent(book.rates.short_fee_bps)}</div>
          <div className="band-note">a year, paid to the pension funds who lend them</div>
        </div>
        <div className="band-cell">
          <div className="band-label">{forEmpire ? "The empire’s open shorts" : "Your open shorts"}</div>
          <div className="band-value">{book.shorts.length.toLocaleString("en-NG")}</div>
          <div className="band-note">{book.shorts.length === 0 ? "none borrowed to sell today" : "each holds 150% of its value in cash"}</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Cash held as collateral</div>
          <div className="band-value">{formatCompact(collateral.toString())}</div>
          <div className="band-note">returned when the shares are given back</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Gain if bought back now</div>
          <div className={`band-value${book.shorts.length === 0 || gain === 0n ? " muted" : gain < 0n ? " change-down" : " change-up"}`}>
            {book.shorts.length === 0 ? "—" : `${gain < 0n ? "▼ " : gain > 0n ? "▲ " : ""}${formatCompact(gain.toString().replace("-", ""))}`}
          </div>
          <div className="band-note">
            {book.shorts.length === 0 ? "nothing to buy back yet" : gain === 0n ? "the price has not moved since they were borrowed" : "on paper, until you give the shares back"}
          </div>
        </div>
      </section>
      <Panel title="Sell short: borrow shares to sell" aside={`fee ${formatPercent(book.rates.short_fee_bps)} a year`}>
        <p className="small"><Term word="Short selling">Selling short</Term> is a bet that a price will fall: borrow shares from the pension funds, sell them, and later buy them back (cheaper, you hope) to give back. You hold 150% of their value in cash while they are borrowed. Below 125% a margin call; below 110%, or a call not met by the next bell, they are bought back for you at 5% above the close. You pay the lender any dividend, and the funds can recall the shares.</p>
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (ticker && count > 0) act.run("/shorts", { ticker, shares: Math.floor(count), for_empire: forEmpire }, "Borrowed. Sell them on the company's page (they are in your holdings), and give them back when you close."); }}>
          <label>Share<select value={ticker} onChange={(e) => setTicker(e.target.value)}><option value="">Choose…</option>{b.lendable.filter((l) => l.lendable > 0).map((l) => <option key={l.ticker} value={l.ticker}>{l.ticker} · {l.name}</option>)}</select></label>
          <label className="answer">Shares<input type="number" min={1} value={shares} onChange={(e) => setShares(e.target.value)} /></label>
          <button className="button-primary" disabled={act.busy || !ticker || !(count > 0)}>Borrow to sell</button>
          {chosen && <span className="muted small">At {formatNaira(chosen.price)}: up to {chosen.lendable.toLocaleString("en-NG")} can be borrowed now{needed ? `; this needs ${formatNaira(needed)} held` : ""}.</span>}
        </form>
      </Panel>
      {book.shorts.length > 0 && (
        <Panel title="Open shorts">
          {book.shorts.map((s) => (
            <div key={s.id} className="report">
              <div className="row small"><span><strong>{s.ticker}</strong> · {s.shares.toLocaleString("en-NG")} shares borrowed at {formatNaira(s.opened_price)}</span>
                <span className={`tag tag-${s.margin_call || s.recalled ? "missed" : "open"}`}>{s.recalled ? "▲ recalled" : s.margin_call ? "▲ margin call" : "open"}</span></div>
              <div className="row small"><span>Price now</span><span className="mono">{formatNaira(s.price)}</span></div>
              <div className="row small"><span>Gain if bought back now</span><span className={`mono ${BigInt(s.gain) > 0n ? "change-up" : BigInt(s.gain) < 0n ? "change-down" : "muted"}`}>{BigInt(s.gain) > 0n ? "▲ " : BigInt(s.gain) < 0n ? "▼ " : ""}{formatNaira(s.gain.replace("-", ""))}</span></div>
              <div className="row small"><span>Collateral held</span><span className="mono">{formatNaira(s.collateral)} · {pct(s.cover_bps)} of their value</span></div>
              <div className="inline-form">
                <button className="button-outline" disabled={act.busy} onClick={() => act.run(`/shorts/${s.id}/close`, { for_empire: forEmpire }, "Given back, and the collateral returned.")}>Give the shares back</button>
                <input className="small-input" type="text" inputMode="decimal" aria-label="More collateral (₦)" placeholder="₦" value={more[s.id] ?? ""} onChange={(e) => setMore({ ...more, [s.id]: e.target.value })} />
                <button className="button-quiet" disabled={act.busy || !asKobo(more[s.id] ?? "")} onClick={() => act.run(`/shorts/${s.id}/collateral`, { amount_kobo: asKobo(more[s.id] ?? ""), for_empire: forEmpire }, "Collateral added.")}>Add collateral</button>
              </div>
              <p className="muted small">To give them back, hold them again: buy them on the company's page first.</p>
            </div>
          ))}
        </Panel>
      )}
      <Panel title="What can be borrowed" aside="short interest: lent out as a share of all shares (never who)">
        <div className="scroll scroll-sticky" tabIndex={0}>
          <table className="dense tape-table">
            <thead><tr><th scope="col">Share</th><th scope="col">Company</th><th scope="col" className="num">Price</th><th scope="col" className="num">Can be borrowed</th><th scope="col" className="num">Short interest</th></tr></thead>
            <tbody>
              {b.lendable.map((l) => (
                <tr key={l.ticker}><td className="mono strong">{l.ticker}</td><th scope="row">{l.name}</th><td className="num mono">{formatNaira(l.price)}</td>
                  <td className="num mono">{l.lendable.toLocaleString("en-NG")}</td><td className="num mono">{formatPercent(l.short_interest_bps, 2)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

function EmpireTab({ b, act }: { b: Borrowing; act: Act }) {
  const e = b.empire!;
  const [borrowLimit, setBorrowLimit] = useState(String(e.limits.borrow_limit_naira ?? 0));
  const [shortLimit, setShortLimit] = useState(String(e.limits.short_limit_naira ?? 0));
  const [derivLimit, setDerivLimit] = useState(String(e.limits.derivatives_limit_naira ?? 0));
  return (
    <>
      <Panel title={`${e.name}: the Risk Manager's limits`} aside={e.sets_limits ? "You sign them" : "The Risk Manager signs them"}>
        <div className="row small"><span>Borrowing against holdings, at most</span><span className="mono">₦{Number(e.limits.borrow_limit_naira ?? 0).toLocaleString("en-NG")}</span></div>
        <div className="row small"><span>Short sales, worth at most</span><span className="mono">₦{Number(e.limits.short_limit_naira ?? 0).toLocaleString("en-NG")}</span></div>
        <div className="row small"><span>Options and futures, committed at most</span><span className="mono">₦{Number(e.limits.derivatives_limit_naira ?? 0).toLocaleString("en-NG")}</span></div>
        {e.sets_limits && (
          <form className="inline-form" onSubmit={(ev) => { ev.preventDefault(); act.run("/empire/limits", { borrow_naira: Number(borrowLimit) || 0, short_naira: Number(shortLimit) || 0, derivatives_naira: Number(derivLimit) || 0 }, "The limits are signed.", "Raising a limit needs the head: it has gone to them to approve. (Lowering one takes effect at once.)"); }}>
            <label>Borrowing (₦)<input className="small-input" type="number" min={0} value={borrowLimit} onChange={(ev) => setBorrowLimit(ev.target.value)} /></label>
            <label>Short sales (₦)<input className="small-input" type="number" min={0} value={shortLimit} onChange={(ev) => setShortLimit(ev.target.value)} /></label>
            <label>Options and futures (₦)<input className="small-input" type="number" min={0} value={derivLimit} onChange={(ev) => setDerivLimit(ev.target.value)} /></label>
            <button className="button-primary" disabled={act.busy}>Sign the limits</button>
          </form>
        )}
        <p className="muted small">Inside these the Asset Manager borrows and sells short for the empire; above them, the head decides.</p>
      </Panel>
      {e.acts && e.book ? (
        <>
          <LoansTab b={b} act={act} forEmpire book={e.book} />
          <ShortsTab b={b} act={act} forEmpire book={e.book} />
        </>
      ) : <p className="muted">The Asset Manager and the head borrow and sell short for the empire.</p>}
    </>
  );
}

export function BorrowWork({ player, onLoggedOut, onChanged }: Props) {
  const { data: b, error, loading, reload } = useLoad(api.borrowing, "borrowing", onLoggedOut);
  const act = useAct(reload, onLoggedOut, onChanged);
  const route = window.location.hash.split("/");
  const [tab, setTab] = useState<Tab>(() => (["loans", "shorts", "empire"].includes(route[2] ?? "") ? route[2] : "loans") as Tab);
  const initialTicker = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("ticker") ?? undefined;
  const choose = (next: Tab) => { setTab(next); window.history.replaceState(null, "", `#/borrow/${next}`); };
  if (loading && !b) return <Loading what="your borrowing" />;
  if (error && !b) return <Failed message={error} onRetry={reload} />;
  if (!b) return null;
  const tabs: [Tab, string][] = [["loans", "Loans"], ["shorts", "Short selling"], ...(b.empire ? [["empire", "For the empire"] as [Tab, string]] : [])];
  return (
    <>
      <div className="work-head">
        <div>
          <h1>Borrow</h1>
          <div className="work-sub">
            Loans against your salary or your shares, and borrowing shares to sell short
          </div>
        </div>
        {tab === "loans" && <span className="muted small">a personal loan is repaid over two years; a loan against shares, when you like</span>}
      </div>

      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
      {b.events.length > 0 && (
        <Panel title="Notices">
          {b.events.slice(0, 4).map((ev, i) => <p key={i} className={`small${ev.kind.includes("call") || ev.kind === "default" || ev.kind === "recall" ? " error" : ""}`}>{ev.words}</p>)}
        </Panel>
      )}
      <div className="underline-tabs" role="tablist" aria-label="Borrowing">
        {tabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : undefined} onClick={() => choose(key)}>{label}</button>)}
      </div>
      {/* What is already owed comes first, above any offer to lend more. It was at the foot of this
          page until 9 November 2026, which is how the owner came to ask where a loan is repaid. */}
      <DebtsPanel player={player} onLoggedOut={onLoggedOut} onChanged={onChanged} book={b} where="borrow" />
      {tab === "loans" && <LoansTab b={b} act={act} book={b} />}
      {tab === "shorts" && <ShortsTab b={b} act={act} book={b} initialTicker={initialTicker} />}
      {tab === "empire" && b.empire && <EmpireTab b={b} act={act} />}
    </>
  );
}

export function BorrowRail({ onLoggedOut }: { onLoggedOut: () => void }) {
  return <WhatCouldHappenPanel what="portfolio" title="What could happen to what you hold?" onLoggedOut={onLoggedOut} />;
}
