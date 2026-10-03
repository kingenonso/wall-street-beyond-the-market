// Empires and the War Room (design document, sections 6, 13, 15 and 18).
// A player without a seat sees every empire and can join or found one. A member sees their own
// empire: its task and who holds each step, its money, its books, its audits, its pacts, its chat.
// The website only asks: the server knows which empire the player belongs to.

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, type EmpireRoom, type EmpireView, type Player } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { NumberTile, ProgressTracker } from "./Parts";
import { Failed, Loading, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void; onChanged: () => void };
type Act = { busy: boolean; error: string | null; notice: string | null; run: (method: "POST" | "PUT" | "DELETE", path: string, body?: unknown) => Promise<boolean> };

/** "25,000.50" typed by a player, as whole kobo. Null if it is not an amount. */
export function asKobo(text: string): number | null {
  const clean = text.replace(/[,₦\s]/g, "");
  if (!/^\d{1,13}(\.\d{1,2})?$/.test(clean)) return null;
  const [naira, kobo = ""] = clean.split(".");
  const value = Number(naira) * 100 + Number(kobo.padEnd(2, "0"));
  return value > 0 ? value : null;
}

const when = (iso: string) => new Date(iso).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** One small form: an amount of naira and a button. */
export function AmountForm({ label, button, busy, onSubmit, hint }: {
  label: string; button: string; busy: boolean; onSubmit: (kobo: number) => void; hint?: ReactNode;
}) {
  const [text, setText] = useState("");
  const kobo = asKobo(text);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (kobo !== null) { onSubmit(kobo); setText(""); }
  }
  return (
    <form className="inline-form" onSubmit={submit}>
      <label className="answer">
        <span className="field-label">{label}</span>
        <span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={text} onChange={(event) => setText(event.target.value)} /></span>
      </label>
      <button className="button-outline" disabled={busy || kobo === null}>{button}</button>
      {hint && <span className="muted small">{hint}</span>}
    </form>
  );
}

function useEmpire(player: Player, onLoggedOut: () => void, onChanged: () => void) {
  const loaded = useLoad(api.empires, `empires:${player.id}`, onLoggedOut);
  const [view, setView] = useState<EmpireView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The work area and the rail each hold the empire. When one changes it, the other reads it again.
  const me = useRef(Math.random());
  useEffect(() => {
    const heard = (event: Event) => {
      if ((event as CustomEvent).detail === me.current) return;
      setView(null); loaded.reload();
    };
    window.addEventListener("empire-changed", heard);
    return () => window.removeEventListener("empire-changed", heard);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function run(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await api.empire(method, path, body);
      setView(answer); setNotice(answer.notice ?? null); onChanged();
      window.dispatchEvent(new CustomEvent("empire-changed", { detail: me.current }));
      return true;
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) onLoggedOut();
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
      return false;
    } finally { setBusy(false); }
  }
  return { loaded, view: view ?? loaded.data, act: { busy, error, notice, run } as Act };
}

// ---------------------------------------------------------------------------
// Without a seat: every empire, and founding one
// ---------------------------------------------------------------------------

