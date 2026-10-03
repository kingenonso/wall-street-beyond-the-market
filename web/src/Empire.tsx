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
import { BondOrderForm, ShareOrderForm } from "./TradeForm";

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
      <Panel title="The league of empires" aside={`Game year ${d.season} · divisions of ${d.division_size}`}>
        <p className="small">
          An empire is a team of thirteen: a head, and two seats for each of the six builds. Five empires run by the computer
          have existed since the first day, and take any player they have a seat for. A seat is in addition to your job: your
          employer still pays your salary, and the empire pays for the work you do for it.
        </p>
        <p className="small">
          Empires compete in divisions. Points come from finishing tasks ({d.league_points.task} each), work passed for the empire
          ({d.league_points.work}), weekend challenges passed by members ({d.league_points.challenge}), and how the empire's worth
          grew over the game year (a point for each 1%, up to {d.league_points.growth_most}; money put in by members is left out,
          so growth cannot be bought). An unlawful pact that comes to light costs {-d.league_points.theft}. As each game year ends, the
          top of a division goes up and the bottom goes down.
        </p>
        {d.divisions.map((division) => (
          <div key={division.division}>
            <div className="why-title">DIVISION {division.division}</div>
            <div className="scroll">
              <table>
                <thead><tr><th scope="col" className="num">Place</th><th scope="col">Empire</th><th scope="col">Run by</th><th scope="col" className="num">Points</th><th scope="col" className="num">Worth</th><th scope="col" className="num">Players</th><th scope="col" className="num">Trust</th><th scope="col"></th></tr></thead>
                <tbody>
                  {division.empires.map((row) => {
                    const entry = d.league.find((e) => e.id === row.id);
                    return (
                      <tr key={row.id} className={row.yours ? "row-chosen" : undefined}>
                        <td className="num mono">{row.place}{row.zone === "up" && <span className="change-up" title="Going up if the year ended today"> ▲</span>}{row.zone === "down" && <span className="change-down" title="Going down if the year ended today"> ▼</span>}</td>
                        <th scope="row">{row.name}</th>
                        <td>{row.run_by}</td>
                        <td className="num mono strong">{row.points}</td>
                        <td className="num mono">{formatCompact(row.worth_kobo)}</td>
                        <td className="num mono">{row.members} of 12</td>
                        <td className="num mono">{row.trust}</td>
                        <td className="num">
                          {row.yours ? <span className="saved small">✓ Yours</span>
                            : entry?.applied ? <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", "/empire/application")}>Withdraw application</button>
                            : !view.room && entry && <button className="button-quiet" disabled={act.busy || !player.build || entry.seats_open === 0}
                                       onClick={() => act.run("POST", `/empires/${row.id}/applications`)}>
                                {entry.seats_open === 0 ? "No seat for your build" : row.run_by === "the computer" ? "Take a seat" : "Apply"}
                              </button>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))}
        <p className="muted small">▲ would go up, ▼ would go down, if the game year ended today. A newly opened empire enters the bottom division.</p>
        {d.seasons.length > 0 && (
          <>
            <div className="why-title">HOW PAST GAME YEARS ENDED</div>
            {d.seasons.map((season) => (
              <div key={season.season} className="small">
                <span className="strong">Year {season.season}:</span>{" "}
                {season.rows.filter((r) => r.moved !== "stayed").length === 0 ? "nobody moved between divisions."
                  : season.rows.filter((r) => r.moved !== "stayed").map((r) => `${r.name} went ${r.moved} (${r.points} points)`).join("; ") + "."}
              </div>
            ))}
          </>
        )}
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
            retirement savings (up to half) may be used here: it is paid straight into the empire, and goes back to your savings if
            the founding is cancelled.
          </p>
          {d.can_found ? (
            <form className="stack-form" onSubmit={(event) => {
              event.preventDefault();
              if (amountKobo !== null || asKobo(savings) !== null) act.run("POST", "/empires", { name, amount_kobo: amountKobo ?? 0, from_savings_kobo: asKobo(savings) ?? 0 });
            }}>
              <label className="answer"><span className="field-label">Name of the empire</span><span className="answer-box"><input type="text" maxLength={40} value={name} onChange={(event) => setName(event.target.value)} /></span></label>
              <label className="answer"><span className="field-label">Your own cash, put in now</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></span></label>
              <label className="answer"><span className="field-label">And, drawn early from your retirement savings, paid straight into the empire (optional)</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={savings} onChange={(event) => setSavings(event.target.value)} /></span></label>
              <button className="button-primary" disabled={act.busy || name.trim().length < 3 || (amountKobo === null && asKobo(savings) === null)}>Begin founding</button>
            </form>
          ) : <p className="muted small">You {player.level ? `are Level ${player.level}` : "have no build yet"}. Founding opens at Level {d.founding_level}.</p>}
        </Panel>
      )}

      {d.build_table && d.build_table.top.length > 0 && (
        <Panel title={`${d.build_table.name}s, ranked`} aside={d.build_table.your_place ? `You are ${d.build_table.your_place} of ${d.build_table.players}` : `${d.build_table.players} players`}>
          <p className="muted small">Every player is ranked within their build: by level, then by experience.</p>
          {d.build_table.top.slice(0, 10).map((row) => (
            <div key={row.place} className={row.you ? "row row-chosen" : "row"}>
              <span><span className="mono">{row.place}.</span> {row.name}{row.you && <span className="muted small"> · you</span>}</span>
              <span className="mono">Level {row.level} <span className="muted small">· {row.rank_name}</span></span>
            </div>
          ))}
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
                <td>{seat.name}{seat.head && <span className="tag tag-active"> ★ {room.head_is_ceo ? "CEO" : "Acting Head"}</span>}{seat.ceo && !seat.head && <span className="muted small"> · holds the CEO rank</span>}{seat.resigning && <span className="small change-down"> · ▼ has resigned</span>}{seat.legal.length > 0 && <span className="small change-down"> · ✕ legal record</span>}{seat.lead && !seat.head && <span className="muted small"> · lead</span>}{seat.you && <span className="muted small"> · you</span>}</td>
                <td className="num mono">{seat.level ?? "—"}</td>
                {room.is_head && <td className="num mono">{seat.held ? (seat.signing_limit_kobo ? formatNaira(seat.signing_limit_kobo) : "the usual") : "—"}</td>}
                <td className="num">
                  {room.is_head && room.status === "active" && !seat.held && (
                    <button className="button-quiet" disabled={act.busy} onClick={() => act.run("PUT", "/empire/staff", { build: seat.build, slot: seat.slot, staffed: !seat.staffed })}>
                      {seat.staffed ? "Let the staff go" : "Hire staff"}
                    </button>
                  )}
                  {room.is_head && room.status === "active" && seat.held && seat.player_id && !seat.you && (
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
      {room.is_head && room.seats.some((seat) => seat.legal.length > 0) && (
        <div className="definition">
          <div className="why-title">LEGAL RECORDS OF YOUR MEMBERS</div>
          <p className="muted small">A theft proved against a member, here or at an empire they have left, is on their legal record. They do not lose their seat with you for it: whether they stay is your decision.</p>
          {room.seats.filter((seat) => seat.legal.length > 0).map((seat) => (
            <div key={`${seat.build}${seat.slot}`}>
              <div className="strong small">{seat.name}</div>
              {seat.legal.map((line, index) => <div key={index} className="small"><span className="muted">{when(line.at)}:</span> {line.words}</div>)}
            </div>
          ))}
        </div>
      )}
      {room.is_head && bonus && (
        <div className="definition">
          <AmountForm label={`Pay this member a bonus from the empire's cash (bonuses of up to ${formatCompact(room.bonus_limit_kobo)} a quarter in all)`} button="Pay bonus" busy={act.busy}
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
          <p className="muted small">Staff work at a fixed Level 40, reliably and slowly, and are paid by the empire each quarter. Staff who are let go are paid for the quarter. An empty seat with no staff does no work.</p>
        </div>
      )}
      {room.applications.length > 0 && (
        <>
          <div className="why-title">ASKING FOR A SEAT</div>
          {room.applications.map((asked) => (
            <div key={asked.id} className="row">
              <span>{asked.display_name} <span className="muted small">· {asked.build.replace("_", " ")}</span>
                {asked.legal.length > 0 ? <span className="small change-down"> · ✕ legal record: {asked.legal[0].words}</span> : <span className="muted small"> · no legal record</span>}</span>
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

function Treasury({ room, act, onLoggedOut }: { room: EmpireRoom; act: Act; onLoggedOut: () => void }) {
  return (
    <Panel title="The empire's money" aside={room.place ? `${room.place} of ${room.empires} empires by worth` : undefined}>
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
            {room.is_head ? "As head you trade without a limit." : `Your limit for the quarter is ${formatNaira(room.trade_limit_kobo)}; ${formatNaira(room.trade_used_kobo)} is used.${room.run_by_computer ? " In an empire the computer runs, the limit is a share of the empire that grows with your rank: 0.5% as an Associate, 2% as a Professional, 5% as a Senior, 10% as a Principal, 20% as a Master." : ""}`} What you buy
            belongs to the empire, not to you. Buying what the empire's task calls for is outside your limit.
            {room.fair_dealing && " An empire run by the computer deals within 2% of the last session's price."} You cannot deal with the empire yourself.
          </p>
          <div className="why-title">SHARES</div>
          <ShareOrderForm whose="The empire" busy={act.busy} held={room.holdings} fairDealing={room.fair_dealing} onLoggedOut={onLoggedOut}
                          onPlace={(order) => act.run("POST", "/empire/orders", { ...order, kind: "limit" })} />
          <div className="why-title">BONDS AND BILLS</div>
          <BondOrderForm whose="The empire" busy={act.busy} held={room.bond_holdings} onLoggedOut={onLoggedOut}
                         onPlace={(order) => act.run("POST", "/empire/bonds", order)} />
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

function Leaving({ room, act }: { room: EmpireRoom; act: Act }) {
  const [letter, setLetter] = useState("");
  const [writing, setWriting] = useState(false);
  const mine = room.resignation;
  const date = (iso: string) => new Date(iso).toLocaleString("en-NG", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
  return (
    <Panel title="Leaving the empire" aside={mine ? "● Your letter is in" : "By resignation letter"}>
      {!mine && (
        <>
          <p className="small">
            {room.status === "forming" ? "The empire is not open yet. If you leave now you go at once, and what you put in is handed back."
              : room.run_by_computer ? "Nobody leaves an empire overnight. Hand in a resignation letter and you leave when this quarter ends. Until then you are a member in full: you work, you are paid, and you may withdraw the letter."
              : `Nobody leaves an empire overnight. Hand in a resignation letter and the head is told. You then work out a notice of ${room.notice_days} real days, as a member in full: you work, you are paid, and you may withdraw the letter. The head may make you an offer to stay, or let you go early. If nothing is agreed, you leave when the notice has run.`}
            {room.is_head && room.humans > 1 && " When a head leaves, the most experienced member becomes Acting Head."}
          </p>
          {writing ? (
            <form className="stack-form" onSubmit={(event) => { event.preventDefault(); act.run("POST", "/empire/resignation", { letter }).then((ok) => ok && setWriting(false)); }}>
              <label className="answer"><span className="field-label">Your letter (the head reads it; it can be left empty)</span>
                <textarea rows={3} maxLength={600} value={letter} onChange={(event) => setLetter(event.target.value)} /></label>
              <div className="step-actions">
                <button className="button-primary" disabled={act.busy}>Hand in the letter</button>
                <button type="button" className="button-quiet" onClick={() => setWriting(false)}>Not now</button>
              </div>
            </form>
          ) : <button className="button-quiet" disabled={act.busy} onClick={() => setWriting(true)}>Write a resignation letter</button>}
          <p className="muted small">Leaving does not close the books behind you: an audit can still prove a theft after you have gone, and you answer for it wherever you are.</p>
        </>
      )}
      {mine && (
        <>
          <p className="small">
            You handed in your letter on {date(mine.given_at)}.{" "}
            {mine.leaves_at ? <>You leave on <span className="strong">{date(mine.leaves_at)}</span> unless you withdraw it or accept an offer to stay.</>
              : <>You leave when <span className="strong">{mine.leaves_label}</span> ends, unless you withdraw it.</>}
          </p>
          {mine.offer ? (
            <div className="definition row-chosen">
              <div className="strong">The head has made you an offer to stay</div>
              {BigInt(mine.offer.bonus_kobo) > 0n && <div className="row"><span>A bonus, paid the moment you accept</span><span className="mono">{formatNaira(mine.offer.bonus_kobo)}</span></div>}
              {mine.offer.signing_limit_kobo != null && <div className="row"><span>What you may sign for in a quarter</span><span className="mono">{formatNaira(mine.offer.signing_limit_kobo)}</span></div>}
              {mine.offer.words && <p className="small">"{mine.offer.words}"</p>}
              <div className="step-actions">
                <button className="button-primary" disabled={act.busy} onClick={() => act.run("POST", "/empire/resignation/acceptance")}>Accept and stay</button>
                <span className="muted small">If you do not accept, your letter stands.</span>
              </div>
            </div>
          ) : !room.run_by_computer && !room.is_head && <p className="muted small">The head has not made an offer.</p>}
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", "/empire/resignation")}>Withdraw my letter and stay</button>
        </>
      )}
    </Panel>
  );
}

function Resignations({ room, act }: { room: EmpireRoom; act: Act }) {
  const [open, setOpen] = useState<number | null>(null);
  const [bonus, setBonus] = useState("");
  const [limit, setLimit] = useState("");
  const [words, setWords] = useState("");
  if (!room.is_head || room.resignations.length === 0) return null;
  const date = (iso: string) => new Date(iso).toLocaleString("en-NG", { weekday: "short", day: "numeric", month: "short" });
  return (
    <Panel title="Resignation letters" aside={`${room.resignations.length} waiting`}>
      {room.resignations.map((letter) => (
        <div key={letter.id} className="definition">
          <div className="row"><span className="strong">{letter.name}</span><span className="small">{letter.leaves_at ? `leaves ${date(letter.leaves_at)}` : `leaves when ${letter.leaves_label} ends`}</span></div>
          {letter.letter && <p className="small">"{letter.letter}"</p>}
          {letter.offer && <div className="small saved">✓ You offered{BigInt(letter.offer.bonus_kobo) > 0n ? ` a bonus of ${formatNaira(letter.offer.bonus_kobo)}` : ""}{letter.offer.signing_limit_kobo ? `${BigInt(letter.offer.bonus_kobo) > 0n ? " and" : ""} a signing limit of ${formatNaira(letter.offer.signing_limit_kobo)}` : ""}. Nothing is paid until they accept.</div>}
          <div className="step-actions">
            <button className="button-outline" disabled={act.busy} onClick={() => setOpen(open === letter.id ? null : letter.id)}>{letter.offer ? "Change the offer" : "Make an offer to stay"}</button>
            <button className="button-quiet" disabled={act.busy} onClick={() => act.run("DELETE", `/empire/resignations/${letter.id}`)}>Let them go now</button>
          </div>
          {open === letter.id && (
            <form className="stack-form" onSubmit={(event) => {
              event.preventDefault();
              act.run("PUT", `/empire/resignations/${letter.id}/offer`, { bonus_kobo: asKobo(bonus) ?? 0, signing_limit_kobo: asKobo(limit), words }).then((ok) => ok && setOpen(null));
            }}>
              <label className="answer"><span className="field-label">A bonus from the empire's cash (up to {formatCompact(room.counter_offer_most_kobo)})</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={bonus} onChange={(event) => setBonus(event.target.value)} /></span></label>
              <label className="answer"><span className="field-label">And, or instead: what they may sign for in a quarter</span><span className="answer-box"><span className="muted small">₦</span><input type="text" inputMode="decimal" value={limit} onChange={(event) => setLimit(event.target.value)} /></span></label>
              <label className="answer"><span className="field-label">A few words (optional)</span><textarea rows={2} maxLength={400} value={words} onChange={(event) => setWords(event.target.value)} /></label>
              <button className="button-primary" disabled={act.busy || (asKobo(bonus) === null && asKobo(limit) === null)}>Send the offer</button>
            </form>
          )}
        </div>
      ))}
    </Panel>
  );
}

function Election({ room, act }: { room: EmpireRoom; act: Act }) {
  const candidates = room.seats.filter((seat) => seat.held && seat.ceo && !seat.head);
  if (!room.election.open) return null;
  return (
    <Panel title="Who leads" aside={room.head_is_ceo ? "Led by a CEO" : "Led by an Acting Head"}>
      <p className="small">
        A founder leads as Acting Head, with capped powers: signing for 2% of the empire's cash in a quarter, bonuses of a tenth
        of its worth, and investments of up to ₦50 million. A head who has earned the <a href="#/rank">CEO rank</a> leads as CEO:
        5% of cash, bonuses of a quarter of its worth, investments of up to ₦200 million. Any member who holds the CEO rank can
        be voted in by the empire: it takes the votes of more than half its players ({room.election.needed} now).
      </p>
      {candidates.length === 0 && <p className="muted small">No member other than the head holds the CEO rank yet, so there is nobody to vote for.</p>}
      {candidates.map((seat) => (
        <div key={`${seat.build}${seat.slot}`} className="row">
          <span>{seat.name} <span className="muted small">· {seat.build_name}, Level {seat.level} · {room.election.tally.find((t) => t.name === seat.name)?.votes ?? 0} votes</span></span>
          <button className="button-outline" disabled={act.busy} onClick={() => act.run("POST", "/empire/head-votes", { build: seat.build, slot: seat.slot })}>Vote for them</button>
        </div>
      ))}
      {room.election.your_vote && <p className="small saved">✓ Your vote is for {room.election.your_vote}.</p>}
    </Panel>
  );
}

function needs(room: EmpireRoom) {
  const cards: { tag: string; title: string; text: string }[] = [];
  for (const step of room.task?.steps ?? []) {
    if (step.yours_to_take) cards.push({ tag: "YOUR STEP", title: step.what, text: `The step before it is done. ${room.task?.company} is waiting on your build.` });
    if (step.yours_to_approve) cards.push({ tag: "APPROVAL", title: "Approve the investment", text: "Every build has reported. The decision is yours as head." });
  }
  if (room.resignation?.offer) cards.push({ tag: "OFFER TO STAY", title: "The head has made you an offer", text: "Accept it and stay, or let your letter stand. See Leaving the empire, below." });
  for (const letter of room.resignations.filter((r) => !r.offer)) cards.push({ tag: "RESIGNATION", title: `${letter.name} has handed in a letter`, text: "Make an offer to stay, let them go now, or let the notice run." });
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
        <span className="muted small">{room ? (room.status === "forming" ? "Being founded" : room.run_by_computer ? "Run by the computer until a player earns its head" : room.is_head ? (room.head_is_ceo ? "You are its CEO" : "You are its Acting Head") : "War Room") : "Join one, or found your own"}</span>
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
          <Resignations room={room} act={act} />
          <Treasury room={room} act={act} onLoggedOut={onLoggedOut} />
          <Books room={room} act={act} />
          <Audits room={room} act={act} />
          <Pacts room={room} act={act} />
          <Election room={room} act={act} />
        </>
      )}
      {!room && <Directory view={view} player={player} act={act} />}
      {room && (
        <>
          <Directory view={view} player={player} act={act} />
          <Leaving room={room} act={act} />
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
        <div className="row"><span>Your seat</span><span>{room.seats.find((s) => s.you)?.build_name}{room.is_head ? (room.head_is_ceo ? " · CEO" : " · Acting Head") : ""}</span></div>
        <div className="row"><span>You may sign for, a quarter</span><span className="mono">{formatNaira(room.signing_limit_kobo)}</span></div>
        {room.can_trade && <div className="row"><span>You may trade, a quarter</span><span className="mono">{formatCompact(room.trade_limit_kobo)}</span></div>}
        <div className="row"><span>Head approves</span><span>investments, bonuses, recruits, pacts</span></div>
        {room.division && <div className="row"><span>In the league</span><span>Division {room.division.division}, place {room.division.place} of {room.division.of} · <span className="mono">{room.division.points} points</span></span></div>}
        <div className="row"><span>Trust in the empire</span><span className="mono">{room.trust} of 100 <span className="muted">({formatPercent(room.trust * 100, 0)})</span></span></div>
      </Panel>
      {room.league_points.length > 0 && (
        <Panel title="League points this game year">
          {room.league_points.slice(0, 8).map((line, index) => (
            <div key={index} className="row"><span className="small">{line.why}</span><span className={line.points >= 0 ? "mono change-up" : "mono change-down"}>{line.points >= 0 ? "▲ +" : "▼ "}{line.points}</span></div>
          ))}
        </Panel>
      )}
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
