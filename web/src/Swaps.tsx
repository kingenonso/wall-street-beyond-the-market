// The gap stage, Part 1: swaps with a bank, a player or an empire; and the pension funds' desk for preferred shares
// and warrants.

import { useState } from "react";
import { api, type Instrument, type InstrumentsDesk, type SwapsDesk } from "./api";
import { useAct } from "./Derivatives";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";

const STATUS: Record<string, string> = { signing: "Being signed inside the empire", proposed: "Offered, waiting for an answer", countersigning: "Being signed by the other empire",
  active: "Running", ended: "Ended" };

export function SwapsPanel({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged?: () => void }) {
  const { data, error, loading, reload } = useLoad<SwapsDesk>(api.swaps, "swaps", onLoggedOut);
  const act = useAct(reload, onLoggedOut, onChanged);
  const [kind, setKind] = useState<"rate" | "oil" | "fx">("rate");
  const [with_, setWith] = useState<"bank" | "player" | "empire">("bank");
  const [bank, setBank] = useState("");
  const [name, setName] = useState("");
  const [side, setSide] = useState<"pay_fixed" | "receive_fixed">("pay_fixed");
  const [quarters, setQuarters] = useState("4");
  const [size, setSize] = useState("");
  const [fixed, setFixed] = useState("");
  const [forEmpire, setForEmpire] = useState(false);
  if (loading && !data) return <Loading what="swaps" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const q = Math.floor(Number(quarters) || 0);
  const notional = kind === "rate" ? asKobo(size) : null;
  const barrels = kind === "oil" ? Math.floor(Number(size.replace(/,/g, "")) || 0) : 0;
  const dollars = kind === "fx" ? Math.round((Number(size.replace(/[,$]/g, "")) || 0) * 100) : 0;
  const fixedValue = with_ === "bank" ? null : kind === "rate" ? Math.round(Number(fixed) * 100) || null : asKobo(fixed);
  const counter = with_ === "bank" ? { bank: bank || data.banks[0]?.id } : with_ === "player" ? { player: name.trim() } : { empire: name.trim() };
  const ready = q >= 1 && q <= 8 && (kind === "rate" ? notional !== null : kind === "fx" ? dollars > 0 : barrels > 0) && (with_ === "bank" || (fixedValue !== null && name.trim() !== ""));
  const body = { kind, side, quarters: q, ...(kind === "rate" ? { notional_kobo: notional } : kind === "fx" ? { dollars_cents: dollars } : { barrels }), ...(fixedValue ? { fixed: fixedValue } : {}), ...counter, for_empire: forEmpire };
  return (
    <Panel title="Swaps" aside={`Central Bank rate ${formatPercent(data.rate_now, 2)} · oil ${formatNaira(data.oil_now)} a barrel · dollar ${formatNaira(String(data.dollar_now))} · opens at Level ${data.unlock_level}`}>
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
      <p className="small">
        A <Term word="Swap">swap</Term> swaps a fixed payment for one that floats, each quarter, for up to eight quarters. Only the difference is paid, at each quarter's close,
        from the quarter after it is signed. A bank takes a swap at once at its own price; a player or an empire is asked. A side that cannot pay owes the other.
        {data.empire && <> For {data.empire}: the Investment Banker structures it, the Legal Counsel drafts it, the Risk Manager signs and the head signs.</>}
      </p>
      {data.swaps.length > 0 ? (
        <div className="scroll" tabIndex={0}>
          <table className="dense">
            <caption className="sr-only">Your swaps</caption>
            <thead><tr><th scope="col">Swap</th><th scope="col">You</th><th scope="col">With</th><th scope="col">Status</th><th scope="col" className="num">Worth to you now</th><th scope="col">Payments so far</th><th scope="col"><span className="sr-only">Answer</span></th></tr></thead>
            <tbody>
              {data.swaps.map((s) => {
                const up = !s.value.startsWith("-");
                return (
                  <tr key={s.id}>
                    <th scope="row" style={{ whiteSpace: "normal", minWidth: 160 }}>{s.name}</th>
                    <td>{s.side === "pay_fixed" ? "Pay fixed" : "Receive fixed"}</td>
                    <td>{s.other}</td>
                    <td>{STATUS[s.status] ?? s.status}</td>
                    <td className={`num mono ${up ? "change-up" : "change-down"}`}>{up ? "▲" : "▼"} {formatNaira(s.value.replace("-", ""))}</td>
                    <td className="small">{s.payments.length === 0 ? "None yet" : s.payments.map((p) => `${p.amount.startsWith("-") ? "paid" : "received"} ${formatCompact(p.amount.replace("-", ""))}${p.unpaid !== "0" ? ` (${formatCompact(p.unpaid)} unpaid)` : ""}`).join(" · ")}</td>
                    <td>{s.yours_to_answer && <span className="inline-form trade-cell">
                      <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/swaps/${s.id}/accept`, { for_empire: s.empire_side }, "Accepted.")}>Accept</button>
                      <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/swaps/${s.id}/decline`, { for_empire: s.empire_side }, "Declined.")}>Decline</button>
                    </span>}
                    {s.status === "proposed" && !s.yours_to_answer && <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/swaps/${s.id}/decline`, { for_empire: s.empire_side }, "Withdrawn.")}>Withdraw</button>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : <p className="muted small">No swaps.</p>}
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); if (ready) act.run("/swaps", body, with_ === "bank" ? "Signed with the bank." : forEmpire ? "Sent for signing inside the empire." : "Offered. They will be asked."); }}>
        <label className="answer">On<select value={kind} onChange={(e) => setKind(e.target.value as "rate" | "oil" | "fx")}><option value="rate">The Central Bank's rate</option><option value="oil">The oil price</option><option value="fx">The dollar (a currency forward)</option></select></label>
        <label className="answer">With<select value={with_} onChange={(e) => setWith(e.target.value as "bank" | "player" | "empire")}><option value="bank">A bank</option><option value="player">A player</option><option value="empire">An empire</option></select></label>
        {with_ === "bank"
          ? <label className="answer">Bank<select value={bank || data.banks[0]?.id || ""} onChange={(e) => setBank(e.target.value)}>{data.banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          : <label className="answer">Their name<input type="text" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} /></label>}
        <label className="answer">You<select value={side} onChange={(e) => setSide(e.target.value as "pay_fixed" | "receive_fixed")}><option value="pay_fixed">Pay fixed, receive the floating</option><option value="receive_fixed">Receive fixed, pay the floating</option></select></label>
        <label className="answer">Quarters (1–8)<input type="number" min={1} max={8} value={quarters} onChange={(e) => setQuarters(e.target.value)} /></label>
        <label className="answer">{kind === "rate" ? "On (₦)" : kind === "fx" ? "Dollars a quarter ($)" : "Barrels a quarter"}<input type="text" inputMode="decimal" value={size} onChange={(e) => setSize(e.target.value)} /></label>
        {with_ !== "bank" && <label className="answer">{kind === "rate" ? "Fixed rate (% a year)" : kind === "fx" ? "Fixed rate (₦ a dollar)" : "Fixed price (₦ a barrel)"}<input type="text" inputMode="decimal" value={fixed} onChange={(e) => setFixed(e.target.value)} /></label>}
        {data.empire && <label className="check-line"><input type="checkbox" checked={forEmpire} onChange={(e) => setForEmpire(e.target.checked)} /> For {data.empire}</label>}
        <button className="button-outline" disabled={act.busy || !ready}>{with_ === "bank" ? "Sign with the bank" : "Offer the swap"}</button>
      </form>
    </Panel>
  );
}

function InstrumentRow({ i, act, empire }: { i: Instrument; act: ReturnType<typeof useAct>; empire: InstrumentsDesk["empire"] }) {
  const [n, setN] = useState("100");
  const [forEmpire, setForEmpire] = useState(false);
  const units = Math.max(Math.floor(Number(n) || 0), 0);
  const held = forEmpire ? (empire?.held[i.code] ?? 0) : i.held;
  const body = (side: "buy" | "sell") => ({ side, units, for_empire: forEmpire });
  return (
    <tr>
      <th scope="row" style={{ whiteSpace: "normal", minWidth: 160 }}>{i.name}
        <div className="muted small">{i.kind === "preferred" ? `${formatPercent(i.dividend_bps ?? 0, 2)} a year on ${formatNaira(String(i.par ?? 0))}` : `${i.shares_per} new share${i.shares_per === 1 ? "" : "s"} at ${formatNaira(String(i.strike ?? 0))} each, until ${i.expiry}`}</div></th>
      <td className="num mono">{formatNaira(i.fair)}</td>
      <td className="num mono">{formatNaira(i.bid)}</td>
      <td className="num mono">{formatNaira(i.ask)}</td>
      <td className="num mono">{i.on_offer.toLocaleString("en-NG")}</td>
      <td className="num mono">{held.toLocaleString("en-NG")}</td>
      <td>
        <span className="inline-form trade-cell">
          <input className="tiny-input" type="number" min={1} aria-label={`Units of ${i.name}`} value={n} onChange={(e) => setN(e.target.value)} />
          <button className="button-quiet" disabled={act.busy || units < 1} onClick={() => act.run(`/instruments/${i.code}/trade`, body("buy"), `Bought ${units.toLocaleString("en-NG")}.`)}>Buy</button>
          <button className="button-quiet" disabled={act.busy || units < 1 || held < 1} onClick={() => act.run(`/instruments/${i.code}/trade`, body("sell"), `Sold ${units.toLocaleString("en-NG")}.`)}>Sell</button>
          {i.kind === "warrant" && <button className="button-quiet" disabled={act.busy || units < 1 || held < 1} onClick={() => act.run(`/instruments/${i.code}/exercise`, { units, for_empire: forEmpire }, "Handed in: the new shares come at the quarter's close.")}>Use</button>}
          {empire?.acts && <label className="check-line small"><input type="checkbox" checked={forEmpire} onChange={(e) => setForEmpire(e.target.checked)} /> for {empire.name}</label>}
        </span>
      </td>
    </tr>
  );
}

export function InstrumentsPanel({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged?: () => void }) {
  const { data, error, loading, reload } = useLoad<InstrumentsDesk>(api.instruments, "instruments", onLoggedOut);
  const act = useAct(reload, onLoggedOut, onChanged);
  if (loading && !data) return <Loading what="preferred shares and warrants" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const waiting = [...data.waiting.map((w) => ({ ...w, empire: false })), ...(data.empire?.waiting ?? []).map((w) => ({ ...w, empire: true }))];
  return (
    <Panel title="Preferred shares and warrants" aside="dealt at the pension funds' desk">
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
      <p className="small">
        A <Term word="Preferred share">preferred share</Term> pays a fixed dividend each quarter the company makes a profit, before the ordinary shares get anything.
        A <Term word="Warrant">warrant</Term> lets you buy new shares from the company at a set price: hand it in with the money, and the shares are issued at the quarter's close.
      </p>
      {data.instruments.length === 0 ? <p className="muted small">None on offer yet: companies sell preferred shares and hand out warrants as quarters close.</p> : (
        <div className="scroll" tabIndex={0}>
          <table className="dense">
            <caption className="sr-only">Preferred shares and warrants</caption>
            <thead><tr><th scope="col">Security</th><th scope="col" className="num">Fair value</th><th scope="col" className="num">You can sell at</th><th scope="col" className="num">You can buy at</th><th scope="col" className="num">On offer</th><th scope="col" className="num">Held</th><th scope="col">Deal</th></tr></thead>
            <tbody>{data.instruments.map((i) => <InstrumentRow key={i.code} i={i} act={act} empire={data.empire} />)}</tbody>
          </table>
        </div>
      )}
      {waiting.length > 0 && (
        <ul className="plain-list small">
          {waiting.map((w) => (
            <li key={w.id}>{w.units.toLocaleString("en-NG")} {w.name} handed in{w.empire ? ` by ${data.empire?.name}` : ""}, with {formatNaira(w.cash)} held{" "}
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/instruments/exercises/${w.id}/cancel`, { for_empire: w.empire }, "Handed back.")}>Take back</button></li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
