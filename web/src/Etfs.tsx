// Index funds and ETFs (the talent and funds stage, Part 3), a tab inside Markets. The game's indexes and managers' own;
// ETFs whose units trade all day like a share, with their value through the day beside their price; approved dealers making
// and unmaking units; the 2x, inverse and commodity ETFs behind a level and a warning. The website only asks; the server decides.

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type EtfAlert, type EtfSheet, type EtfsPage, type EtfSummary, type IndexPage } from "./api";
import { AreaChart } from "./Charts";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { NumberTile } from "./Parts";
import { Change, Failed, Loading, Panel } from "./Shell";
import { LineChart } from "./TrendChart";

const units = (n: number) => n.toLocaleString("en-NG");
const level = (hundredths: string | number) => (Number(hundredths) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const naira = (kobo: string | number) => `₦${(Number(kobo) / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const day = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-NG", { day: "numeric", month: "short", timeZone: "UTC" });
const KIND_TAG: Record<string, string> = { leverage: "2x daily", inverse: "inverse daily", commodity: "commodity" };

type Run = (path: string, body?: unknown) => Promise<boolean>;

function useRun(onChanged: () => void, reload: () => void, onLoggedOut: () => void): [Run, boolean, string | null, string | null] {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run: Run = async (path, body) => {
    setBusy(true); setError(null); setDone(null);
    try { await api.etfAct(path, body); setDone("Done."); onChanged(); reload(); return true; }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) { onLoggedOut(); return false; }
      setError(problem instanceof ApiError ? problem.message : "Could not reach the server. Please try again.");
      return false;
    }
    finally { setBusy(false); }
  };
  return [run, busy, error, done];
}

function Gap({ bps }: { bps: number }) {
  const off = Math.abs(bps) >= 50;
  return <span className={`mono${off ? (bps > 0 ? " change-up" : " change-down") : ""}`}>{bps > 0 ? "+" : ""}{(bps / 100).toFixed(2)}%</span>;
}

/** The Markets section's "Indexes & ETFs" tab. */
export function EtfsWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const page = useLoad(api.etfs, "etfs", onLoggedOut);
  const [open, setOpen] = useState<{ kind: "etf" | "index"; code: string } | null>(null);
  if (page.error) return <Failed message={page.error} onRetry={page.reload} />;
  if (!page.data) return <Loading what="the indexes and ETFs" />;
  const data = page.data;
  if (open?.kind === "etf") return <EtfView code={open.code} onBack={() => { setOpen(null); page.reload(); }} onLoggedOut={onLoggedOut} onChanged={onChanged} />;
  if (open?.kind === "index") return <IndexView code={open.code} onBack={() => setOpen(null)} onLoggedOut={onLoggedOut} />;
  const plain = data.etfs.filter((e) => !e.special);
  const special = data.etfs.filter((e) => e.special);
  return (
    <>
      <Panel title="Indexes and ETFs" aside={`passive money: ${formatPercent(data.passive.share_bps)} of the market (heading for ${formatPercent(data.passive.target_bps, 0)})`}>
        <p className="small">
          An <span className="strong">index</span> follows a group of companies (or bonds) by published rules. An <span className="strong">ETF</span> copies an
          index and its units trade on the exchange all day, like a share; its <span className="strong">value</span> (what its holdings are worth, per
          unit) is shown beside its <span className="strong">price</span>. When the two drift apart, approved dealers can make or unmake units to close
          the gap, and earn the difference. Each quarter's changes to an index are announced three closing bells ahead.
        </p>
        {data.mine.length > 0 && <>
          <div className="why-title">YOUR ETFS</div>
          {data.mine.map((m) => (
            <div key={m.code} className="row">
              <span><button className="link-button strong" onClick={() => setOpen({ kind: "etf", code: m.code })}>{m.code}</button> <span className="muted small">{m.name} · {units(m.held)} units</span></span>
              <span className="mono">{formatNaira(m.value)} <Change bps={m.day_bps} /></span>
            </div>
          ))}
        </>}
      </Panel>
      <Panel title="Indexes" aside="levels at the last trade; 1,000 at the start">
        <div className="table-scroll">
          <table className="mini-table" tabIndex={0}>
            <caption className="sr-only">Every index</caption>
            <thead><tr><th scope="col">Index</th><th scope="col" className="num">Level</th><th scope="col" className="num">Today</th>
              <th scope="col" className="num">Quarter</th><th scope="col" className="num">Year</th><th scope="col" className="num">Members</th></tr></thead>
            <tbody>
              {data.indexes.map((i) => (
                <tr key={i.code}>
                  <td><button className="link-button strong" onClick={() => setOpen({ kind: "index", code: i.code })}>{i.name}</button>
                    <div className="muted small">{i.code}{i.custom ? ` · published by ${i.owner}` : ""}</div></td>
                  <td className="num mono">{level(i.level)}</td><td className="num"><Change bps={i.day_bps} /></td>
                  <td className="num"><Change bps={i.quarter_bps} /></td><td className="num"><Change bps={i.year_bps} /></td>
                  <td className="num mono">{i.members}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <EtfTable title="ETFs" aside="price and value per unit; the gap between them" rows={plain} onOpen={(code) => setOpen({ kind: "etf", code })} />
      {special.length > 0 && (
        <EtfTable title="2x, inverse and commodity ETFs" aside={`for players of Level ${data.special_level}+ who have read the warning`} rows={special}
                  onOpen={(code) => setOpen({ kind: "etf", code })} />
      )}
      {data.index_funds.length > 0 && (
        <Panel title="Index funds" aside="bought and sold at the next closing bell, in the Funds tab">
          {data.index_funds.map((f) => (
            <div key={f.id} className="row small">
              <span><a href="#/market/funds" className="strong">{f.name}</a> <span className="muted">· copies {f.index_code} · {f.manager}</span></span>
              <span className="mono">{formatCompact(f.worth)} · fee {formatPercent(f.fee_bps, 2)} · tracking error {f.tracking.error_bps === null ? "n/a" : formatPercent(f.tracking.error_bps, 2)}</span>
            </div>
          ))}
        </Panel>
      )}
      <DealerPanel data={data} onLoggedOut={onLoggedOut} onChanged={onChanged} reload={page.reload} />
      {data.managing && <ManagingPanel etf={data.managing} onLoggedOut={onLoggedOut} onChanged={onChanged} reload={page.reload} />}
      {data.can_launch && !data.managing && <LaunchEtf data={data} onLoggedOut={onLoggedOut} onChanged={onChanged} reload={page.reload} />}
      {data.can_launch && <CustomIndex data={data} onLoggedOut={onLoggedOut} onChanged={onChanged} reload={page.reload} />}
    </>
  );
}

function EtfTable({ title, aside, rows, onOpen }: { title: string; aside: string; rows: EtfSummary[]; onOpen: (code: string) => void }) {
  return (
    <Panel title={title} aside={aside}>
      <div className="table-scroll">
        <table className="mini-table" tabIndex={0}>
          <caption className="sr-only">{title}</caption>
          <thead><tr><th scope="col">ETF</th><th scope="col" className="num">Price</th><th scope="col" className="num">Value</th>
            <th scope="col" className="num">Gap</th><th scope="col" className="num">Today</th><th scope="col" className="num">Year</th>
            <th scope="col" className="num">Size</th><th scope="col" className="num">Fee</th><th scope="col" className="num">Tracking error</th></tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.code}>
                <td><button className="link-button strong" onClick={() => onOpen(e.code)}>{e.code}</button>{KIND_TAG[e.kind] && <span className="tag tag-warn">{KIND_TAG[e.kind]}</span>}
                  <div className="muted small">{e.name}{e.status === "closing" ? " · closing" : ""}</div></td>
                <td className="num mono">{naira(e.price)}</td><td className="num mono">{naira(e.nav)}</td>
                <td className="num"><Gap bps={e.premium_bps} /></td><td className="num"><Change bps={e.day_bps} /></td><td className="num"><Change bps={e.year_bps} /></td>
                <td className="num mono">{formatCompact(e.size)}</td><td className="num mono">{formatPercent(e.fee_bps, 2)}</td>
                <td className="num mono">{e.tracking.error_bps === null ? "n/a" : formatPercent(e.tracking.error_bps, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function IndexView({ code, onBack, onLoggedOut }: { code: string; onBack: () => void; onLoggedOut: () => void }) {
  const page = useLoad(() => api.indexPage(code), `index:${code}`, onLoggedOut);
  if (page.error) return <Failed message={page.error} onRetry={page.reload} />;
  if (!page.data) return <Loading what="the index" />;
  const i: IndexPage = page.data;
  return (
    <>
      <button className="button-quiet" onClick={onBack}>← Indexes and ETFs</button>
      <Panel title={i.name} aside={i.custom ? `published by ${i.owner}` : "the index provider"}>
        <div className="tiles">
          <NumberTile label="Level" value={level(i.level)} change={i.day_bps} />
          <NumberTile label="Over a quarter" value={<Change bps={i.quarter_bps} />} />
          <NumberTile label="Over a year" value={<Change bps={i.year_bps} />} />
          <NumberTile label="Members" value={i.members} />
        </div>
        <AreaChart label={`${i.name}, at each closing bell`} format={(v) => level(v)} points={i.history.map((h) => ({ label: day(h.session_date), value: Number(h.level) }))} />
        <div className="why-title">THE RULES</div>
        <p className="small">{i.rules}</p>
      </Panel>
      <Panel title="Who is in it" aside="share of the index at today's prices">
        {i.weights.map((w) => <div key={w.asset} className="row small"><span>{w.name} <span className="ticker">{w.ticker}</span></span><span className="mono">{formatPercent(w.weight_bps)}</span></div>)}
      </Panel>
      <Panel title="Changes" aside="announced as a quarter closes, made at the third closing bell after">
        {i.changes.length === 0 ? <p className="muted small">No changes yet.</p> : i.changes.map((c, k) => (
          <div key={k} className="small fact-row">
            <span className="strong">{c.label} review · {c.status === "made" ? "made" : "announced"} for {day(c.effective_day)}</span>
            <span>{c.adds.length ? `In: ${c.adds.map((a) => a.name).join(", ")}. ` : ""}{c.drops.length ? `Out: ${c.drops.map((d) => d.name).join(", ")}.` : ""}{!c.adds.length && !c.drops.length ? "Same members, weights reset." : ""}</span>
          </div>
        ))}
      </Panel>
    </>
  );
}

function EtfView({ code, onBack, onLoggedOut, onChanged }: { code: string; onBack: () => void; onLoggedOut: () => void; onChanged: () => void }) {
  const sheet = useLoad(() => api.etf(code), `etf:${code}`, onLoggedOut);
  const [run, busy, error, done] = useRun(onChanged, sheet.reload, onLoggedOut);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("1000");
  const [price, setPrice] = useState("");
  const [forEmpire, setForEmpire] = useState(false);
  if (sheet.error) return <Failed message={sheet.error} onRetry={sheet.reload} />;
  if (!sheet.data) return <Loading what="the ETF" />;
  const e: EtfSheet = sheet.data;
  const suggested = e.quote ? (side === "buy" ? e.quote.ask : e.quote.bid) : e.price;
  const priceKobo = price.trim() === "" ? Number(suggested) : Math.round(Number(price) * 100);
  return (
    <>
      <button className="button-quiet" onClick={onBack}>← Indexes and ETFs</button>
      <Panel title={`${e.code} · ${e.name}`} aside={e.computer ? "Broad Street Asset Management" : `managed by ${e.manager}`}>
        <p className="small">{e.kind_words}: <span className="strong">{e.tracks}</span>{e.method === "sample" ? ", by holding its largest members" : ""}.</p>
        {e.words && <p className="small muted">“{e.words}”</p>}
        {e.warning && <div className="definition shadow" role="note"><div className="why-title">READ THIS FIRST</div><p className="small">{e.warning}</p></div>}
        <div className="tiles">
          <NumberTile label="Price" value={naira(e.price)} change={e.day_bps} note="the last trade (or the last bell)" />
          <NumberTile label="Value now (iNAV)" value={naira(e.nav)} note="what its holdings are worth, per unit" />
          <NumberTile label="Gap" value={<Gap bps={e.premium_bps} />} note="price against value" />
          <NumberTile label="Size" value={formatCompact(e.size)} note={`${units(e.units)} units`} />
          <NumberTile label="Fee" value={`${formatPercent(e.fee_bps, 2)} a year`} note={`tracking error ${e.tracking.error_bps === null ? "not known yet" : formatPercent(e.tracking.error_bps, 2)}`} />
        </div>
        {e.history.length >= 2 && (
          <LineChart names={["Closing price", "Value"]} format={(v) => `₦${v.toFixed(2)}`}
                     data={e.history.map((h) => ({ label: day(h.day), first: Number(h.close) / 100, second: Number(h.nav) / 100 }))} />
        )}
      </Panel>
      <Panel title="Buy and sell" aside={`today between ${naira(e.band.low)} and ${naira(e.band.high)}`}>
        {e.quote && <p className="small">The market makers buy at <span className="mono strong">{naira(e.quote.bid)}</span> and sell at <span className="mono strong">{naira(e.quote.ask)}</span>, up to {units(e.quote.depth)} units. Each side pays 0.05% to the exchange.</p>}
        <div className="row small"><span>You hold {units(e.mine.units)} units</span><span className="mono">{formatNaira(e.mine.value)}</span></div>
        {e.status === "open" && (
          <form className="trade-grid" onSubmit={(ev) => { ev.preventDefault(); run(`/etfs/${e.code}/orders`, { side, quantity: Math.floor(Number(qty)), limit_price_kobo: priceKobo, for_empire: forEmpire }); }}>
            <div className="step-actions" role="group" aria-label="Buy or sell">
              <button type="button" className={side === "buy" ? "button-outline chip-on" : "button-quiet"} aria-pressed={side === "buy"} onClick={() => { setSide("buy"); setPrice(""); }}>Buy</button>
              <button type="button" className={side === "sell" ? "button-outline chip-on" : "button-quiet"} aria-pressed={side === "sell"} onClick={() => { setSide("sell"); setPrice(""); }}>Sell</button>
            </div>
            <label className="answer"><span className="field-label">Units</span><span className="answer-box"><input type="number" min={1} value={qty} onChange={(ev) => setQty(ev.target.value)} /></span></label>
            <label className="answer"><span className="field-label">Price for each unit, in naira</span><span className="answer-box"><input type="number" step="0.01" placeholder={(Number(suggested) / 100).toFixed(2)} value={price} onChange={(ev) => setPrice(ev.target.value)} /></span></label>
            {e.empire?.head && <label className="small"><input type="checkbox" checked={forEmpire} onChange={(ev) => setForEmpire(ev.target.checked)} /> for my empire</label>}
            <button className="button-outline" disabled={busy || !(Number(qty) > 0)}>{side === "buy" ? "Place the buy order" : "Place the sell order"}</button>
          </form>
        )}
        {e.warning && e.special && e.kind !== "commodity" && <button className="button-quiet" disabled={busy} onClick={() => run("/etfs/warning")}>I have read the warning</button>}
        <button className="button-quiet" disabled={busy} onClick={() => run(`/etfs/${e.code}/follow`, { on: !e.following })}>{e.following ? "✓ Following: stop" : "Follow this ETF (its news pops up)"}</button>
        {error && <p className="error" role="alert">{error}</p>}
        {done && <p className="small tag-good" role="status">{done}</p>}
        {e.orders.filter((o) => o.status === "open").map((o) => (
          <div key={o.id} className="row small"><span>{o.side === "buy" ? "Buying" : "Selling"} {units(o.remaining)} at {naira(o.limit_price)} · waiting until the bell</span>
            <button className="button-quiet" disabled={busy} onClick={() => run(`/etfs/orders/${o.id}/cancel`)}>Cancel</button></div>
        ))}
        {(e.book.buy.length > 0 || e.book.sell.length > 0) && <>
          <div className="why-title">OTHER ORDERS WAITING</div>
          <div className="row small"><span>Buyers: {e.book.buy.map((b) => `${units(b.units)} at ${naira(b.limit_price)}`).join(" · ") || "none"}</span></div>
          <div className="row small"><span>Sellers: {e.book.sell.map((b) => `${units(b.units)} at ${naira(b.limit_price)}`).join(" · ") || "none"}</span></div>
        </>}
      </Panel>
      {e.basket && (
        <Panel title="Its basket" aside={`what ${units(e.creation_units)} new units cost, published daily`}>
          {e.basket.lines.slice(0, 15).map((x) => <div key={x.asset} className="row small"><span>{x.ticker}</span><span className="mono">{units(x.units)} · {formatPercent(x.weight_bps)}</span></div>)}
          <div className="row small"><span>and cash</span><span className="mono">{formatNaira(e.basket.cash)}</span></div>
        </Panel>
      )}
      <Panel title="How closely it copies" aside="each quarter: its return, what it tracks, the gap and its swing">
        {e.quarters.length === 0 ? <p className="muted small">Not yet a full quarter.</p> : (
          <div className="table-scroll">
            <table className="mini-table" tabIndex={0}>
              <caption className="sr-only">Tracking, quarter by quarter</caption>
              <thead><tr><th scope="col">Quarter</th><th scope="col" className="num">It returned</th><th scope="col" className="num">What it tracks</th>
                <th scope="col" className="num">Gap</th><th scope="col" className="num">Tracking error</th></tr></thead>
              <tbody>{e.quarters.map((q) => (
                <tr key={q.period}><td>{q.label}</td><td className="num"><Change bps={q.return_bps} /></td><td className="num"><Change bps={q.tracked_bps} /></td>
                  <td className="num mono">{q.difference_bps === null ? "n/a" : formatPercent(q.difference_bps, 2)}</td>
                  <td className="num mono">{q.error_bps === null ? "n/a" : formatPercent(q.error_bps, 2)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

function DealerPanel({ data, onLoggedOut, onChanged, reload }: { data: EtfsPage; onLoggedOut: () => void; onChanged: () => void; reload: () => void }) {
  const [run, busy, error, done] = useRun(onChanged, reload, onLoggedOut);
  const [code, setCode] = useState(data.etfs[0]?.code ?? "");
  const [blocks, setBlocks] = useState("1");
  const [how, setHow] = useState<"basket" | "cash">("cash");
  if (!data.dealer.head) return null;
  const n = Math.max(Math.floor(Number(blocks) || 0), 0) * data.launch.creation_units;
  return (
    <Panel title="Your empire as a dealer" aside={data.dealer.approved ? "✓ approved" : "not approved"}>
      {!data.dealer.approved ? (
        <>
          <p className="small">An approved dealer makes new ETF units (handing the fund its basket of shares, or cash) and unmakes them. When an ETF's price runs above its value, a dealer makes units and sells them; when it falls below, a dealer buys units and unmakes them. An empire worth {formatNaira(data.dealer.least_worth)} or more, with a head whose record is clean, is approved.</p>
          <button className="button-outline" disabled={busy} onClick={() => run("/etfs/dealer")}>Ask to be approved</button>
        </>
      ) : (
        <form className="stack-form" onSubmit={(ev) => ev.preventDefault()}>
          <label className="answer"><span className="field-label">ETF</span>
            <select value={code} onChange={(ev) => setCode(ev.target.value)}>{data.etfs.map((e) => <option key={e.code} value={e.code}>{e.code} · gap {(e.premium_bps / 100).toFixed(2)}%</option>)}</select></label>
          <label className="answer"><span className="field-label">Blocks of {units(data.launch.creation_units)} units</span><span className="answer-box"><input type="number" min={1} value={blocks} onChange={(ev) => setBlocks(ev.target.value)} /></span></label>
          <label className="answer"><span className="field-label">Against</span>
            <select value={how} onChange={(ev) => setHow(ev.target.value as "basket" | "cash")}><option value="cash">Cash (0.25%)</option><option value="basket">A basket of its shares (0.05%)</option></select></label>
          <div className="step-actions">
            <button className="button-outline" disabled={busy || n <= 0} onClick={() => run(`/etfs/${code}/create`, { units: n, how })}>Make {units(n)} units</button>
            <button className="button-outline" disabled={busy || n <= 0} onClick={() => run(`/etfs/${code}/redeem`, { units: n, how })}>Unmake {units(n)} units</button>
          </div>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {done && <p className="small tag-good" role="status">{done}</p>}
    </Panel>
  );
}

function LaunchEtf({ data, onLoggedOut, onChanged, reload }: { data: EtfsPage; onLoggedOut: () => void; onChanged: () => void; reload: () => void }) {
  const [run, busy, error] = useRun(onChanged, reload, onLoggedOut);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const choosable = data.indexes.filter((i) => !i.custom || data.my_indexes.some((m) => m.code === i.code));
  const [indexCode, setIndexCode] = useState(choosable[0]?.code ?? "");
  const [method, setMethod] = useState("full");
  const [fee, setFee] = useState("25");
  const [seed, setSeed] = useState(String(Number(BigInt(data.launch.seed) / 100n)));
  const bonds = choosable.find((i) => i.code === indexCode)?.kind === "bonds";
  return (
    <Panel title="Launch an ETF" aside={`registration ${formatNaira(data.launch.registration)}`}>
      <form className="stack-form" onSubmit={(ev) => {
        ev.preventDefault();
        run("/etfs/launch", { code: code.toUpperCase(), name, index_code: indexCode, method: bonds ? "full" : method, fee_bps: Number(fee), seed_naira: Number(seed) });
      }}>
        <p className="small muted">Your own money (at least {formatNaira(data.launch.seed)}) makes the first units at ₦100. The game copies the index for the fund; you set the fee (at most {formatPercent(data.launch.fee_most_bps, 0)}) and earn it every day. The cheapest, closest-copying ETFs draw the households' money. To launch an index fund instead, use the Funds tab.</p>
        <label className="answer"><span className="field-label">Code (3 to 5 letters)</span><span className="answer-box"><input type="text" maxLength={5} value={code} onChange={(ev) => setCode(ev.target.value)} /></span></label>
        <label className="answer"><span className="field-label">Name</span><span className="answer-box"><input type="text" maxLength={60} value={name} onChange={(ev) => setName(ev.target.value)} /></span></label>
        <label className="answer"><span className="field-label">The index it copies</span>
          <select value={indexCode} onChange={(ev) => setIndexCode(ev.target.value)}>{choosable.map((i) => <option key={i.code} value={i.code}>{i.name}</option>)}</select></label>
        {!bonds && <label className="answer"><span className="field-label">How it copies</span>
          <select value={method} onChange={(ev) => setMethod(ev.target.value)}><option value="full">Every member, in proportion</option><option value="sample">Only the largest members, up to 80% of the index</option></select></label>}
        <label className="answer"><span className="field-label">Yearly fee</span>
          <select value={fee} onChange={(ev) => setFee(ev.target.value)}>{[0, 5, 10, 15, 20, 25, 35, 50, 75, 100].map((b) => <option key={b} value={b}>{formatPercent(b, 2)}</option>)}</select></label>
        <label className="answer"><span className="field-label">Your own money (₦)</span><span className="answer-box"><input type="number" value={seed} onChange={(ev) => setSeed(ev.target.value)} /></span></label>
        <button className="button-outline" disabled={busy || name.trim().length < 3 || code.trim().length < 3}>Launch the ETF</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </Panel>
  );
}

function ManagingPanel({ etf, onLoggedOut, onChanged, reload }: { etf: NonNullable<EtfsPage["managing"]>; onLoggedOut: () => void; onChanged: () => void; reload: () => void }) {
  const [run, busy, error, done] = useRun(onChanged, reload, onLoggedOut);
  return (
    <Panel title={`The ETF you run: ${etf.code}`} aside={etf.status === "closing" ? "closing at the next bell" : undefined}>
      <div className="tiles">
        <NumberTile label="Size" value={formatCompact(etf.size)} note={`${units(etf.units)} units`} />
        <NumberTile label="Gap" value={<Gap bps={etf.premium_bps} />} />
        <NumberTile label="Tracking error" value={etf.tracking.error_bps === null ? "n/a" : formatPercent(etf.tracking.error_bps, 2)} />
        <NumberTile label="Fees earned this quarter" value={formatNaira(String(etf.fees_this_quarter))} />
      </div>
      <div className="step-actions">
        {etf.fee_bps > 0 && <button className="button-quiet" disabled={busy} onClick={() => run("/etfs/manage/fee", { fee_bps: Math.max(etf.fee_bps - 5, 0) })}>Lower the fee by 0.05%</button>}
        {etf.status === "open" && <button className="button-quiet" disabled={busy} onClick={() => run("/etfs/manage/close")}>Close it at the next bell</button>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {done && <p className="small tag-good" role="status">{done}</p>}
    </Panel>
  );
}

function CustomIndex({ data, onLoggedOut, onChanged, reload }: { data: EtfsPage; onLoggedOut: () => void; onChanged: () => void; reload: () => void }) {
  const [run, busy, error, done] = useRun(onChanged, reload, onLoggedOut);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [tickers, setTickers] = useState("");
  const [weighting, setWeighting] = useState("value");
  const list = tickers.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
  return (
    <Panel title="Publish an index of your own" aside={`${data.my_indexes.length} of 3 published`}>
      <form className="stack-form" onSubmit={(ev) => { ev.preventDefault(); run("/indexes", { code: code.toUpperCase(), name, tickers: list, weighting }); }}>
        <p className="small muted">5 to 30 listed companies, counted by value (none above 15%) or equally. It starts at 1,000; changes are announced three bells ahead. Only you can launch a fund that copies it.</p>
        <label className="answer"><span className="field-label">Code (3 to 8 letters or numbers)</span><span className="answer-box"><input type="text" maxLength={8} value={code} onChange={(ev) => setCode(ev.target.value)} /></span></label>
        <label className="answer"><span className="field-label">Name</span><span className="answer-box"><input type="text" maxLength={60} value={name} onChange={(ev) => setName(ev.target.value)} /></span></label>
        <label className="answer"><span className="field-label">Companies' codes, separated by spaces</span><span className="answer-box"><input type="text" value={tickers} onChange={(ev) => setTickers(ev.target.value)} /></span></label>
        <label className="answer"><span className="field-label">Counted</span>
          <select value={weighting} onChange={(ev) => setWeighting(ev.target.value)}><option value="value">By value</option><option value="equal">Equally</option></select></label>
        <button className="button-outline" disabled={busy || list.length < 5 || name.trim().length < 3}>Publish it</button>
        {error && <p className="error" role="alert">{error}</p>}
        {done && <p className="small tag-good" role="status">{done}</p>}
      </form>
    </Panel>
  );
}

function remembered(): number | null {
  try {
    const v = window.localStorage.getItem("wsbm-etf-alerts");
    return v === null ? null : Number(v);
  } catch {
    return null;
  }
}

/** Index changes, an ETF far from its value, record money in or out: they pop up for the people they concern. */
export function EtfAlerts({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [shown, setShown] = useState<EtfAlert[]>([]);
  const mark = useRef<number | null>(remembered());
  useEffect(() => {
    let stopped = false;
    function look() {
      api.etfAlerts(mark.current).then((found) => {
        if (stopped) return;
        mark.current = found.mark;
        if (found.alerts.length) setShown((now) => [...now, ...found.alerts.filter((i) => !now.some((x) => x.id === i.id))].slice(-3));
      }).catch((problem) => { if (problem instanceof ApiError && problem.status === 401) onLoggedOut(); });
    }
    look();
    const timer = window.setInterval(look, 60_000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [onLoggedOut]);
  if (shown.length === 0) return null;
  const a = shown[shown.length - 1];
  const close = () => {
    try {
      const before = Number(window.localStorage.getItem("wsbm-etf-alerts") ?? "0");
      window.localStorage.setItem("wsbm-etf-alerts", String(Math.max(before, ...shown.map((x) => x.id))));
    } catch { /* not remembered: fine */ }
    setShown((now) => now.slice(0, -1));
  };
  return (
    <div className="bank-alert-region fund-alert-region etf-alert-region">
      <div className="bank-alert fund-alert" role="alertdialog" aria-labelledby={`etf-alert-${a.id}`}>
        <div className="bank-alert-tag">● {a.kind === "index_change" ? "INDEXES" : `ETFS${a.code ? ` · ${a.code}` : ""}`}</div>
        <div className="bank-alert-headline" id={`etf-alert-${a.id}`}>{a.headline}</div>
        <p className="small">{a.words}</p>
        <div className="bank-alert-actions">
          <a className="button-outline" href="#/market/etfs" onClick={close}>See indexes and ETFs</a>
          <button className="button-quiet" onClick={close}>Close{shown.length > 1 ? ` (${shown.length - 1} more)` : ""}</button>
        </div>
      </div>
    </div>
  );
}
