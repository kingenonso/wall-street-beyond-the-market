// Floor extras, slice 2 (owner, 17 November 2026: "go on"): the bank desk, inside the Trading floor tab. A client asks the
// banks for short money; each bank prices it as a yearly rate after reading the credit file; the cheapest is taken, and the
// money comes back with interest on the due day. Every figure comes from the server.

import { useEffect, useState } from "react";
import { api, ApiError, type FloorBank, type FloorLoan } from "./api";
import { formatCompact } from "./format";
import { useLoad } from "./hooks";
import { Panel } from "./Shell";

const lagosTime = (iso: string) => new Date(iso).toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" });
const rate = (bps: number) => `${(bps / 100).toFixed(2)}%`;
const STATUS: Record<FloorLoan["status"], string> = {
  open: "open", repaid: "repaid", shortfall: "not repaid in full: the rest is owed in default", defaulted: "failed: part repaid",
};

function useBank(onLoggedOut: () => void) {
  const page = useLoad(api.floorBank, "floor-bank", onLoggedOut);
  const reload = page.reload;
  useEffect(() => {
    const id = window.setInterval(reload, 5_000);
    return () => window.clearInterval(id);
  }, [reload]);
  return page;
}

function useAct(setFresh: (b: FloorBank) => void) {
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function act(run: () => Promise<FloorBank>, done: string) {
    setBusy(true); setSaid(null);
    try { setFresh(await run()); setSaid(done); }
    catch (e) { setSaid(e instanceof ApiError ? e.message : "Could not reach the server."); }
    finally { setBusy(false); }
  }
  return { said, busy, act };
}

