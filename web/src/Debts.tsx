// What you owe, in one place, with the way to pay it back.
//
// The owner's complaint of 9 November 2026 was plain: "I can't find a place to repay my loan." The
// repay control existed, but it sat at the bottom of Money › Borrow, underneath two large panels
// offering to lend you *more* — so the thing you already owed was the last thing on the page. This
// panel is the correction: every debt the player can settle, listed with the amount, the rate, and a
// box to pay it, in the order they would think of it. It appears on the desk the moment anything is
// owed, and at the top of Borrow, above the borrowing forms.
//
// A mortgage is listed here too, but it is repaid through the property module, so the line links to
// the property page rather than pretending to own that button. The server still decides every amount;
// this file only asks.

import { useState } from "react";
import { api, ApiError, type BorrowingDesk, type Loan, type Player } from "./api";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Panel } from "./Shell";

type Props = {
  player: Player;
  onLoggedOut: () => void;
  onChanged?: () => void;
  /** A borrowing book already read by the page, so the desk does not ask the server twice. */
  book?: BorrowingDesk;
  /** "desk" says only what a player can act on from the front page; "borrow" is the full dress. */
  where?: "desk" | "borrow";
};

const KIND_WORDS: Record<Loan["kind"], string> = {
  personal: "Personal loan",
  margin: "Against shares and bonds",
  shortfall: "Owed for a loss beyond the cash held for it",
};

/** What one loan costs, in the words a player thinks in. */
function loanWords(loan: Loan): string {
  const bits = [KIND_WORDS[loan.kind] ?? "Loan", loan.bank, `${formatPercent(loan.rate_bps, 1)} a year`];
  if (loan.status === "default") bits.push("in default");
  else if (loan.margin_call) bits.push("margin call");
  else if (loan.missed > 0) bits.push(`${loan.missed} missed`);
  return bits.join(" · ");
}

/** The kobo figure as a plain number the server will accept, or null if it will not fit. */
function wholeKobo(amount: string): number | null {
  try {
    const value = BigInt(amount);
    return value > 0n && value <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(value) : null;
  } catch {
    return null;
  }
}

export function DebtsPanel({ player, onLoggedOut, onChanged, book, where = "desk" }: Props) {
  const loaded = useLoad(api.borrowing, `debts:${player.cash.amount_kobo}`, onLoggedOut);
  const b = book ?? loaded.data;
  const [pay, setPay] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // A failure to read is not the desk's business: the borrow page says so in its own words.
  if (!b) return null;

  // The key is how the row is told apart in the amount boxes, since a player's loan 3 and the
  // empire's loan 3 are two different debts.
  type Row = { key: string; id: number; loan: Loan; forEmpire: boolean; empireName?: string };
  const rows: Row[] = [];
  for (const loan of b.loans) rows.push({ key: `p${loan.id}`, id: loan.id, loan, forEmpire: false });
  if (b.empire?.book && b.empire.acts) {
    for (const loan of b.empire.book.loans) {
      rows.push({ key: `e${loan.id}`, id: loan.id, loan, forEmpire: true, empireName: b.empire.name });
    }
  }

  const owedOnLoans = rows.reduce((total, row) => total + BigInt(row.loan.outstanding), 0n);
  const owedInAll = BigInt(b.debts);
  // borrowings the borrowing desk does not settle: mortgages are repaid on the property page.
  const elsewhere = owedInAll > owedOnLoans ? owedInAll - owedOnLoans : 0n;

  if (rows.length === 0 && elsewhere <= 0n) {
    return where === "borrow" ? (
      <Panel title="What you owe" aside="nothing">
        <p className="small">You owe nothing. No loan, no mortgage, no interest running against you.</p>
      </Panel>
    ) : null;
  }

  async function settle(row: Row, amount: number, done: string) {
    setBusy(row.key); setError(null); setNotice(null);
    try {
      await api.post(`/borrowing/loans/${row.id}/repay`, { amount_kobo: amount, for_empire: row.forEmpire });
      setPay((now) => ({ ...now, [row.key]: "" }));
      setNotice(done);
      loaded.reload();
      onChanged?.();
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server.");
    } finally {
      setBusy(null);
    }
  }

  function repay(row: Row, all: boolean) {
    const amount = all ? wholeKobo(row.loan.outstanding) : asKobo(pay[row.key] ?? "");
    if (!amount) return;
    void settle(row, amount, all ? "Paid off in full. The interest stops there." : "Repaid against the loan.");
  }

  return (
    <Panel title="What you owe" aside={`${formatCompact(b.debts)} in all · ${formatCompact(b.equity)} would be left if every debt were paid`}
           className={where === "desk" ? "panel-yours" : undefined}>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="saved" role="status">{notice}</p>}
      {rows.map((row) => {
        const amount = pay[row.key] ?? "";
        return (
          <div key={row.key} className="report">
            <div className="row small">
              <span>{row.empireName ? `${row.empireName}: ` : ""}{loanWords(row.loan)}</span>
              <span className="mono strong">{formatNaira(row.loan.outstanding)}</span>
            </div>
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); repay(row, false); }}>
              <label className="answer">Repay (₦)
                <input type="text" inputMode="decimal" value={amount} placeholder="any amount"
                       onChange={(e) => setPay({ ...pay, [row.key]: e.target.value })} />
              </label>
              <button className="button-outline" disabled={busy !== null || !asKobo(amount)}>Repay this much</button>
              <button type="button" className="button-primary" disabled={busy !== null || wholeKobo(row.loan.outstanding) === null}
                      onClick={() => repay(row, true)}>
                Pay it all off ({formatNaira(row.loan.outstanding)})
              </button>
            </form>
          </div>
        );
      })}
      {elsewhere > 0n && (
        <div className="report">
          <div className="row small">
            <span>Owed on property, as a mortgage</span>
            <span className="mono strong">{formatCompact(elsewhere.toString())}</span>
          </div>
          <p className="muted small">
            A mortgage is repaid with the property it is secured on. <a href="#/property">Repay it on the property page</a>.
          </p>
        </div>
      )}
      {rows.length > 0 && (
        <p className="muted small">
          Interest is charged to the day you repay. Paying a loan off in full stops the interest there and then;
          paying part of it brings the next payment down.
        </p>
      )}
    </Panel>
  );
}
