// Pension funds run by players (Stage 6). A saver chooses one, or leaves it; an Asset Manager of
// Level 20 opens one and invests what savers bring. The website only asks; the server decides.

import { useState } from "react";
import { api, ApiError, type ManagedFund, type PensionFunds, type Player } from "./api";
import { AmountForm } from "./Empire";
import { BondOrderForm, ShareOrderForm } from "./TradeForm";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { NumberTile } from "./Parts";
import { Change, Panel } from "./Shell";

type Run = (method: "POST" | "PUT" | "DELETE", path: string, body?: unknown) => Promise<boolean>;

function Managing({ fund, busy, run, onLoggedOut }: { fund: ManagedFund; busy: boolean; run: Run; onLoggedOut: () => void }) {
  return (
    <Panel title={`The fund you manage: ${fund.name}`} aside={`${fund.savers} savers · fee ${(fund.fee_bps / 100).toFixed(2)}% a quarter`}>
      <div className="tiles">
        <NumberTile label="The fund is worth" value={formatCompact(fund.worth_kobo)} note={`a unit: ₦${fund.unit_price.toFixed(4)}`} />
        <NumberTile label="Cash" value={formatCompact(fund.cash_kobo)} />
        <NumberTile label="Shares" value={formatCompact(fund.shares_value_kobo)} />
        <NumberTile label="Bonds and bills" value={formatCompact(fund.bonds_value_kobo)} />
      </div>
      {fund.leaving > 0 && <p className="small change-down">▼ {fund.leaving} saver{fund.leaving === 1 ? " is" : "s are"} waiting for their savings back. The fund can sell, and can buy nothing until they are paid. If you do not sell, the regulator will when the quarter closes.</p>}
      {fund.holdings.map((h) => <div key={h.ticker} className="row"><span>{h.ticker} shares</span><span className="mono">{h.shares.toLocaleString("en-NG")} · {formatCompact(h.value_kobo)}</span></div>)}
      {fund.bond_holdings.map((b) => <div key={b.code} className="row"><span>{b.name} <span className="ticker">{b.code}</span></span><span className="mono">{b.units.toLocaleString("en-NG")} · {formatCompact(b.value_kobo)}</span></div>)}
      {fund.orders.filter((o) => o.status === "open").map((order) => (
        <div key={order.id} className="row"><span>{order.side === "buy" ? "Buying" : "Selling"} {order.remaining.toLocaleString("en-NG")} {order.ticker} <span className="muted small">· waiting</span></span>
          <button className="button-quiet" disabled={busy} onClick={() => run("DELETE", `/pension-fund/orders/${order.id}`)}>Cancel</button></div>
      ))}
      <div className="why-title">Invest the savers' money</div>
      <div className="why-title">Shares</div>
      <ShareOrderForm whose="The fund" busy={busy} held={fund.holdings} fairDealing onLoggedOut={onLoggedOut}
                      onPlace={(order) => run("POST", "/pension-fund/orders", { ...order, kind: "limit" })} />
      <div className="why-title">Bonds and bills</div>
      <BondOrderForm whose="The fund" busy={busy} held={fund.bond_holdings} onLoggedOut={onLoggedOut}
                     onPlace={(order) => run("POST", "/pension-fund/bonds", order)} />
      <div className="definition shadow">
        <div className="why-title">The shadow side</div>
        <p className="small">
          You may sign for a cost that is not real, and the money comes to you. In the fund's books it reads "Custody and
          dealing costs". The regulator audits every fund each quarter, and any saver may hire the AI audit in an audit season.
          If it is proved, you repay it with a fine of the same amount again and are struck off for good.
        </p>
        <AmountForm label={`Sign for a cost (limit ${formatNaira(fund.signing_limit_kobo)} a quarter, ${formatNaira(fund.signing_used_kobo)} used)`}
                    button="Sign for it" busy={busy} onSubmit={(kobo) => run("POST", "/pension-fund/costs", { amount_kobo: kobo })} />
      </div>
      {fund.books.length > 0 && <div className="why-title">The fund's books</div>}
      {fund.books.slice(0, 8).map((entry) => <div key={entry.id} className="row"><span>{entry.period_label} · {entry.category}</span><span className="mono">{formatNaira(entry.amount_kobo)}{entry.found && <span className="change-down small"> ✕ proved false</span>}</span></div>)}
      {fund.fee_bps > 0 && <button className="button-quiet" disabled={busy} onClick={() => run("PUT", "/pension-fund/fee", { fee_bps: Math.max(fund.fee_bps - 5, 0) })}>Lower the fee by 0.05%</button>}
    </Panel>
  );
}

export function PensionFundsPanel({ player, onLoggedOut, onChanged }: { player: Player; onLoggedOut: () => void; onChanged: () => void }) {
  const loaded = useLoad(api.pensionFunds, `pension-funds:${player.id}`, onLoggedOut);
  const [fresh, setFresh] = useState<PensionFunds | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [fee, setFee] = useState("25");
  const data = fresh ?? loaded.data;
  const run: Run = async (method, path, body) => {
    setBusy(true); setError(null);
    try { setFresh(await api.pensionFund(method, path, body)); onChanged(); return true; }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again."); return false; }
    finally { setBusy(false); }
  };
  if (!data) return null;
  return (
    <>
      <Panel title="Pension funds run by players" aside={data.audit_season ? "● Audit season" : undefined}>
        <p className="small">
          An Asset Manager of Level {data.manager_level} may open a pension fund, and you may move your retirement savings into
          it instead of one of the four ordinary funds. The manager invests your money on the market and takes a fee. A good
          manager may do better than the ordinary funds; a bad one may lose your money, and a dishonest one may take it. The
          regulator audits every fund each quarter. A fund must deal within 2% of the market price, cannot deal with its own
          manager, and can trade its own worth once a quarter. You can always ask for your savings back; moves in and out are
          carried out as the quarter closes.
        </p>
        {error && <p className="error" role="alert">{error}</p>}
        {data.funds.length === 0 && <p className="muted small">No player has opened a pension fund yet.</p>}
        {data.funds.map((fund) => (
          <div key={fund.id} className={fund.yours ? "fund-card definition row-chosen" : "fund-card"}>
            <div className="row">
              <span><span className="strong">{fund.yours ? "✓ " : ""}{fund.name}</span> <span className="muted small">· {fund.run_by_regulator ? "run by the regulator" : `managed by ${fund.manager}`}</span></span>
              <span className="mono">{formatCompact(fund.worth_kobo)} <span className="muted">· {fund.savers} savers</span></span>
            </div>
            <div className="muted small">
              Fee {(fund.fee_bps / 100).toFixed(2)}% a quarter · a unit is worth ₦{fund.unit_price.toFixed(4)} · over the last game year{" "}
              {fund.over_year_bps === null ? "too new to say" : <Change bps={fund.over_year_bps} />} · holds cash {formatCompact(fund.cash_kobo)}, shares {formatCompact(fund.shares_value_kobo)}, bonds {formatCompact(fund.bonds_value_kobo)}
            </div>
            {fund.proved_thefts > 0 && <div className="small change-down">▼ {fund.struck_off ? "Its manager was struck off for taking savers' money." : `${fund.proved_thefts} proved theft${fund.proved_thefts === 1 ? "" : "s"} on its record.`}</div>}
            <div className="step-actions">
              {fund.yours ? (
                <>
                  <span className="small">Your savings here: <span className="mono strong">{formatNaira(fund.your_value_kobo)}</span>{fund.leaving && " · you have asked for them back; you are paid when the quarter closes, as far as the fund has cash"}</span>
                  <span>
                    <button className="button-quiet" disabled={busy || !data.audit_season} title={data.audit_season ? undefined : "Only in an audit season"} onClick={() => run("POST", "/pension-fund/ai-audit")}>Hire the AI audit</button>
                    {!fund.leaving && <button className="button-quiet" disabled={busy} onClick={() => run("DELETE", "/pension-fund/savings")}>Ask for my savings back</button>}
                  </span>
                </>
              ) : fund.joining ? (
                <>
                  <span className="small">✓ Your savings move here when the quarter closes.</span>
                  <button className="button-quiet" disabled={busy} onClick={() => run("DELETE", "/pension-fund/savings")}>Change my mind</button>
                </>
              ) : !fund.struck_off && fund.manager !== player.display_name && (
                <button className="button-outline" disabled={busy} onClick={() => run("PUT", `/pension-funds/${fund.id}/savings`)}>Move my savings here when the quarter closes</button>
              )}
            </div>
          </div>
        ))}
        {data.can_open && (
          <form className="stack-form" onSubmit={(event) => { event.preventDefault(); run("POST", "/pension-funds", { name, fee_bps: Number(fee) }); }}>
            <div className="why-title">Open a pension fund</div>
            <p className="muted small">Registration costs {formatNaira(data.registration_fee_kobo)} from your own cash. A manager opens one fund, once. Your own pension cannot be kept in the fund you run.</p>
            <label className="answer"><span className="field-label">Name of the fund</span><span className="answer-box"><input type="text" maxLength={40} value={name} onChange={(event) => setName(event.target.value)} /></span></label>
            <label className="answer"><span className="field-label">Your fee each quarter, of everything in the fund</span>
              <select value={fee} onChange={(event) => setFee(event.target.value)}>{[0, 5, 10, 15, 20, 25, 30, 40, 50].map((bps) => <option key={bps} value={bps}>{formatPercent(bps, 2)}</option>)}</select></label>
            <button className="button-outline" disabled={busy || name.trim().length < 3}>Open the fund</button>
          </form>
        )}
      </Panel>
      {data.managing && <Managing fund={data.managing} busy={busy} run={run} onLoggedOut={onLoggedOut} />}
    </>
  );
}