function Directory({ view, player, act }: { view: EmpireView; player: Player; act: Act }) {
  const d = view.directory;
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [savings, setSavings] = useState("");
  const amountKobo = asKobo(amount);
  return (
    <>
      <Panel title="The league of empires" aside="Ranked by what each is worth">
        <p className="small">
          An empire is a team of thirteen: a head, and two seats for each of the six builds. Five empires run by the computer
          have existed since the first day, and take any player they have a seat for. A seat is in addition to your job: your
          employer still pays your salary, and the empire pays for the work you do for it.
        </p>
        <div className="scroll">
          <table>
            <thead><tr><th scope="col" className="num">Place</th><th scope="col">Empire</th><th scope="col">Run by</th><th scope="col" className="num">Worth</th><th scope="col" className="num">Players</th><th scope="col" className="num">Trust</th><th scope="col"></th></tr></thead>
            <tbody>
              {d.league.map((row) => (
                <tr key={row.id} className={row.yours ? "row-chosen" : undefined}>
                  <td className="num mono">{row.place}</td>
                  <th scope="row">{row.name}</th>
                  <td>{row.run_by}</td>
                  <td className="num mono">{formatCompact(row.worth_kobo)}</td>
                  <td className="num mono">{row.members} of 12</td>
                  <td className="num mono">{row.trust}</td>
                  <td className="num">
                    {row.yours ? <span className="saved small">✓ Yours</span>
                      : row.applied ? <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", "/empire/application")}>Withdraw application</button>
                      : !view.room && <button className="button-quiet" disabled={act.busy || !player.build || row.seats_open === 0}
                                 onClick={() => act.run("POST", `/empires/${row.id}/applications`)}>
                          {row.seats_open === 0 ? "No seat for your build" : row.run_by === "the computer" ? "Take a seat" : "Apply"}
                        </button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!player.build && <p className="muted small">Choose a build on the <a href="#/career">Career</a> page first: a seat in an empire is a seat for a build.</p>}
        {d.forming.length > 0 && !view.room && (
          <>
            <div className="why-title">BEING FOUNDED</div>
            {d.forming.map((row) => (
              <div key={row.id} className="row">
                <span>{row.name} <span className="muted small">· founder: {row.founder}</span></span>
                <button className="button-quiet" disabled={act.busy || !player.build} onClick={() => act.run("POST", `/empires/${row.id}/applications`)}>Apply to be a partner</button>
              </div>
            ))}
          </>
        )}
      </Panel>

      {!view.room && (
        <Panel title="Found your own empire" aside={`Level ${d.founding_level} and above`}>
          <p className="small">
            The founder must be Level {d.founding_level}. Registration costs {formatNaira(d.registration_fee_kobo)}, paid from what the
            founder and their partners pool together, and it needs at least three players before it can open. Until a player has
            earned the rank of CEO, the founder leads as Acting Head, with capped powers. The one early withdrawal from your
            retirement savings (up to half) may be used here.
          </p>
          {d.can_found ? (
            <form className="stack-form" onSubmit={(event) => {
              event.preventDefault();
              if (amountKobo !== null) act.run("POST", "/empires", { name, amount_kobo: amountKobo, from_savings_kobo: asKobo(savings) ?? 0 });
            }}>
              <label className="answer"><span className="field-label">Name of the empire</span><span className="answer-box"><input type="text" maxLength={40} value={name} onChange={(event) => setName(event.target.value)} /></span></label>
              <label className="answer"><span className="field-label">Cash you put in now</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></span></label>
              <label className="answer"><span className="field-label">Of which, drawn early from your retirement savings (optional)</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={savings} onChange={(event) => setSavings(event.target.value)} /></span></label>
              <button className="button-primary" disabled={act.busy || name.trim().length < 3 || amountKobo === null}>Begin founding</button>
            </form>
          ) : <p className="muted small">You {player.level ? `are Level ${player.level}` : "have no build yet"}. Founding opens at Level {d.founding_level}.</p>}
        </Panel>
      )}

      {d.exposed_pacts.length > 0 && (
        <Panel title="Pacts that have come to light" aside="Uncovered by journalists, or reported">
          {d.exposed_pacts.map((pact, index) => (
            <div key={index} className="row">
              <span>{pact.one} and {pact.other} <span className="muted small">· {pact.kind}</span></span>
              <span className={pact.legal ? "muted small" : "small change-down"}>{pact.legal ? "lawful" : "▼ unlawful"}</span>
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// An empire being founded
// ---------------------------------------------------------------------------

function Founding({ room, act }: { room: EmpireRoom; act: Act }) {
  const pooled = BigInt(room.cash_kobo);
  const fee = BigInt(room.registration_fee_kobo);
  return (
    <Panel title={`Founding ${room.name}`} aside="Not open yet">
      <ProgressTracker steps={[
        { label: "Begin founding", done: true },
        { label: `Three players`, done: room.humans >= room.least_humans, note: `${room.humans} so far` },
        { label: "Pool the registration fee", done: pooled >= fee, note: `${formatCompact(room.cash_kobo)} of ${formatCompact(room.registration_fee_kobo)}` },
        { label: "Open the empire", done: false, note: "the head does this" },
      ]} />
      <div className="why-title">WHO HAS PUT IN WHAT</div>
      {room.capital.map((line) => <div key={line.display_name} className="row"><span>{line.display_name}</span><span className="mono">{formatNaira(line.amount_kobo)}</span></div>)}
      <AmountForm label="Put in more of your own cash" button="Put in" busy={act.busy} onSubmit={(kobo) => act.run("POST", "/empire/capital", { amount_kobo: kobo })}
                  hint="If the founding is cancelled, every naira goes back to whoever put it in." />
      {room.is_head && (
        <div className="step-actions">
          <button className="button-primary" disabled={act.busy || room.humans < room.least_humans || pooled < fee} onClick={() => act.run("POST", "/empire/opening")}>Open the empire</button>
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", "/empire/founding")}>Cancel the founding</button>
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The War Room
// ---------------------------------------------------------------------------

function Task({ room, act }: { room: EmpireRoom; act: Act }) {
  const task = room.task;
  return (
    <Panel title="The task in hand" aside={task ? `${task.company} (${task.ticker}) · up to ${formatCompact(task.amount_kobo)}` : "None"}>
      {!task && <p className="muted small">No task has been started. {room.is_head ? "As head, you start one: the server chooses a company for the empire to look at and, if it stands up, invest in." : "The head starts one."}</p>}
      {task && (
        <>
          <p className="small">
            A task needs every build. Each step is handed from one build to the next; a step that falls to a seat with no player
            is done by the staff, one step each working day. {task.status === "done" ? "✓ This task is complete." : task.status === "failed" ? "This task was left unfinished and was closed." : ""}
          </p>
          <ol className="handoffs">
            {task.steps.map((step) => (
              <li key={step.id} className={`handoff handoff-${step.status}`} aria-current={step.status === "current" ? "step" : undefined}>
                <span className="tracker-mark" aria-hidden="true">{step.status === "done" ? "✓" : step.position}</span>
                <div>
                  <div className="strong">{step.build_name}: {step.what}</div>
                  <div className="muted small">
                    {step.status === "done" ? `Done by ${step.done_by ?? "the staff"}. Handed on: ${step.hands_on.toLowerCase()}.`
                      : step.status === "current" ? (step.taken_by ? `${step.taken_by} has it in hand.` : "Waiting to be taken.")
                      : `Waits for the step before it. Hands on: ${step.hands_on.toLowerCase()}.`}
                  </div>
                  {step.yours_to_take && <button className="button-primary" disabled={act.busy} onClick={() => act.run("POST", `/empire/steps/${step.id}/take`)}>Take this step</button>}
                  {step.yours_to_approve && <button className="button-primary" disabled={act.busy} onClick={() => act.run("POST", `/empire/steps/${step.id}/approve`)}>Approve the investment</button>}
                  {step.status === "current" && step.taken_by && <a className="small" href="#/work"> Open your work</a>}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
      {room.is_head && (!task || task.status !== "open") && (
        <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", "/empire/tasks")}>Start an investment task</button>
      )}
    </Panel>
  );
}

function Seats({ room, act }: { room: EmpireRoom; act: Act }) {
  const [bonus, setBonus] = useState<string | null>(null);
  return (
    <Panel title="Seats and the chain of command" aside={`${room.humans} players · ${room.seats.filter((s) => s.staffed).length} staff`}>
      <div className="scroll">
        <table>
          <thead><tr><th scope="col">Build</th><th scope="col">Held by</th><th scope="col" className="num">Level</th>{room.is_head && <th scope="col" className="num">May sign for, a quarter</th>}<th scope="col"></th></tr></thead>
          <tbody>
            {room.seats.map((seat) => (
              <tr key={`${seat.build}${seat.slot}`} className={seat.you ? "row-chosen" : undefined}>
                <th scope="row">{seat.build_name} {seat.slot}</th>
                <td>{seat.name}{seat.head && <span className="tag tag-active"> ★ {room.kind === "player" ? "Acting Head" : "Head"}</span>}{seat.lead && !seat.head && <span className="muted small"> · lead</span>}{seat.you && <span className="muted small"> · you</span>}</td>
                <td className="num mono">{seat.level ?? "—"}</td>
                {room.is_head && <td className="num mono">{seat.player_id ? (seat.signing_limit_kobo ? formatNaira(seat.signing_limit_kobo) : "the usual") : "—"}</td>}
                <td className="num">
                  {room.is_head && !seat.player_id && (
                    <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", "/empire/staff", { build: seat.build, slot: seat.slot, staffed: !seat.staffed })}>
                      {seat.staffed ? "Let the staff go" : "Hire staff"}
                    </button>
                  )}
                  {room.is_head && seat.player_id && !seat.you && (
                    <>
                      <button className="button-quiet" disabled={act.busy} onClick={() => setBonus(bonus === seat.player_id ? null : seat.player_id)}>Bonus or limit</button>
                      <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/empire/members/${seat.player_id}`)}>Remove</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {room.is_head && bonus && (
        <div className="definition">
          <AmountForm label="Pay this member a bonus from the empire's cash" button="Pay bonus" busy={act.busy}
                      onSubmit={(kobo) => act.run("POST", "/empire/bonuses", { member_id: bonus, amount_kobo: kobo, why: "Bonus" })} />
          <AmountForm label="What this member may sign for in a quarter" button="Set limit" busy={act.busy}
                      onSubmit={(kobo) => act.run("PUT", "/empire/limits", { member_id: bonus, signing_limit_kobo: kobo })} />
        </div>
      )}
      {room.is_head && (
        <div className="definition">
          <div className="why-title">LIMITS YOU SET AS HEAD</div>
          <AmountForm label={`What a member may sign for in a quarter (now ${formatNaira(room.expense_limit_kobo)})`} button="Set" busy={act.busy}
                      onSubmit={(kobo) => act.run("PUT", "/empire/limits", { expense_limit_kobo: kobo })} />
          <div className="row">
            <span>An Asset Manager may trade, in a quarter, this share of the empire</span>
            <span>
              {[500, 1000, 2000, 5000].map((bps) => (
                <button key={bps} className={room.trade_limit_bps === bps ? "button-outline" : "button-quiet"} disabled={act.busy}
                        onClick={() => act.run("PUT", "/empire/limits", { trade_limit_bps: bps })}>{bps / 100}%</button>
              ))}
            </span>
          </div>
          <p className="muted small">Staff work at a fixed Level 40, reliably and slowly, and are paid by the empire each quarter. An empty seat with no staff does no work.</p>
        </div>
      )}
      {room.applications.length > 0 && (
        <>
          <div className="why-title">ASKING FOR A SEAT</div>
          {room.applications.map((asked) => (
            <div key={asked.id} className="row">
              <span>{asked.display_name} <span className="muted small">· {asked.build.replace("_", " ")}</span></span>
              <span>
                <button className="button-outline" disabled={act.busy} onClick={() => act.run("PUT", `/empire/applications/${asked.id}`, { accept: true })}>Accept</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/empire/applications/${asked.id}`, { accept: false })}>Refuse</button>
              </span>
            </div>
          ))}
        </>
      )}
    </Panel>
  );
}

function Treasury({ room, act }: { room: EmpireRoom; act: Act }) {
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [code, setCode] = useState("");
  const [units, setUnits] = useState("");
  const count = Number(quantity);
  const priceKobo = asKobo(price);
  return (
    <Panel title="The empire's money" aside={room.place ? `Place ${room.place} of ${room.empires} in the league` : undefined}>
      <div className="tiles">
        <NumberTile label="Worth" value={formatCompact(room.worth_kobo)} note={`trust ${room.trust} of 100`} />
        <NumberTile label="Cash" value={formatCompact(room.cash_kobo)} />
        <NumberTile label="Shares" value={formatCompact(room.shares_value_kobo)} note={`${room.holdings.length} companies`} />
        <NumberTile label="Bonds and bills" value={formatCompact(room.bonds_value_kobo)} />
      </div>
      {(room.holdings.length > 0 || room.bond_holdings.length > 0) && (
        <div className="scroll">
          <table>
            <thead><tr><th scope="col">Held</th><th scope="col" className="num">Number</th><th scope="col" className="num">Value</th></tr></thead>
            <tbody>
              {room.holdings.map((h) => <tr key={h.ticker}><th scope="row"><a href={`#/companies/${h.ticker}`}>{h.ticker}</a> shares</th><td className="num mono">{h.shares.toLocaleString("en-NG")}</td><td className="num mono">{formatCompact(h.value_kobo)}</td></tr>)}
              {room.bond_holdings.map((b) => <tr key={b.code}><th scope="row">{b.name} <span className="ticker">{b.code}</span></th><td className="num mono">{b.units.toLocaleString("en-NG")}</td><td className="num mono">{formatCompact(b.value_kobo)}</td></tr>)}
            </tbody>
          </table>
        </div>
      )}
      {room.orders.filter((o) => o.status === "open").map((order) => (
        <div key={order.id} className="row">
          <span>{order.side === "buy" ? "Buying" : "Selling"} {order.remaining.toLocaleString("en-NG")} {order.ticker}{order.limit_price_kobo ? ` at ${formatNaira(order.limit_price_kobo)}` : ""} <span className="muted small">· waiting</span></span>
          {room.can_trade && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/empire/orders/${order.id}`)}>Cancel</button>}
        </div>
      ))}
      {room.can_trade ? (
        <>
          <div className="why-title">TRADE FOR THE EMPIRE, WITH THE EMPIRE'S MONEY</div>
          <p className="muted small">
            Your limit for the quarter is {formatNaira(room.trade_limit_kobo)}; {formatNaira(room.trade_used_kobo)} is used. What you buy
            belongs to the empire, not to you.
          </p>
          <form className="inline-form" onSubmit={(event) => {
            event.preventDefault();
            if (Number.isInteger(count) && count > 0 && priceKobo !== null) {
              act.run("POST", "/empire/orders", { ticker, side, kind: "limit", quantity: count, limit_price_kobo: priceKobo }).then((ok) => ok && setQuantity(""));
            }
          }}>
            <label className="answer"><span className="field-label">Share code</span><span className="answer-box"><input type="text" maxLength={3} value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} /></span></label>
            <label className="answer"><span className="field-label">Buy or sell</span>
              <select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")}><option value="buy">Buy</option><option value="sell">Sell</option></select></label>
            <label className="answer"><span className="field-label">Shares</span><span className="answer-box"><input type="text" inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value.replace(/\D/g, ""))} /></span></label>
            <label className="answer"><span className="field-label">Price each</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} /></span></label>
            <button className="button-outline" disabled={act.busy || ticker.length !== 3 || !(count > 0) || priceKobo === null}>Place the order</button>
          </form>
          <form className="inline-form" onSubmit={(event) => {
            event.preventDefault();
            if (Number(units) > 0) act.run("POST", "/empire/bonds", { code, side, units: Number(units) }).then((ok) => ok && setUnits(""));
          }}>
            <label className="answer"><span className="field-label">Bond or bill code (from the <a href="#/market/bonds">Bonds and bills</a> page)</span><span className="answer-box"><input type="text" maxLength={12} value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></span></label>
            <label className="answer"><span className="field-label">Number</span><span className="answer-box"><input type="text" inputMode="numeric" value={units} onChange={(event) => setUnits(event.target.value.replace(/\D/g, ""))} /></span></label>
            <button className="button-outline" disabled={act.busy || code.length < 3 || !(Number(units) > 0)}>{side === "buy" ? "Buy" : "Sell"} for the empire</button>
          </form>
        </>
      ) : <p className="muted small">Only the empire's Asset Managers, and its head, place its trades.</p>}
      {room.shared.map((other) => (
        <div key={other.name} className="definition">
          <div className="row"><span className="strong">Shared with us by {other.name}</span><span className="muted small">under a pact to share information</span></div>
          <div className="muted small">Cash {formatCompact(other.cash_kobo)} · shares {formatCompact(other.shares_value_kobo)} · bonds {formatCompact(other.bonds_value_kobo)}{other.lines.length > 0 && ` · holds ${other.lines.map((l) => l.ticker).join(", ")}`}</div>
        </div>
      ))}
    </Panel>
  );
}

function Books({ room, act }: { room: EmpireRoom; act: Act }) {
  return (
    <Panel title="The books" aside="Every payment out of the empire that is not a trade">
      {room.books.length === 0 && <p className="muted small">Nothing has been paid out yet.</p>}
      {room.books.length > 0 && (
        <div className="scroll">
          <table>
            <thead><tr><th scope="col">Quarter</th><th scope="col">Entered as</th><th scope="col" className="num">Amount</th><th scope="col"></th></tr></thead>
            <tbody>
              {room.books.slice(0, 25).map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.period_label}</td>
                  <th scope="row">{entry.category}<div className="muted small">{entry.description}</div></th>
                  <td className="num mono">{formatNaira(entry.amount_kobo)}</td>
                  <td className="num">{entry.found ? <span className="small change-down">✕ proved false</span>
                    : <button className="button-quiet" disabled={act.busy} onClick={() => act.run("POST", "/empire/reports", { book_id: entry.id })}>Report it</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        The books show what each payment was entered as. They do not show who entered it, or whether it is what it says: that
        is what an audit finds. If you report an entry and it is proved false, you are paid a tenth of what is recovered. A
        report that proves groundless costs you a little reputation. Three reports a quarter.
      </p>
      <div className="definition shadow">
        <div className="why-title">THE SHADOW SIDE</div>
        <p className="small">
          You may sign for a cost that is not real, and the money comes to you. In the books it reads "{room.disguise}". It
          leaves a trail: if an audit proves it, you repay it with a fine of the same amount again, lose your seat and
          reputation, and it goes on your legal record. What you cannot repay is taken from your salary.
        </p>
        <AmountForm label={`Sign for a cost (limit ${formatNaira(room.signing_limit_kobo)} a quarter, ${formatNaira(room.signing_used_kobo)} used)`}
                    button="Sign for it" busy={act.busy} onSubmit={(kobo) => act.run("POST", "/empire/expenses", { amount_kobo: kobo })} />
        {room.your_entries.map((entry) => (
          <div key={entry.id} className="row"><span>{entry.period_label} · {entry.category}</span>
            <span className="mono">{formatNaira(entry.amount_kobo)} {entry.found ? <span className="change-down small">✕ found</span> : <span className="muted small">not found</span>}</span></div>
        ))}
      </div>
    </Panel>
  );
}

function Audits({ room, act }: { room: EmpireRoom; act: Act }) {
  const [chosen, setChosen] = useState<number[]>([]);
  const KIND = { accountant: "An Accountant's audit", staff: "The staff Accountant's audit", ai: "The AI audit" } as const;
  return (
    <Panel title="Audits and what follows" aside={room.audit_season ? "● Audit season: the AI audit can be hired" : `Next audit season: ${room.next_audit_season}`}>
      {room.open_audit && (
        <div className="definition row-chosen">
          <div className="strong">Your audit found {room.open_audit.findings.length} false {room.open_audit.findings.length === 1 ? "entry" : "entries"}</div>
          <p className="muted small">Tick the entries you put in the report. What you leave out stays hidden: that choice is yours, and it is on you.</p>
          {room.open_audit.findings.map((finding) => (
            <label key={finding.book_id} className="choice-option">
              <input type="checkbox" checked={chosen.includes(finding.book_id)}
                     onChange={(event) => setChosen(event.target.checked ? [...chosen, finding.book_id] : chosen.filter((id) => id !== finding.book_id))} />
              {" "}{finding.period_label} · {finding.category} · {formatNaira(finding.amount_kobo)}{finding.yours && " · your own entry"}
            </label>
          ))}
          <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/empire/audits/${room.open_audit!.id}`, { report: chosen }).then(() => setChosen([]))}>File the report</button>
        </div>
      )}
      <div className="step-actions">
        {room.can_audit && !room.open_audit && <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", "/empire/audits")}>Audit the books (once a quarter)</button>}
        <button className="button-outline" disabled={act.busy || !room.audit_season || room.ai_audit_done} onClick={() => act.run("POST", "/empire/ai-audit")}>
          Hire the AI audit · {formatCompact(room.ai_audit_fee_kobo)} {room.is_head ? "from the empire" : "from your own cash"}
        </button>
      </div>
      <p className="muted small">
        The AI audit checks every entry of the last four quarters against every member's own statement, and is right 95 times
        in 100. It can be hired only in an audit season (the last quarter of each game year), once, and its fee is large.
        An Accountant's audit covers two quarters; how much it finds depends on the Accountant's level against the level of
        whoever disguised the entry.
      </p>
      {room.audits.map((audit) => (
        <div key={audit.id} className="row">
          <span>{KIND[audit.kind]} <span className="muted small">· {audit.from_period_label}{audit.to_period_label !== audit.from_period_label ? ` to ${audit.to_period_label}` : ""}{audit.status === "open" ? " · not yet filed" : ""}</span></span>
          <span className="mono small">{audit.examined} entries · {audit.reported} called false</span>
        </div>
      ))}
      {room.cases.length > 0 && <div className="why-title">PROVED THEFTS</div>}
      {room.cases.map((item) => (
        <div key={item.id} className="definition">
          <div className="row">
            <span><span className="strong">{item.who}</span> took {formatNaira(item.amount_kobo)} <span className="muted small">· entered as "{item.category}", {item.period_label}</span></span>
            <span className={item.status === "open" ? "tag tag-active" : item.status === "punished" ? "tag tag-failed" : "tag"}>{item.status === "open" ? "● Awaiting the head" : item.status === "punished" ? "✕ Punished" : "Forgiven"}</span>
          </div>
          {item.status === "punished" && <div className="muted small">Repaid {formatNaira(item.repaid_kobo)}, including a fine of {formatNaira(item.fine_kobo)}.{BigInt(item.debt_left_kobo) > 0n && ` Still owes ${formatNaira(item.debt_left_kobo)}, taken from salary.`} Sacked; reputation down; on their legal record.</div>}
          {item.status === "open" && room.is_head && (
            <div className="step-actions">
              <button className="button-primary" disabled={act.busy} onClick={() => act.run("PUT", `/empire/cases/${item.id}`, { punish: true })}>Repay with a fine, and sack</button>
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/empire/cases/${item.id}`, { punish: false })}>Forgive</button>
            </div>
          )}
        </div>
      ))}
      <p className="muted small">Courts, juries and sentences arrive with the law stage. Until then the head of the empire decides.</p>
    </Panel>
  );
}

function Pacts({ room, act }: { room: EmpireRoom; act: Act }) {
  const [to, setTo] = useState("");
  const [kind, setKind] = useState("alliance");
  const [terms, setTerms] = useState("");
  const chosen = room.pact_kinds.find((k) => k.code === kind);
  return (
    <Panel title="Secret pacts" aside="Hidden from everybody outside the two empires">
      {room.pacts.length === 0 && <p className="muted small">The empire has no pacts.</p>}
      {room.pacts.map((pact) => (
        <div key={pact.id} className="definition">
          <div className="row">
            <span><span className="strong">With {pact.with}</span> <span className="muted small">· {pact.kind}</span></span>
            <span className="small">{pact.status}{pact.exposed && " · ▼ uncovered"}{!pact.legal && <span className="change-down"> · unlawful</span>}</span>
          </div>
          <div className="small">"{pact.terms}"</div>
          {room.is_head && (
            <div className="step-actions">
              {pact.ours && pact.status === "drafted" && <button className="button-outline" disabled={act.busy} onClick={() => act.run("PUT", `/empire/pacts/${pact.id}`, { action: "sign" })}>Sign and send</button>}
              {!pact.ours && pact.status === "proposed" && <>
                <button className="button-outline" disabled={act.busy} onClick={() => act.run("PUT", `/empire/pacts/${pact.id}`, { action: "sign" })}>Sign</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/empire/pacts/${pact.id}`, { action: "refuse" })}>Refuse</button></>}
              {pact.status === "signed" && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/empire/pacts/${pact.id}`, { action: "break" })}>Break it (costs trust)</button>}
              {pact.status === "signed" && !pact.legal && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", `/empire/pacts/${pact.id}`, { action: "report" })}>Report it</button>}
            </div>
          )}
        </div>
      ))}
      {room.can_draft && (
        <form className="stack-form" onSubmit={(event) => {
          event.preventDefault();
          act.run("POST", "/empire/pacts", { to_empire: Number(to), kind, terms }).then((ok) => ok && setTerms(""));
        }}>
          <div className="why-title">DRAFT A PACT</div>
          <label className="answer"><span className="field-label">With</span>
            <select value={to} onChange={(event) => setTo(event.target.value)}><option value="">Choose an empire…</option>{room.others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
          <label className="answer"><span className="field-label">Kind of agreement</span>
            <select value={kind} onChange={(event) => setKind(event.target.value)}>{room.pact_kinds.map((k) => <option key={k.code} value={k.code}>{k.label}{k.legal ? "" : " (unlawful)"}</option>)}</select></label>
          {chosen && !chosen.legal && <p className="small change-down">▼ This kind of agreement is an offence. If it is uncovered, both empires lose trust, and the law stage will add penalties.</p>}
          <label className="answer"><span className="field-label">The terms: what each side must do</span><textarea rows={3} maxLength={400} value={terms} onChange={(event) => setTerms(event.target.value)} /></label>
          <button className="button-outline" disabled={act.busy || !to || terms.trim().length < 10}>Save the draft</button>
          <p className="muted small">A pact is drafted by a Lawyer, signed by both heads, and can be broken by either side at any moment. Journalists can uncover it.</p>
        </form>
      )}
    </Panel>
  );
}

export function Chat({ room, act }: { room: EmpireRoom; act: Act }) {
  const [body, setBody] = useState("");
  return (
    <Panel title="War Room chat" aside={`${room.humans} members`}>
      <div className="chat" role="log" aria-live="polite">
        {room.messages.length === 0 && <p className="muted small">Nobody has said anything yet.</p>}
        {room.messages.map((message) => (
          <div key={message.id} className={message.yours ? "chat-line yours" : "chat-line"}>
            <div className="muted small">{message.yours ? "You" : message.who} · {when(message.at)}</div>
            <div>{message.body}</div>
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={(event) => {
        event.preventDefault();
        if (body.trim()) act.run("POST", "/empire/messages", { body }).then((ok) => ok && setBody(""));
      }}>
        <input type="text" aria-label="Your message" maxLength={500} value={body} onChange={(event) => setBody(event.target.value)} placeholder="Say something to your empire" />
        <button className="button-outline" disabled={act.busy || !body.trim()}>Send</button>
      </form>
      <p className="muted small">Voice chat is not connected yet: it needs an outside voice service, which is a decision for the owner. Text chat works now.</p>
    </Panel>
  );
}

function needs(room: EmpireRoom) {
  const cards: { tag: string; title: string; text: string }[] = [];
  for (const step of room.task?.steps ?? []) {
    if (step.yours_to_take) cards.push({ tag: "YOUR STEP", title: step.what, text: `The step before it is done. ${room.task?.company} is waiting on your build.` });
    if (step.yours_to_approve) cards.push({ tag: "APPROVAL", title: "Approve the investment", text: "Every build has reported. The decision is yours as head." });
  }
  if (room.open_audit) cards.push({ tag: "AUDIT", title: "File your audit report", text: `${room.open_audit.findings.length} false entries found. Decide what goes in the report.` });
  if (room.is_head) {
    for (const item of room.cases.filter((c) => c.status === "open")) cards.push({ tag: "PROVED THEFT", title: `${item.who} took ${formatNaira(item.amount_kobo)}`, text: "An audit proved it. Decide what follows." });
    if (room.applications.length > 0) cards.push({ tag: "APPLICATIONS", title: `${room.applications.length} asking for a seat`, text: "Accept or refuse them under Seats." });
    for (const pact of room.pacts.filter((p) => (p.ours && p.status === "drafted") || (!p.ours && p.status === "proposed"))) cards.push({ tag: "PACT", title: `A pact with ${pact.with} needs your signature`, text: pact.kind });
  }
  return cards.slice(0, 3);
}

export function EmpireWork({ player, onLoggedOut, onChanged }: Props) {
  const { loaded, view, act } = useEmpire(player, onLoggedOut, onChanged);
  if (loaded.loading && !view) return <Loading what="the empires" />;
  if (!view) return <Failed message={loaded.error ?? "Could not load the empires."} onRetry={loaded.reload} />;
  const room = view.room;
  const cards = room && room.status === "active" ? needs(room) : [];
  return (
    <>
      <div className="work-head">
        <h1>{room ? room.name : "Empires"}</h1>
        <span className="muted small">{room ? (room.status === "forming" ? "Being founded" : room.run_by_computer ? "Run by the computer until a player earns its head" : room.is_head ? "You are its Acting Head" : "War Room") : "Join one, or found your own"}</span>
      </div>
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
      {room && room.status === "active" && (
        <section aria-label="Needs you now">
          {cards.length === 0 ? <p className="muted">Nothing in the War Room is waiting on you.</p> : (
            <div className="queue">
              {cards.map((card, index) => (
                <article key={card.title} className={index === 0 ? "card card-first" : "card"}>
                  <div className="card-top"><span className="card-tag">{card.tag}</span></div>
                  <h3>{card.title}</h3><p className="muted">{card.text}</p>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
      {room && room.status === "forming" && <><Founding room={room} act={act} /><Seats room={room} act={act} /></>}
      {room && room.status === "active" && (
        <>
          <Task room={room} act={act} />
          <Seats room={room} act={act} />
          <Treasury room={room} act={act} />
          <Books room={room} act={act} />
          <Audits room={room} act={act} />
          <Pacts room={room} act={act} />
        </>
      )}
      {!room && <Directory view={view} player={player} act={act} />}
      {room && (
        <>
          <Directory view={view} player={player} act={act} />
          <Panel title="Leaving">
            <div className="step-actions">
              <span className="muted small">{room.is_head && room.humans > 1 ? "If you leave, the most experienced member becomes Acting Head." : "You can take a seat in another empire afterwards."}</span>
              {room.status === "active" && <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", "/empire/seat")}>Leave {room.name}</button>}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}

export function EmpireRail({ player, onLoggedOut, onChanged }: Props) {
  const { view, act } = useEmpire(player, onLoggedOut, onChanged);
  const room = view?.room;
  if (!view) return null;
  if (!room) {
    return (
      <Panel title="Why join an empire?">
        <ul className="reasons">
          <li>Work that needs every build: tasks handed from one build to the next.</li>
          <li>The empire pays for the steps you do, on top of your salary.</li>
          <li>Asset Managers trade the empire's money, far more than their own.</li>
          <li>A place in the league of empires.</li>
        </ul>
      </Panel>
    );
  }
  return (
    <>
      <Chat room={room} act={act} />
      <Panel title="Your part">
        <div className="row"><span>Your seat</span><span>{room.seats.find((s) => s.you)?.build_name}{room.is_head ? " · Acting Head" : ""}</span></div>
        <div className="row"><span>You may sign for, a quarter</span><span className="mono">{formatNaira(room.signing_limit_kobo)}</span></div>
        {room.can_trade && <div className="row"><span>You may trade, a quarter</span><span className="mono">{formatCompact(room.trade_limit_kobo)}</span></div>}
        <div className="row"><span>Head approves</span><span>investments, bonuses, recruits, pacts</span></div>
        <div className="row"><span>Trust in the empire</span><span className="mono">{room.trust} of 100 <span className="muted">({formatPercent(room.trust * 100, 0)})</span></span></div>
      </Panel>
      <Panel title="Decision log" aside="Permanent">
        {room.events.slice(0, 12).map((event, index) => (
          <div key={index} className="news-line"><div className="small muted">{when(event.at)}</div><div className="small">{event.words}</div></div>
        ))}
      </Panel>
      {room.legal_record.length > 0 && (
        <Panel title="Your legal record">
          {room.legal_record.map((line, index) => <div key={index} className="news-line"><div className="small muted">{when(line.at)}</div><div className="small">{line.words}</div></div>)}
        </Panel>
      )}
    </>
  );
}
