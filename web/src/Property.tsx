// Stage 8: land and property. The districts of the five cities on a map, every building and plot, the
// Auction House with its live countdowns, what the player (and their empire) owns, mortgages, and the
// empire's headquarters. The website only asks: the server checks every bid, and keeps every secret
// (a seller's lowest price, other bidders' limits, a title's flaws) to itself.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  api, ApiError, type Auction, type District, type Headquarters, type Holdings, type MyLot, type PartnerRequest, type Player,
  type LeasebackTerms, type PropertyLot, type PropertyMarket,
} from "./api";
import { asKobo } from "./Empire";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { NumberTile } from "./Parts";
import { Failed, Loading, Panel } from "./Shell";
import { LotExtras, ProjectsTab, SalesAndDevelopments } from "./PropertyMore";
import { Term } from "./Term";

type Props = { player: Player; onLoggedOut: () => void; onChanged?: () => void };
type Tab = "auctions" | "map" | "mine" | "empire" | "projects";

const CITIES = ["Lagos", "Abuja", "Port Harcourt", "Kano", "Aba"];
const STEP_NAMES = { title: "The Investment Banker checks the title", valuation: "The Asset Manager values it", limit: "The Risk Manager sets the top price", money: "The Investment Banker arranges the money" } as const;
const STEP_BUILD = { title: "investment_banker", valuation: "asset_manager", limit: "risk_manager", money: "investment_banker" } as const;
type Step = keyof typeof STEP_NAMES;
const REASON: Record<Auction["reason"], { tag: string; words: string }> = {
  listing: { tag: "Listing", words: "A property company is selling. It has a lowest price nobody sees." },
  owner: { tag: "Owner’s sale", words: "An owner is selling. There may be a lowest price nobody sees." },
  repossession: { tag: "■ Forced sale", words: "The bank is selling it: its mortgage was not paid. There is no lowest price." },
  tax: { tag: "■ Forced sale", words: "Sold for unpaid tax. There is no lowest price." },
};

const pct = (bps: number) => formatPercent(bps, 1);
const index = (bps: number) => (bps / 100).toFixed(1);
const move = (now: number, before: number | undefined) => (before ? Math.round(((now - before) / before) * 10000) : null);

function Arrow({ bps }: { bps: number | null }) {
  if (bps === null) return <span className="muted small">new</span>;
  const dir = bps > 0 ? "up" : bps < 0 ? "down" : "flat";
  return <span className={`mono change-${dir}`}>{bps > 0 ? "▲" : bps < 0 ? "▼" : "–"} {(Math.abs(bps) / 100).toFixed(1)}%</span>;
}

/** The server's time, ticking: countdowns never trust the player's own clock. */
function useServerNow(serverNow: string | undefined): number {
  const offset = useRef(0);
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    if (serverNow) offset.current = new Date(serverNow).getTime() - Date.now();
  }, [serverNow]);
  useEffect(() => {
    const every = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(every);
  }, []);
  return tick + offset.current;
}

function countdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(total / 86400), h = Math.floor((total % 86400) / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  if (d > 0) return `${d}d ${h}h ${String(m).padStart(2, "0")}m`;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export function useAct(reload: () => void, onLoggedOut: () => void, onChanged?: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run(path: string, body: unknown, done: string | ((result: { words?: string }) => string)) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const answer = await api.propertyAct(path, body);
      setNotice(typeof done === "string" ? done : done((answer?.result ?? {}) as { words?: string }));
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
export type Act = ReturnType<typeof useAct>;

function Messages({ act }: { act: Act }) {
  return (
    <>
      {act.error && <p className="error" role="alert">{act.error}</p>}
      {act.notice && <p className="saved" role="status">{act.notice}</p>}
    </>
  );
}

function Condition({ value }: { value: number }) {
  const words = value >= 80 ? "Good" : value >= 50 ? "Fair" : value >= 25 ? "▼ Poor: tenants leave" : "■ Very poor";
  return (
    <span className="small">
      <span className="mono">{value}/100</span> <span className="muted">{words}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// The Auction House
// ---------------------------------------------------------------------------

function AuctionCard({ a, m, now, act, empire, playerBuild }: {
  a: Auction; m: PropertyMarket; now: number; act: Act; empire?: boolean; playerBuild?: string;
}) {
  const [limit, setLimit] = useState("");
  const [bank, setBank] = useState("");
  const [share, setShare] = useState("0");
  const [partner, setPartner] = useState("");
  const [askName, setAskName] = useState("");
  const [askShare, setAskShare] = useState("25");
  const ends = new Date(a.ends_at).getTime();
  const opens = new Date(a.opens_at).getTime();
  const open = a.status === "open" && now >= opens && now < ends;
  const lastMinutes = open && ends - now <= 5 * 60 * 1000;
  const reason = REASON[a.reason];
  const p = a.property;
  const agreed = (empire ? m.empire?.partner_asks : m.my_partner_asks)?.filter((x) => x.auction_id === a.id && x.status === "agreed") ?? [];
  const asked = (empire ? m.empire?.partner_asks : m.my_partner_asks)?.filter((x) => x.auction_id === a.id) ?? [];
  const checks = empire ? m.empire?.checks[String(a.id)] ?? {} : {};
  const bid = () => {
    const k = asKobo(limit);
    if (!k) return;
    if (empire) act.run(`/empire/auctions/${a.id}/bid`, { limit_kobo: k, partner_id: partner ? Number(partner) : null }, "The empire's bid is in.");
    else act.run(`/auctions/${a.id}/bid`, {
      limit_kobo: k, mortgage_bank: Number(share) > 0 ? bank || null : null, mortgage_bps: Math.round(Number(share) * 100),
      partner_id: partner ? Number(partner) : null,
    }, "Your bid is in. Your part of it is held until the auction ends or you are outbid.");
  };
  return (
    <article className="lot" aria-labelledby={`lot-${a.id}-${empire ? "e" : "p"}`}>
      <div className="lot-head">
        <div>
          <span className={`tag ${a.reason === "repossession" || a.reason === "tax" ? "tag-missed" : "tag-open"}`}>{reason.tag}</span>{" "}
          <h3 id={`lot-${a.id}-${empire ? "e" : "p"}`} className="lot-title">{p.name}</h3>
          <div className="muted small">{p.kind_name} · {p.size_m2.toLocaleString("en-NG")} m² · {p.district}, {p.city}</div>
        </div>
        <div className="lot-clock" aria-live={lastMinutes ? "polite" : "off"}>
          {a.status === "sold" ? <span className="tag tag-done">✓ Sold</span>
            : a.status === "unsold" ? <span className="tag tag-refused">✕ Not sold</span>
            : now < opens ? <><div className="lbl">Opens in</div><div className="mono figure-small">{countdown(opens - now)}</div></>
            : <><div className="lbl">{lastMinutes ? "▲ Last minutes" : "Ends in"}</div><div className={`mono figure-small${lastMinutes ? " change-down" : ""}`}>{countdown(ends - now)}</div></>}
        </div>
      </div>
      <div className="lot-figures">
        <div><div className="lbl">{a.price ? "Price now" : "Opening price"}</div><div className="mono">{formatNaira(a.price ?? a.start_price)}</div></div>
        <div><div className="lbl">Next bid at least</div><div className="mono">{formatNaira(a.minimum)}</div></div>
        <div><div className="lbl"><Term word="Guide value">Value when listed</Term></div><div className="mono">{formatCompact(a.fair)}</div></div>
        <div><div className="lbl">Rent a quarter</div><div className="mono">{formatCompact(p.rent_due)}</div></div>
        <div><div className="lbl">Bidders</div><div className="mono">{a.bidders}</div></div>
      </div>
      <div className="row small"><span>Condition</span><Condition value={p.condition} /></div>
      <p className="muted small">{reason.words}{a.reason === "listing" || a.reason === "owner" ? (a.lowest_price_met ? " ✓ The leading bid meets it." : a.price ? " ○ The leading bid does not meet it yet." : "") : ""}</p>
      {a.you_lead && <p className="saved small" role="status">▲ You lead. Your top price ({formatNaira(a.your_limit ?? "0")}) is never shown to anybody else.</p>}
      {a.your_status === "outbid" && <p className="error small">▼ You have been outbid. Your cash is back with you. Bid again to go higher.</p>}
      {a.events.length > 0 && (
        <ul className="lot-events small" aria-label="What has happened">
          {a.events.slice(0, 3).map((e, i) => <li key={i}><span className="muted">{new Date(e.at).toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit" })}</span> {e.words}</li>)}
        </ul>
      )}
      {empire && (
        <div className="lot-checks">
          <div className="lbl">The desks' checks before the empire bids</div>
          <ol className="check-list">
            {(Object.keys(STEP_NAMES) as Step[]).map((step) => (
              <li key={step} className={checks[step] ? "check-done" : "check-todo"}>
                <span aria-hidden="true">{checks[step] ? "✓" : "○"}</span> {STEP_NAMES[step]}
                {checks[step] && <span className="muted small"> · {checkWords(step, checks[step])}</span>}
              </li>
            ))}
          </ol>
          {open && playerBuild && <CheckForm a={a} m={m} act={act} build={playerBuild} head={!!m.empire?.head} />}
        </div>
      )}
      {open && (!empire || m.empire?.head) && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); bid(); }}>
          <label className="answer">Your top price (₦)
            <input type="text" inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder={formatNaira(a.minimum)} />
          </label>
          {!empire && (
            <>
              <label>Mortgage share
                <select value={share} onChange={(e) => setShare(e.target.value)}>
                  {[0, 20, 40, 50, 60, 70, 80].map((n) => <option key={n} value={n}>{n === 0 ? "No mortgage" : `${n}% from a bank`}</option>)}
                </select>
              </label>
              {Number(share) > 0 && (
                <label>Bank
                  <select value={bank} onChange={(e) => setBank(e.target.value)}>
                    <option value="">Choose…</option>
                    {m.banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>
              )}
            </>
          )}
          {agreed.length > 0 && (
            <label>Partner
              <select value={partner} onChange={(e) => setPartner(e.target.value)}>
                <option value="">None</option>
                {agreed.map((x) => <option key={x.id} value={x.id}>{x.partner} · {pct(x.partner_bps)} · up to {formatCompact(x.most ?? "0")}</option>)}
              </select>
            </label>
          )}
          <button className="button-primary" disabled={act.busy || !asKobo(limit) || (Number(share) > 0 && !bank)}>{empire ? "Bid for the empire" : "Bid"}</button>
          <span className="muted small">
            You name the most you will pay. The Auction House bids for you, one step at a time, only as high as it must to keep
            you in the lead. {empire ? "The bid is paid as the Investment Banker arranged." : "Your share of the top price is held until the auction ends."}
          </span>
        </form>
      )}
      {open && a.your_status === "live" && !a.you_lead && a.your_bid_id && (
        <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/auctions/bids/${a.your_bid_id}/withdraw`, { for_empire: !!empire }, "Your bid is withdrawn and your cash is back.")}>Walk away</button>
      )}
      {open && (!empire || m.empire?.head) && (
        <details className="small">
          <summary>Share this bid with a partner{asked.length > 0 ? ` (${asked.length} asked)` : ""}</summary>
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run(`/auctions/${a.id}/partners`, { for_empire: !!empire, partner_player_name: askName, partner_bps: Math.round(Number(askShare) * 100) }, "Asked. They must agree, and set how far they will go, before you can bid together."); }}>
            <label className="answer">Player's name<input type="text" value={askName} onChange={(e) => setAskName(e.target.value)} /></label>
            <label>Their share (%)<input className="small-input" type="number" min={5} max={90} value={askShare} onChange={(e) => setAskShare(e.target.value)} /></label>
            <button className="button-outline" disabled={act.busy || !askName.trim()}>Ask them</button>
          </form>
          {asked.map((x) => <div key={x.id} className="row"><span>{x.partner} · {pct(x.partner_bps)}</span><span className={`tag tag-${x.status === "agreed" ? "done" : x.status === "refused" ? "refused" : "waiting"}`}>{x.status}</span></div>)}
          <p className="muted">A partner holds their share of the price they will go to, and owns that share of the property if you win. A bid shared with a partner cannot also use a mortgage.</p>
        </details>
      )}
    </article>
  );
}

function checkWords(step: Step, c: Record<string, unknown>): string {
  if (step === "title") return c.clean ? "clean" : "▲ a claim on part of it";
  if (step === "valuation") return `worth ${formatCompact(String(c.value ?? 0))}`;
  if (step === "limit") return `top price ${formatCompact(String(c.limit ?? 0))}`;
  return c.mortgage_bps ? `${pct(Number(c.mortgage_bps))} borrowed` : "cash, no loan";
}

function CheckForm({ a, m, act, build, head }: { a: Auction; m: PropertyMarket; act: Act; build: string; head: boolean }) {
  const [amount, setAmount] = useState("");
  const [bank, setBank] = useState("");
  const [share, setShare] = useState("0");
  const done = m.empire?.checks[String(a.id)] ?? {};
  const staffed = m.empire?.desks_with_members ?? [];
  const mine = (Object.keys(STEP_BUILD) as Step[]).filter((s) => STEP_BUILD[s] === build);
  // The head does a check only for a desk nobody sits at.
  const steps = [...mine, ...(head ? (Object.keys(STEP_BUILD) as Step[]).filter((s) => !staffed.includes(STEP_BUILD[s]) && !mine.includes(s)) : [])];
  if (steps.length === 0) return null;
  const waiting = steps.filter((s) => !done[s]).length;
  return (
    <details className="small" open={waiting > 0 && steps.length === 1}>
      <summary>{waiting > 0 ? `Your check${steps.length > 1 ? "s" : ""}: ${waiting} to do` : "Your checks are done (you may redo them)"}</summary>
      {steps.map((step) => (
        <form key={step} className="inline-form" onSubmit={(e) => {
          e.preventDefault();
          const body: Record<string, unknown> = { step };
          if (step === "valuation") body.value_kobo = asKobo(amount);
          if (step === "limit") body.limit_kobo = asKobo(amount);
          if (step === "money") { body.mortgage_bps = Math.round(Number(share) * 100); body.bank = Number(share) > 0 ? bank : null; }
          act.run(`/empire/auctions/${a.id}/check`, body, `${STEP_NAMES[step]}: done.`);
        }}>
          <span className="small">{STEP_NAMES[step]}{!mine.includes(step) ? " (nobody sits at that desk, so the head does it)" : ""}</span>
          {(step === "valuation" || step === "limit") && (
            <label className="answer">{step === "valuation" ? "What it is worth (₦)" : "The most the empire may pay (₦)"}
              <input type="text" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </label>
          )}
          {step === "money" && (
            <>
              <label>Borrow
                <select value={share} onChange={(e) => setShare(e.target.value)}>
                  {[0, 20, 40, 50, 60].map((n) => <option key={n} value={n}>{n === 0 ? "Nothing: pay in cash" : `${n}% of the price`}</option>)}
                </select>
              </label>
              {Number(share) > 0 && (
                <label>Bank<select value={bank} onChange={(e) => setBank(e.target.value)}><option value="">Choose…</option>{m.banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
              )}
            </>
          )}
          <button className="button-outline" disabled={act.busy || ((step === "valuation" || step === "limit") && !asKobo(amount)) || (step === "money" && Number(share) > 0 && !bank)}>
            {step === "title" ? "Search the registry (the empire pays the fee)" : "Record it"}
          </button>
        </form>
      ))}
    </details>
  );
}

function AuctionHouse({ m, now, act, requests }: { m: PropertyMarket; now: number; act: Act; requests: PartnerRequest[] }) {
  const [city, setCity] = useState("All");
  const shown = m.auctions.filter((a) => city === "All" || a.property.city === city);
  const live = shown.filter((a) => a.status === "open");
  const coming = shown.filter((a) => a.status === "coming");
  const done = shown.filter((a) => a.status === "sold" || a.status === "unsold");
  return (
    <>
      <Partners requests={requests} act={act} />
      <div className="filter-row" role="group" aria-label="City">
        {["All", ...CITIES].map((c) => <button key={c} className={city === c ? "chip chip-on" : "chip"} aria-pressed={city === c} onClick={() => setCity(c)}>{c}</button>)}
      </div>
      <Panel title="Live now" aside={`${live.length} ${live.length === 1 ? "auction" : "auctions"} · a bid in the last five minutes adds five more`}>
        {live.length === 0 ? <p className="muted">Nothing is up for auction at this moment. The property companies list a dozen lots each week, spread over the days.</p>
          : live.map((a) => <AuctionCard key={a.id} a={a} m={m} now={now} act={act} />)}
      </Panel>
      {coming.length > 0 && (
        <Panel title="Coming up" aside="Each runs for 24 hours">
          {coming.map((a) => <AuctionCard key={a.id} a={a} m={m} now={now} act={act} />)}
        </Panel>
      )}
      {done.length > 0 && (
        <Panel title="Just ended">
          <div className="scroll" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Lot</th><th scope="col">City</th><th scope="col" className="num">Price</th><th scope="col">Result</th></tr></thead>
              <tbody>
                {done.map((a) => (
                  <tr key={a.id}>
                    <th scope="row">{a.property.name}</th><td>{a.property.city}</td>
                    <td className="num mono">{a.price ? formatCompact(a.price) : "—"}</td>
                    <td>{a.status === "sold" ? "✓ Sold" : "✕ Not sold"}{a.you_lead && a.status === "sold" ? " · to you" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  );
}

function Partners({ requests, act }: { requests: PartnerRequest[]; act: Act }) {
  const [most, setMost] = useState<Record<number, string>>({});
  const waiting = requests.filter((r) => r.status === "asked");
  if (waiting.length === 0) return null;
  return (
    <Panel title="Asked to share a bid" aside={`${waiting.length} waiting`}>
      {waiting.map((r) => (
        <div key={r.id} className="report">
          <div className="row small"><span>{r.asked_by} asks {r.for_empire ? "your empire" : "you"} to take {pct(r.partner_bps)} of {r.property}</span></div>
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(most[r.id] ?? ""); if (k) act.run(`/auctions/partners/${r.id}/answer`, { for_empire: r.for_empire, agree: true, most_kobo: k }, "Agreed. Your share of that price is held until the auction ends."); }}>
            <label className="answer">The highest price you will share in (₦)
              <input type="text" inputMode="decimal" value={most[r.id] ?? ""} onChange={(e) => setMost({ ...most, [r.id]: e.target.value })} />
            </label>
            <button className="button-primary" disabled={act.busy || !asKobo(most[r.id] ?? "")}>Agree</button>
            <button type="button" className="button-quiet" disabled={act.busy} onClick={() => act.run(`/auctions/partners/${r.id}/answer`, { for_empire: r.for_empire, agree: false }, "Refused.")}>Refuse</button>
          </form>
        </div>
      ))}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// The map
// ---------------------------------------------------------------------------

function CityMap({ m, chosen, onChoose }: { m: PropertyMarket; chosen: number | null; onChoose: (id: number) => void }) {
  return (
    <div className="city-map" aria-label="The districts of the five cities">
      {CITIES.map((city) => (
        <section key={city} className="city-block" aria-labelledby={`city-${city}`}>
          <h3 id={`city-${city}`} className="lbl">{city}</h3>
          <div className="district-grid">
            {m.districts.filter((d) => d.city === city).map((d) => {
              const before = d.history.length > 1 ? d.history[d.history.length - 2].price_bps : undefined;
              const change = move(d.price_bps, before);
              const dir = change === null ? "flat" : change > 50 ? "up" : change < -50 ? "down" : "flat";
              return (
                <button key={d.id} className={`district district-${dir}${chosen === d.id ? " district-on" : ""}`} aria-pressed={chosen === d.id} onClick={() => onChoose(d.id)}>
                  <span className="district-name">{d.name}</span>
                  <span className="muted small">{d.kind_name}</span>
                  <span className="mono small">{index(d.price_bps)} <Arrow bps={change} /></span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
      <p className="muted small">
        Each district's price index: 100 is where prices stood when the world began. ▲ up and ▼ down on the last quarter.
        Rents follow the city's spending and jobs; prices follow rents, interest rates and what buyers have been paying.
      </p>
    </div>
  );
}

function DistrictPanel({ d }: { d: District }) {
  const [sort, setSort] = useState<"value" | "rent" | "size">("value");
  const props = useMemo(() => [...d.properties].sort((a, b) =>
    sort === "size" ? b.size_m2 - a.size_m2 : Number(BigInt(sort === "value" ? b.value : b.rent_due) - BigInt(sort === "value" ? a.value : a.rent_due))), [d, sort]);
  return (
    <Panel title={`${d.name}, ${d.city}`} aside={d.kind_name}>
      <div className="tiles">
        <NumberTile label="Price index" value={index(d.price_bps)} />
        <NumberTile label="Rent index" value={index(d.rent_bps)} />
        <NumberTile label="Space let" value={pct(d.occupancy_bps)} />
      </div>
      <div className="filter-row" role="group" aria-label="Sort by">
        {(["value", "rent", "size"] as const).map((k) => <button key={k} className={sort === k ? "chip chip-on" : "chip"} aria-pressed={sort === k} onClick={() => setSort(k)}>{k === "value" ? "Value" : k === "rent" ? "Rent" : "Size"}</button>)}
      </div>
      <div className="scroll" tabIndex={0}>
        <table>
          <thead><tr><th scope="col">Property</th><th scope="col" className="num">Size</th><th scope="col" className="num">Value</th><th scope="col" className="num">Rent a quarter</th><th scope="col">Condition</th><th scope="col">Owner</th></tr></thead>
          <tbody>
            {props.map((p) => (
              <tr key={p.id}>
                <th scope="row">{p.name}<div className="muted small">{p.kind_name}{p.status === "collapsed" ? " · ■ fallen down" : ""}</div></th>
                <td className="num mono">{p.size_m2.toLocaleString("en-NG")} m²</td>
                <td className="num mono">{formatCompact(p.value)}</td>
                <td className="num mono">{p.rent_due === "0" ? "—" : formatCompact(p.rent_due)}</td>
                <td>{p.kind === "land" ? <span className="muted small">a plot</span> : <Condition value={p.condition} />}</td>
                <td className="small">{p.owners.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// What the player (or their empire) owns
// ---------------------------------------------------------------------------

function Owned({ h, act, forEmpire, canAct, m }: { h: Holdings; act: Act; forEmpire: boolean; canAct: boolean; m: PropertyMarket }) {
  const [reserve, setReserve] = useState<Record<number, string>>({});
  const [repay, setRepay] = useState<Record<number, string>>({});
  const [lease, setLease] = useState<Record<number, { terms?: LeasebackTerms; quarters: string; error?: string }>>({});
  async function askTerms(id: number) {
    try { setLease({ ...lease, [id]: { terms: await api.leasebackTerms(id), quarters: "8" } }); }
    catch (problem) { setLease({ ...lease, [id]: { quarters: "8", error: problem instanceof Error ? problem.message : "Could not reach the server." } }); }
  }
  return (
    <>
      <div className="tiles">
        <NumberTile label="Property, at today's prices" value={formatCompact(h.value)} />
        <NumberTile label="Owed on it (mortgages, tax)" value={formatCompact(h.owed)} />
        <NumberTile label="Yours, after what is owed" value={formatCompact(h.equity)} />
      </div>
      {h.properties.length === 0 ? (
        <p className="muted">{forEmpire ? "The empire owns no property yet." : "You own no property yet."} Buildings and plots are bought at the Auction House.</p>
      ) : h.properties.map((p: MyLot) => (
        <article key={p.id} className="lot">
          <div className="lot-head">
            <div>
              <h3 className="lot-title">{p.name}</h3>
              <div className="muted small">{p.kind_name} · {p.district}, {p.city} · {p.share_bps < 10000 ? `${pct(p.share_bps)} of it` : "all of it"}</div>
            </div>
            <div className="mono figure-small">{formatCompact(p.value)}</div>
          </div>
          <div className="lot-figures">
            <div><div className="lbl">Rent last quarter</div><div className="mono">{formatCompact(p.last_rent)}</div></div>
            <div><div className="lbl">Tax last quarter</div><div className="mono">{formatCompact(p.last_tax)}</div></div>
            <div><div className="lbl">Tax unpaid</div><div className={`mono${p.tax_owed !== "0" ? " change-down" : ""}`}>{p.tax_owed === "0" ? "None" : `▲ ${formatCompact(p.tax_owed)}`}</div></div>
            <div><div className="lbl">Paid</div><div className="mono">{formatCompact(p.paid)}</div></div>
          </div>
          {p.kind !== "land" && p.status === "standing" && <div className="row small"><span>Condition</span><Condition value={p.condition} /></div>}
          {canAct && <LotExtras p={p} act={act} forEmpire={forEmpire} m={m} />}
          {canAct && (
            <div className="inline-form">
              {p.kind !== "land" && p.status === "standing" && (
                <>
                  <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/${p.id}/upkeep`, { for_empire: forEmpire, on: !p.upkeep }, p.upkeep ? "Upkeep stopped. The building will wear five times as fast." : "Upkeep started.")}>
                    {p.upkeep ? "✓ Upkeep on · stop it" : "○ Upkeep off · start it"}
                  </button>
                  {p.condition < 100 && <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/${p.id}/renovate`, { for_empire: forEmpire }, "Renovated: 25 points of condition.")}>Renovate (5% of its value)</button>}
                </>
              )}
              {p.build_cost && <button className="button-outline" disabled={act.busy} onClick={() => act.run(`/property/${p.id}/build`, { for_empire: forEmpire }, "Built.")}>Build here · {formatCompact(p.build_cost)}</button>}
              <button className="button-quiet" disabled={act.busy} onClick={() => act.run(`/property/${p.id}/title-search`, { for_empire: forEmpire }, (r) => `The lands registry: ${r.words ?? "no answer"}`)}>Search the title</button>
              {p.share_bps === 10000 && (
                <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run(`/property/${p.id}/sell`, { for_empire: forEmpire, reserve_kobo: asKobo(reserve[p.id] ?? "") ?? 0 }, "It is up for auction for 24 hours."); }}>
                  <label className="answer">Lowest price you will take (₦, blank for none)<input type="text" inputMode="decimal" value={reserve[p.id] ?? ""} onChange={(e) => setReserve({ ...reserve, [p.id]: e.target.value })} /></label>
                  <button className="button-outline" disabled={act.busy}>Put it up for auction</button>
                </form>
              )}
              {p.share_bps === 10000 && p.kind !== "land" && p.kind !== "farmland" && p.status === "standing" && !lease[p.id] && (
                <span><button className="button-quiet" disabled={act.busy} onClick={() => askTerms(p.id)}>Sell and lease back…</button> <Term word="Sale and leaseback">{""}</Term></span>
              )}
              {lease[p.id]?.error && <p className="error small">{lease[p.id].error}</p>}
              {lease[p.id]?.terms && (() => { const t = lease[p.id].terms!; return (
                <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run(`/property/${p.id}/leaseback`, { for_empire: forEmpire, quarters: Number(lease[p.id].quarters) }, "Sold and leased back: you keep the use of it and pay rent each quarter."); }}>
                  <span className="small">A property company would pay <span className="mono">{formatCompact(t.price)}</span> (worth {formatCompact(t.worth)}) and charge <span className="mono">{formatCompact(String(t.rent))}</span> a quarter. Two rents missed and the lease is broken.</span>
                  <label className="answer">For<select value={lease[p.id].quarters} onChange={(e) => setLease({ ...lease, [p.id]: { ...lease[p.id], quarters: e.target.value } })}>{[4, 6, 8, 12, 16, 20].map((n) => <option key={n} value={n}>{n} quarters</option>)}</select></label>
                  <button className="button-outline" disabled={act.busy}>Sell and lease it back</button>
                  <button type="button" className="button-quiet" onClick={() => { const next = { ...lease }; delete next[p.id]; setLease(next); }}>Not now</button>
                </form>
              ); })()}
            </div>
          )}
        </article>
      ))}
      <SalesAndDevelopments sales={h.sales ?? []} developments={h.developments ?? []} act={act} forEmpire={forEmpire} m={m} />
      {(h.leases ?? []).length > 0 && (
        <Panel title="Leased back" aside="you keep the use; the rent is paid at each quarter's close">
          {(h.leases ?? []).map((l) => (
            <div key={l.id} className="row small"><span>{l.name} · from {l.landlord} until {l.until}</span><span className="mono">{formatCompact(String(l.rent))} a quarter{l.missed > 0 ? ` · ▲ ${l.missed} rent missed` : ""}</span></div>
          ))}
        </Panel>
      )}
      {h.mortgages.length > 0 && (
        <Panel title="Mortgages" aside={`${pct(m.mortgage_rate_bps)} a year today`}>
          {h.mortgages.map((x) => (
            <div key={x.id} className="report">
              <div className="row small"><span>{x.bank} · {h.properties.find((p) => p.id === x.property_id)?.name ?? "a property sold"}</span><span className={`tag tag-${x.missed ? "missed" : x.status === "shortfall" ? "missed" : "open"}`}>{x.missed ? `▲ ${x.missed} missed` : x.status}</span></div>
              <div className="row small"><span>Borrowed</span><span className="mono">{formatCompact(x.principal)}</span></div>
              <div className="row small"><span>Still owed</span><span className="mono">{formatCompact(x.outstanding)}</span></div>
              {x.missed > 0 && <p className="error small">Two payments missed and the bank sells the property at auction, whatever the price.</p>}
              {canAct && (
                <form className="inline-form" onSubmit={(e) => { e.preventDefault(); const k = asKobo(repay[x.id] ?? ""); if (k) act.run(`/property/mortgages/${x.id}/repay`, { for_empire: forEmpire, amount_kobo: k }, "Repaid."); }}>
                  <label className="answer">Repay early (₦)<input type="text" inputMode="decimal" value={repay[x.id] ?? ""} onChange={(e) => setRepay({ ...repay, [x.id]: e.target.value })} /></label>
                  <button className="button-outline" disabled={act.busy || !asKobo(repay[x.id] ?? "")}>Repay</button>
                </form>
              )}
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

export function PropertyWork({ onLoggedOut, onChanged }: Props) {
  const { data: m, error, loading, reload } = useLoad(api.property, "property", onLoggedOut);
  const partners = useLoad(api.partnerRequests, "partner-requests", onLoggedOut);
  const act = useAct(() => { reload(); partners.reload(); }, onLoggedOut, onChanged);
  const [tab, setTab] = useState<Tab>(() => (window.location.hash.split("/")[2] as Tab) || "auctions");
  const [district, setDistrict] = useState<number | null>(null);
  const now = useServerNow(m?.now);
  // The Auction House is live: read it again every 20 seconds while the page is open.
  useEffect(() => {
    const every = setInterval(reload, 20_000);
    return () => clearInterval(every);
  }, [reload]);
  const choose = (next: Tab) => { setTab(next); window.history.replaceState(null, "", `#/property/${next}`); };
  if (loading && !m) return <Loading what="the property market" />;
  if (error && !m) return <Failed message={error} onRetry={reload} />;
  if (!m) return null;
  if (m.districts.length === 0) {
    return <Panel title="Property"><p className="muted">The property market opens at the next quarter's close.</p></Panel>;
  }
  const tabs: [Tab, string][] = [["auctions", "Auction House"], ["map", "Districts"], ["mine", "My property"], ...(m.empire ? [["empire", "Empire's property"] as [Tab, string]] : []), ["projects", "Projects and funds"]];
  const chosen = m.districts.find((d) => d.id === district) ?? null;
  return (
    <>
      <div className="work-head">
        <div>
          <h1>Property</h1>
          <div className="work-sub">Land and buildings in five cities, the Auction House, and what you own</div>
        </div>
      </div>
      <section className="band band-4" aria-label="The property market today">
        <div className="band-cell">
          <div className="band-label"><Term word="Rental yield">Yield investors ask</Term></div>
          <div className="band-value">{pct(m.yield_bps)}</div>
          <div className="band-note">a year’s rent, against what a building costs</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Mortgage rate</div>
          <div className="band-value">{pct(m.mortgage_rate_bps)}</div>
          <div className="band-note">a year, on what a bank lends you</div>
        </div>
        <div className="band-cell">
          <div className="band-label">Property and land tax</div>
          <div className="band-value">{pct(m.tax_bps)}</div>
          <div className="band-note">a year, paid at each quarter’s close</div>
        </div>
        <div className="band-cell">
          <div className="band-label">What a bank will lend you</div>
          <div className="band-value">{formatCompact(m.mortgage_most)}</div>
          <div className="band-note">at most, for one property, after your mortgage; a salary is needed</div>
        </div>
      </section>
      <Messages act={act} />
      <div className="underline-tabs" role="tablist" aria-label="Property">
        {tabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : undefined} onClick={() => choose(key)}>{label}</button>)}
      </div>
      {tab === "auctions" && <AuctionHouse m={m} now={now} act={act} requests={partners.data?.requests ?? []} />}
      {tab === "map" && (
        <>
          <Panel title="The map"><CityMap m={m} chosen={district} onChoose={setDistrict} /></Panel>
          {chosen ? <DistrictPanel d={chosen} /> : <p className="muted">Choose a district to see every building and plot in it.</p>}
        </>
      )}
      {tab === "mine" && (
        <Panel title="My property">
          <Owned h={m.mine} act={act} forEmpire={false} canAct m={m} />
          <p className="muted small">{m.mortgage_limit_note} Rent is paid at each quarter's close; tax and upkeep are taken then too. Unpaid tax grows by a twentieth each quarter, and the Government sells a property whose unpaid tax reaches a tenth of its value.</p>
        </Panel>
      )}
      {tab === "projects" && <ProjectsTab m={m} act={act} onLoggedOut={onLoggedOut} />}
      {tab === "empire" && m.empire && (
        <>
          <Panel title={`${m.empire.name}: property`} aside={m.empire.head ? "You decide, as head" : "The head decides"}>
            <Owned h={m.empire.property} act={act} forEmpire canAct={m.empire.head} m={m} />
          </Panel>
          <Panel title="Bidding for the empire" aside="Four desks check a lot before the head may bid">
            {m.empire.auctions.filter((a) => a.status === "open" || a.status === "coming").length === 0
              ? <p className="muted">Nothing is up for auction at this moment.</p>
              : m.empire.auctions.filter((a) => a.status === "open" || a.status === "coming").map((a) => (
                <AuctionCard key={a.id} a={a} m={m} now={now} act={act} empire playerBuild={m.empire?.build} />
              ))}
          </Panel>
        </>
      )}
    </>
  );
}

export function PropertyRail({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data: m } = useLoad(api.property, "property", onLoggedOut);
  const partners = useLoad(api.partnerRequests, "partner-requests", onLoggedOut);
  if (!m) return null;
  const leading = m.auctions.filter((a) => a.status === "open" && a.you_lead);
  const outbid = m.auctions.filter((a) => a.status === "open" && a.your_status === "outbid");
  const asked = (partners.data?.requests ?? []).filter((r) => r.status === "asked");
  const late = m.mine.mortgages.filter((x) => x.missed > 0);
  const items = [
    ...outbid.map((a) => ({ tag: "▼ Outbid", title: a.property.name })),
    ...asked.map((r) => ({ tag: "Partner", title: `${r.asked_by}: ${r.property}` })),
    ...late.map((x) => ({ tag: "■ Mortgage", title: `${x.missed} payment missed at ${x.bank}` })),
    ...leading.map((a) => ({ tag: "▲ Leading", title: a.property.name })),
  ];
  return (
    <>
      <Panel title="Needs you now">
        {items.length === 0 ? <p className="muted small">Nothing at the Auction House is waiting on you.</p> : (
          <div className="wait-list">
            {items.slice(0, 6).map((it, i) => (
              <a key={i} className="wait-item" href="#/property/auctions">
                <span className="wait-tag">{it.tag}</span><span className="wait-title">{it.title}</span>
              </a>
            ))}
          </div>
        )}
      </Panel>
      <Panel title="My property">
        <div className="row"><span>Worth</span><span className="mono">{formatCompact(m.mine.value)}</span></div>
        <div className="row"><span>Owed on it</span><span className="mono">{formatCompact(m.mine.owed)}</span></div>
        <div className="row"><span>Yours</span><span className="mono">{formatCompact(m.mine.equity)}</span></div>
      </Panel>
      <Panel title="Cities" aside="price index, start = 100">
        {CITIES.map((city) => {
          const ds = m.districts.filter((d) => d.city === city);
          if (ds.length === 0) return null;
          const avg = Math.round(ds.reduce((s, d) => s + d.price_bps, 0) / ds.length);
          const before = ds.every((d) => d.history.length > 1) ? Math.round(ds.reduce((s, d) => s + d.history[d.history.length - 2].price_bps, 0) / ds.length) : undefined;
          return <div key={city} className="row"><span>{city}</span><span className="mono">{index(avg)} <Arrow bps={move(avg, before)} /></span></div>;
        })}
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------------------
// The empire's headquarters (a tab of the Empire section)
// ---------------------------------------------------------------------------

export function HeadquartersTab({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged?: () => void }) {
  const { data, error, loading, reload } = useLoad(api.headquarters, "headquarters", onLoggedOut);
  const act = useAct(reload, onLoggedOut, onChanged);
  const [building, setBuilding] = useState("");
  const [levels, setLevels] = useState("1");
  if (loading && !data) return <Loading what="the headquarters" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const hq = data.headquarters;
  const isRisk = data.build === "risk_manager";
  const standing = data.owned.filter((p) => p.status === "standing" && p.kind !== "land" && p.id !== hq?.property_id);
  return (
    <>
      <Messages act={act} />
      {hq ? <HqPanel hq={hq} data={data} act={act} isRisk={isRisk} levels={levels} setLevels={setLevels} /> : (
        <Panel title="Headquarters">
          <p>The empire has no headquarters yet. A headquarters is a building the empire owns outright. It teaches the members more
            from the empire's work, adds seats as it rises, and brings its city's advantages.</p>
        </Panel>
      )}
      {data.head && (
        <Panel title={hq ? "Move the headquarters" : "Set up the headquarters"} aside={hq ? "A move costs a tenth of what has been spent on it. Its level goes with it" : undefined}>
          {standing.length === 0 ? <p className="muted">The empire owns no building it could use. Buy one at the <a href="#/property/empire">Auction House</a>.</p> : (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (building) act.run("/empire/headquarters", { property_id: Number(building) }, hq ? "The headquarters has moved." : "The headquarters is set up at Level 1."); }}>
              <label>Building<select value={building} onChange={(e) => setBuilding(e.target.value)}><option value="">Choose…</option>
                {standing.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.city}</option>)}</select></label>
              <button className="button-primary" disabled={act.busy || !building}>{hq ? "Move here" : "Make it the headquarters"}</button>
            </form>
          )}
        </Panel>
      )}
      <Panel title="What each city brings">
        {data.cities.map((c) => (
          <div key={c.city} className="row small">
            <span><strong>{c.city}</strong> · {c.words}</span>
            <span className="muted">building costs {pct(c.cost_bps)} of the usual</span>
          </div>
        ))}
      </Panel>
    </>
  );
}

function HqPanel({ hq, data, act, isRisk, levels, setLevels }: {
  hq: NonNullable<Headquarters["headquarters"]>; data: Headquarters; act: Act; isRisk: boolean; levels: string; setLevels: (v: string) => void;
}) {
  const conditionWords = hq.condition >= 50 ? "Sound" : hq.condition >= 30 ? "▲ First warning" : hq.condition >= 15 ? "▲▲ Second warning" : "■ Final warning: it may fall";
  return (
    <Panel title={`Headquarters · ${hq.building}`} aside={`${hq.district}, ${hq.city}`}>
      {hq.homeless && <p className="error" role="alert">■ The building was sold at a forced sale. The headquarters' benefits have stopped and its extra seats are frozen until the head moves it to a building the empire owns.</p>}
      {hq.collapsed && !hq.homeless && <p className="error" role="alert">■ The headquarters has fallen down. Its benefits have stopped and its extra seats are frozen until it is rebuilt. Members keep their seats.</p>}
      <div className="tiles">
        <NumberTile label="Level" value={`${hq.level} of 120`} note={hq.next_seat_at ? `A new seat at Level ${hq.next_seat_at}` : "The highest level"} />
        <NumberTile label="Members learn more" value={`+${pct(hq.bonus_bps)}`} note={`+${pct(hq.city_bonus_bps)} on work for a client in its city's industries`} />
        <NumberTile label="Seats it adds" value={String(hq.extra_seats)} note={hq.seats.some((s) => s.frozen) ? "✕ frozen" : "beyond the two for each build"} />
        <NumberTile label="Spent on it" value={formatCompact(hq.spent)} />
      </div>
      <div className="row"><span>Condition</span><span className="mono">{hq.condition}/100 <span className="muted small">{conditionWords}</span></span></div>
      <div className="meter" aria-hidden="true"><div className={`meter-fill${hq.condition < 50 ? " meter-loss" : ""}`} style={{ width: `${hq.condition}%` }} /></div>
      <p className="small">{hq.city}: {hq.city_words}.{hq.lobbying ? ` Its standing in Abuja counts ${hq.lobbying} towards lobbying when that opens.` : ""}</p>
      <div className="report">
        <div className="lbl">Upkeep and insurance (the Risk Manager's to ask, the head's to approve)</div>
        <div className="row small"><span>Upkeep a quarter</span><span className="mono">{formatCompact(hq.upkeep)}</span></div>
        <div className="row small"><span>Asked for by the Risk Manager</span><span>{hq.upkeep_asked ? "✓ Yes" : "○ Not yet"}</span></div>
        <div className="row small"><span>Approved by the head</span><span>{hq.upkeep_approved ? "✓ Yes" : "✕ No: it wears 8 points a quarter"}</span></div>
        <div className="inline-form">
          {(isRisk || data.head) && !hq.upkeep_asked && <button className="button-outline" disabled={act.busy} onClick={() => act.run("/empire/headquarters/upkeep/ask", {}, "Asked. The head decides.")}>Ask for the upkeep</button>}
          {data.head && <button className={hq.upkeep_approved ? "button-quiet" : "button-primary"} disabled={act.busy} onClick={() => act.run("/empire/headquarters/upkeep/approve", { approve: !hq.upkeep_approved }, hq.upkeep_approved ? "Upkeep stopped." : "Upkeep approved: it is paid at each close.")}>{hq.upkeep_approved ? "Stop the upkeep" : "Approve the upkeep"}</button>}
        </div>
        <p className="muted small">
          Warnings come at condition 50, 30 and 15. Below 15 it may fall down. If it falls after a warning was ignored, the head and the
          Risk Manager lose reputation. Insurance for the building is bought with the empire's other cover, on the <a href="#/empire/risk">Risk</a> tab: it pays for the building lost.
        </p>
      </div>
      {data.head && hq.standing && hq.next_cost && (
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); act.run("/empire/headquarters/raise", { levels: Number(levels) }, "Raised."); }}>
          <label>Raise by<select value={levels} onChange={(e) => setLevels(e.target.value)}>{[1, 2, 5, 10].map((n) => <option key={n} value={n}>{n} {n === 1 ? "level" : "levels"}</option>)}</select></label>
          <button className="button-primary" disabled={act.busy}>Raise it</button>
          <span className="muted small">The next level costs {formatNaira(hq.next_cost)}. Each level costs more than the last, and does a little less.</span>
        </form>
      )}
      {data.head && hq.collapsed && !hq.homeless && (
        <button className="button-primary" disabled={act.busy} onClick={() => act.run("/empire/headquarters/rebuild", {}, "Rebuilt.")}>Rebuild it · {formatCompact(hq.rebuild_cost)}</button>
      )}
    </Panel>
  );
}

export type { PropertyLot };