function Loans({ loans, side, onRepay, busy }: { loans: FloorLoan[]; side: "borrowed" | "lent"; onRepay?: (id: number) => void; busy?: boolean }) {
  if (!loans.length) return <p className="small muted">{side === "borrowed" ? "You have borrowed nothing on the Floor." : "Your desk has lent nothing yet."}</p>;
  return (
    <table className="small bank-loans">
      <thead><tr><th>{side === "borrowed" ? "From" : "To"}</th><th>Money</th><th>Rate</th><th>Due</th><th>Interest</th><th>State</th><th /></tr></thead>
      <tbody>
        {loans.map((l) => (
          <tr key={l.id}>
            <td>{side === "borrowed" ? l.lender : `${l.borrower_name} (${l.grade})`}</td>
            <td className="mono">{formatCompact(l.principal)}</td>
            <td className="mono">{rate(l.rate_bps)}</td>
            <td className="mono">{l.status === "open" ? lagosTime(l.due_at) : lagosTime(l.closed_at!)}</td>
            <td className="mono">{formatCompact(l.interest_now)}</td>
            <td className={l.status === "open" || l.status === "repaid" ? "" : "change-down"}>
              {STATUS[l.status]}{BigInt(l.lost) > 0n ? `, ${formatCompact(l.lost)} lost` : ""}
            </td>
            <td>{side === "borrowed" && l.status === "open" && onRepay &&
              <button className="button-outline small" disabled={busy} onClick={() => onRepay(l.id)}>Repay now</button>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Borrow({ b, setFresh }: { b: FloorBank; setFresh: (b: FloorBank) => void }) {
  const [amount, setAmount] = useState("10000000");
  const [days, setDays] = useState(b.days?.[2] ?? 7);
  const [seconds, setSeconds] = useState(30);
  const [chosen, setChosen] = useState<string[]>(() => (b.desks ?? []).slice(0, 3).map((d) => d.key));
  const { said, busy, act } = useAct(setFresh);
  const kobo = Math.round(Number(amount.replace(/[,\s]/g, "")) * 100);
  const toggle = (key: string) => setChosen((c) => (c.includes(key) ? c.filter((k) => k !== key) : [...c, key]));
  return (
    <>
      <p className="small">
        Your credit file: grade <strong>{b.file?.grade}</strong>. {b.file?.words} Worth after debts {formatCompact(b.file?.worth ?? "0")}, owing{" "}
        {formatCompact(b.file?.debts ?? "0")}{b.owed && BigInt(b.owed) > 0n ? `, of which ${formatCompact(b.owed)} on the Floor` : ""}.
      </p>
      <div className="bank-ask">
        <label className="small">Borrow ₦<input className="mono" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label className="small">for
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {(b.days ?? []).map((d) => <option key={d} value={d}>{d} {d === 1 ? "day" : "days"}</option>)}
          </select>
        </label>
        <label className="small">banks have
          <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>
            {[15, 30, 45, 60].map((s) => <option key={s} value={s}>{s} seconds</option>)}
          </select>
        </label>
      </div>
      <div className="bank-desks">
        {(b.desks ?? []).map((d) => (
          <label key={d.key} className="small"><input type="checkbox" checked={chosen.includes(d.key)} onChange={() => toggle(d.key)} /> {d.name}</label>
        ))}
      </div>
      <button className="button-outline small" disabled={busy || !chosen.length || !(kobo > 0)}
              onClick={() => act(() => api.floorBankAsk(kobo, days, seconds, chosen), "Asked. The rates come in below.")}>Ask for the money</button>
      {said && <span className="small"> {said}</span>}
      {(b.asks ?? []).map((a) => (
        <div key={a.id} className="bank-quotes">
          <p className="small strong">{formatCompact(a.amount)} for {a.days} {a.days === 1 ? "day" : "days"}: rates until {lagosTime(a.quotes_until)}, take one by {lagosTime(a.take_until)}</p>
          {a.quotes.length === 0 && <p className="small muted">Waiting for the banks.</p>}
          {a.quotes.map((q) => (
            <p key={q.id} className="small">
              {q.bank}: <span className="mono">{rate(q.rate_bps)}</span> a year, {formatCompact(q.interest)} in interest{" "}
              <button className="button-outline small" disabled={busy} onClick={() => act(() => api.floorBankTake(a.id, q.id), "Borrowed. The money is in your account.")}>Take</button>
            </p>
          ))}
        </div>
      ))}
      <Loans loans={b.borrowed ?? []} side="borrowed" busy={busy} onRepay={(id) => act(() => api.floorBankRepay(id), "Repaid.")} />
    </>
  );
}

function Incoming({ item, setFresh }: { item: NonNullable<FloorBank["incoming"]>[number]; setFresh: (b: FloorBank) => void }) {
  const [pct, setPct] = useState(item.my_rate_bps ? String(item.my_rate_bps / 100) : "");
  const { said, busy, act } = useAct(setFresh);
  const bps = Math.round(Number(pct) * 100);
  return (
    <div className="bank-incoming">
      <p className="small">
        <strong>{item.client}</strong> wants {formatCompact(item.amount)} for {item.days} {item.days === 1 ? "day" : "days"}, {item.purpose}. Grade{" "}
        <strong>{item.grade}</strong>: {item.grade_words} Rates close at {lagosTime(item.quotes_until)}.
      </p>
      {item.file && (
        <p className="small muted">Worth after debts {formatCompact(item.file.worth)}, owing {formatCompact(item.file.debts)}
          {item.file.in_default ? ", with a loan in default" : ""}. Floor loans repaid: {item.file.repaid}; not repaid in full: {item.file.failed}.</p>
      )}
      <p className="small muted">This grade fails about {rate(item.loan_fail_bps)} of the time over a loan this long; the loss it is expected to cost is
        {" "}{rate(item.expected_loss_bps)} a year.</p>
      <label className="small">Your rate <input className="mono bank-rate" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} />% a year</label>
      <button className="button-outline small" disabled={busy || !(bps > 0)} onClick={() => act(() => api.floorBankQuote(item.id, bps), "Priced.")}>
        {item.my_rate_bps ? "Change the rate" : "Price it"}
      </button>
      {item.my_rate_bps && <span className="small"> Your rate now: {rate(item.my_rate_bps)}.</span>}
      {said && <span className="small"> {said}</span>}
    </div>
  );
}

/** The bank desk: borrow short money on the Floor, and for a banker, price and lend it. */
export function BankPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const page = useBank(onLoggedOut);
  const [fresh, setFresh] = useState<FloorBank | null>(null);
  useEffect(() => setFresh(null), [page.data]);
  const b = fresh ?? page.data;
  if (!b?.ready || !b.file) return null;
  const banker = b.incoming !== undefined;
  return (
    <Panel title="Bank desk" aside={`short loans; the Central Bank's rate is ${rate(b.policy_rate_bps ?? 0)}`}>
      <div className={banker ? "floor-grid-requests" : ""}>
        <div>
          <p className="small strong">Borrow</p>
          <Borrow b={b} setFresh={setFresh} />
        </div>
        {banker && (
          <div>
            <p className="small strong">Lend</p>
            {b.incoming!.length === 0 && <p className="small muted">No requests for money at your desk now. Open your desk and they come in.</p>}
            {b.incoming!.map((item) => <Incoming key={item.id} item={item} setFresh={setFresh} />)}
            <p className="small strong">Your loan book</p>
            {b.record && <p className="small muted">{b.record.loans} loans, {formatCompact(b.record.lent)} lent, {formatCompact(b.record.earned)} earned in
              interest, {formatCompact(b.record.lost)} lost to {b.record.failed} {b.record.failed === 1 ? "failure" : "failures"}.</p>}
            <Loans loans={b.book ?? []} side="lent" />
          </div>
        )}
      </div>
      <p className="small muted">The lender pays the money over at once and is paid back with the interest on the due day. A player who cannot pay owes the rest in
        default; a computer client that fails pays back {Math.round((b.recovery_bps ?? 0) / 100)}% and the lender bears the loss, which counts towards the desk's
        day's loss limit. You may borrow here at most what you are worth after your debts.</p>
    </Panel>
  );
}
