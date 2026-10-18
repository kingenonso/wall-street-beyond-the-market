import { useState } from "react";
import { api, type Charity, type IntelPiece, type InvestigationFile, type MediaTitle, type Player, type PressDesk, type TitleAuction } from "./api";
import { formatNaira } from "./format";
import { useLoad } from "./hooks";
import { Notices, useRun } from "./Newsroom";
import { Failed, Loading, Panel } from "./Shell";
import { Term } from "./Term";

/** Stage 10, Part 2: information as a thing in the world — the Sealed Tip, what the player holds, the Intelligence Market,
 * the record of rumours, sources and investigations. Never a piece's truth: the player learns it by checking or by waiting. */

const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", dateStyle: "medium", timeStyle: "short" }) : "";

function About({ p }: { p: IntelPiece }) {
  const a = p.about;
  const names = [a.company && `${a.company}${a.ticker ? ` (${a.ticker})` : ""}`, a.empire, a.other_empire, a.city].filter(Boolean).join(" · ");
  return <span className="small muted">{names || a.topic}</span>;
}

function Status({ p }: { p: IntelPiece }) {
  const tag = p.status === "verified" ? "tag-good" : p.status === "disproved" ? "tag-bad" : "tag";
  return (
    <span className="small">
      <span className={tag}>{p.status_words}</span>
      {p.confidential && <> · <Term word="Confidential information">from inside</Term></>}
      {p.reliability_bps !== null && <> · source right {Math.round(p.reliability_bps / 100)}% of the time</>}
      {" · "}{p.useful ? (p.useful_until ? `useful until ${when(p.useful_until)}` : "useful") : "no longer useful"}
    </span>
  );
}

type IntelTab = "today" | "market" | "rumours" | "sources" | "investigations";

export function IntelWork({ player, tab: start, onLoggedOut }: { player: Player; tab?: string; onLoggedOut: () => void }) {
  const journalist = player.build === "journalist";
  const known: IntelTab[] = ["today", "market", "rumours", ...(journalist ? (["sources", "investigations"] as IntelTab[]) : [])];
  const [tab, setTab] = useState<IntelTab>(known.includes(start as IntelTab) ? (start as IntelTab) : "today");
  const tabs: [IntelTab, string][] = [["today", "Your tip and pieces"], ["market", "The market"], ["rumours", "Rumours on the record"],
    ...(journalist ? ([["sources", "Sources"], ["investigations", "Investigations"]] as [IntelTab, string][]) : [])];
  function choose(next: IntelTab) {
    setTab(next);
    window.history.replaceState(null, "", `#/intel/${next}`);
  }
  return (
    <>
      <div className="page-head"><h1>Intelligence</h1><span className="muted small">Who knew what, and when, is kept for good</span></div>
      <div className="underline-tabs" role="tablist" aria-label="Intelligence">
        {tabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : undefined} onClick={() => choose(key)}>{label}</button>)}
      </div>
      {tab === "today" && <Today player={player} onLoggedOut={onLoggedOut} />}
      {tab === "market" && <Market onLoggedOut={onLoggedOut} />}
      {tab === "rumours" && <Rumours onLoggedOut={onLoggedOut} />}
      {tab === "sources" && journalist && <Sources onLoggedOut={onLoggedOut} />}
      {tab === "investigations" && journalist && <Investigations onLoggedOut={onLoggedOut} />}
    </>
  );
}

export function IntelRail() {
  return (
    <Panel title="How information works">
      <ul className="reasons small">
        <li>Each real day you get one <strong>Sealed Tip</strong>, matched to your build. About a third are real and still to come, a third are false, a third are already public. Once opened, it is useful for four hours.</li>
        <li><strong>Check</strong> a piece before you act on it: it costs ₦50,000 and is right most of the time.</li>
        <li>Sell copies on the market, or pass a piece to a Financial Journalist. Who held what, and since when, is kept.</li>
        <li>Trading on a piece from someone inside a company, while it is useful, is <Term word="Confidential information">dealing on confidential information</Term>: it is kept for the courts.</li>
      </ul>
    </Panel>
  );
}

function Today({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.intel, "intel", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [give, setGive] = useState<Record<string, string>>({});
  const [price, setPrice] = useState<Record<string, string>>({});
  if (loading && !data) return <Loading what="your information" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const tip = data.tip;
  return (
    <>
      <Notices act={act} />
      <Panel title="Today's Sealed Tip" aside={tip.opened ? undefined : `for a ${tip.for}`}>
        {!tip.opened ? (
          <>
            <p>{tip.words}</p>
            <button className="button-primary" disabled={act.busy} onClick={() => act.run(() => api.post("/intel/tip/open"), "Opened.")}>Open it</button>
          </>
        ) : (
          <>
            <p className="strong">{tip.words}</p>
            <p><About p={tip} /> · <Status p={tip} /></p>
            {tip.check && <p className="small">Your check: {tip.check}</p>}
          </>
        )}
        <p className="muted small">One a day. Extra tips can never be bought.</p>
      </Panel>
      <Panel title="What you hold" aside={`${data.mine.length} piece${data.mine.length === 1 ? "" : "s"}`}>
        {data.mine.length === 0 && <p className="muted">Nothing yet. Open your tip, or buy a piece on the market.</p>}
        {data.mine.map((p) => (
          <div key={p.ref} className="fact-row">
            <div>
              <div className="strong">{p.words}</div>
              <div><About p={p} /> · <Status p={p} /> · {p.holders} hold it</div>
              {p.check && <div className="small">Checked: {p.check}</div>}
            </div>
            {p.useful && (
              <div className="intel-actions">
                {!p.check && <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post("/intel/check", { ref: p.ref }), (r) => String(r.words ?? "Checked."))}>Check it (₦50,000)</button>}
                <label className="answer small">Pass to a journalist<input type="text" maxLength={40} value={give[p.ref] ?? ""} onChange={(e) => setGive({ ...give, [p.ref]: e.target.value })} placeholder="their name" /></label>
                <button className="button-quiet" disabled={act.busy || !(give[p.ref] ?? "").trim()} onClick={() => act.run(() => api.post("/intel/give", { ref: p.ref, to: give[p.ref] }), (r) => String(r.words ?? "Given."))}>Pass it on</button>
                <label className="answer small">Sell copies at ₦<input type="number" min={10000} step={10000} value={price[p.ref] ?? ""} onChange={(e) => setPrice({ ...price, [p.ref]: e.target.value })} /></label>
                <button className="button-quiet" disabled={act.busy || !Number(price[p.ref])} onClick={() => act.run(() => api.post("/intel/offer", { ref: p.ref, price_naira: Math.round(Number(price[p.ref])) }), "Offered on the market.")}>Offer</button>
                {player.build === "journalist" && <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post("/newsroom/lead", { ref: p.ref }), "Added to your story, as an unconfirmed report.")}>Put in my story</button>}
              </div>
            )}
          </div>
        ))}
      </Panel>
      <Panel title={`For your work: ${data.feed.build}`} aside="from the public record">
        {data.feed.items.length === 0 ? <p className="muted">Nothing on the record for your desk yet.</p> : (
          <ul className="reasons small">{data.feed.items.map((i, n) => <li key={n}>{i.what}</li>)}</ul>
        )}
      </Panel>
    </>
  );
}

function Market({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.intel, "intel-market", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  if (loading && !data) return <Loading what="the market" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <Notices act={act} />
      <Panel title="The Intelligence Market" aside="you read a piece's words only once you buy it">
        {data.market.length === 0 && <p className="muted">Nothing is offered just now.</p>}
        {data.market.map((l) => (
          <div key={l.listing_id} className="fact-row">
            <div>
              <div className="strong">{l.held && l.words ? l.words : `A ${l.kind.replace("_", " ")} about ${l.about.company ?? l.about.empire ?? l.about.city ?? l.about.topic}`}</div>
              <div><About p={l} /> · <Status p={l} /> · offered by {l.seller} · {l.holders} hold it · sold {l.sold}</div>
            </div>
            <div className="intel-actions">
              <span className="mono">{formatNaira(l.price)}</span>
              {l.yours ? <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post(`/intel/listings/${l.listing_id}/withdraw`), "Withdrawn.")}>Withdraw</button>
                : l.held ? <span className="muted small">you hold it</span>
                : <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.post(`/intel/listings/${l.listing_id}/buy`), "Bought: it is in what you hold.")}>Buy</button>}
            </div>
          </div>
        ))}
      </Panel>
    </>
  );
}

function Rumours({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.rumours, "rumours", onLoggedOut);
  if (loading && !data) return <Loading what="the record of rumours" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <Panel title="Unconfirmed reports: what was believed, and what was true">
      {data.rumours.length === 0 && <p className="muted">No unconfirmed report has run yet.</p>}
      {data.rumours.length > 0 && (
        <table className="table">
          <thead><tr><th scope="col">Report</th><th scope="col">By</th><th scope="col">When</th><th scope="col" className="num">Readers</th><th scope="col" className="num">Investors marked it</th><th scope="col">Turned out</th></tr></thead>
          <tbody>
            {data.rumours.map((r) => (
              <tr key={r.story_id}>
                <td>{r.headline}</td><td>{r.author}</td><td>{r.when}</td><td className="num mono">{r.readers.toLocaleString("en-NG")}</td>
                <td className="num mono">{r.marked_bps ? `${(r.marked_bps / 100).toFixed(2)}%` : "—"}</td>
                <td><span className={r.outcome === "borne out" ? "tag-good" : r.outcome === "proved wrong" ? "tag-bad" : "muted"}>{r.outcome}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function Sources({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.intel, "intel-sources", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [kind, setKind] = useState<"company" | "ministry">("company");
  const [ticker, setTicker] = useState("");
  if (loading && !data) return <Loading what="your sources" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const sources = data.sources ?? [];
  return (
    <>
      <Notices act={act} />
      <Panel title="Your sources" aside={`you may keep ${data.sources_allowed ?? 2}`}>
        {sources.length === 0 && <p className="muted">No sources yet. Building one takes two quarters.</p>}
        {sources.map((s) => (
          <div key={s.id} className="fact-row">
            <div>
              <div className="strong">{s.kind === "company" ? `Inside ${s.where}` : "In the ministries"}</div>
              <div className="small muted">{s.status === "cultivating" ? `Being built: ready ${s.ready}` : s.status === "burned" ? "Burned: they will not talk to you again" : `Ready · right about ${Math.round(s.reliability_bps / 100)}% of the time`}</div>
            </div>
            {s.status === "active" && (
              <div className="intel-actions">
                <button className="button-outline" disabled={act.busy || s.asked_today} onClick={() => act.run(() => api.post(`/intel/sources/${s.id}/ask`), "Your source told you something: it is in what you hold.")}>{s.asked_today ? "Asked today" : "Ask"}</button>
                <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post(`/intel/sources/${s.id}/drop`), "Dropped.")}>Drop</button>
              </div>
            )}
          </div>
        ))}
      </Panel>
      <Panel title="Build a new source" aside="one a quarter">
        <div className="form-row">
          <label className="answer">Where<select value={kind} onChange={(e) => setKind(e.target.value as "company" | "ministry")}><option value="company">inside a company</option><option value="ministry">in the ministries</option></select></label>
          {kind === "company" && <label className="answer">Ticker<input type="text" maxLength={5} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} /></label>}
          <button className="button-primary" disabled={act.busy || (kind === "company" && ticker.length < 2)} onClick={() => act.run(() => api.post("/intel/sources", { kind, ticker: kind === "company" ? ticker : null }), (r) => String(r.words ?? "Begun."))}>Begin</button>
        </div>
        <p className="muted small">A source inside a company tells you what is coming there before the quarter is out; one in the ministries, which way the Central Bank leans or where the Government will build. Print a source's hint before it is borne out, or sell it, and you may burn the source.</p>
      </Panel>
    </>
  );
}

function FileCard({ f, act }: { f: InvestigationFile; act: ReturnType<typeof useRun> }) {
  return (
    <Panel title={`${f.kind === "charity" ? "The charity " : ""}${f.target}`} aside={`${f.status} · opened ${f.opened}`}>
      <p>
        Documents <span className="mono">{f.documents} of {f.needed}</span> · second source {f.confirmed ? <span className="tag-good">confirmed</span> : <span className="muted">not yet</span>}
      </p>
      <ol className="reasons small">{f.notes.slice(-8).map((n, i) => <li key={i}>{n}</li>)}</ol>
      {f.status === "open" && (
        <div className="button-row">
          <button className="button-outline" disabled={act.busy || f.dug_today} onClick={() => act.run(() => api.post(`/investigations/${f.id}/dig`), "Searched.")}>{f.dug_today ? "Searched today" : "Search for documents"}</button>
          <button className="button-quiet" disabled={act.busy || f.asked_today || f.confirmed || f.documents < 2} onClick={() => act.run(() => api.post(`/investigations/${f.id}/second-source`), "Asked around.")}>Seek a second source</button>
          <button className="button-primary" disabled={act.busy || !f.can_publish} onClick={() => act.run(() => api.post(`/investigations/${f.id}/publish`), (r) => `Published: ${Number(r.readers ?? 0).toLocaleString("en-NG")} readers.`)}>Publish the exposé</button>
          <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post(`/investigations/${f.id}/drop`), "Dropped.")}>Drop</button>
        </div>
      )}
    </Panel>
  );
}

function Investigations({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.investigations, "investigations", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [target, setTarget] = useState<"empire" | "charity">("empire");
  const [name, setName] = useState("");
  if (loading && !data) return <Loading what="your investigations" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <Notices act={act} />
      <Panel title="Open a file" aside="two at a time">
        <div className="form-row">
          <label className="answer">On<select value={target} onChange={(e) => setTarget(e.target.value as "empire" | "charity")}><option value="empire">an empire</option><option value="charity">a charity</option></select></label>
          <label className="answer">Its name<input type="text" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} /></label>
          <button className="button-primary" disabled={act.busy || name.trim().length < (target === "charity" ? 4 : 3)} onClick={() => act.run(() => target === "empire" ? api.post("/investigations", { empire: name }) : api.post("/investigations/charity", { charity: name }), "File opened.")}>Open</button>
        </div>
        <p className="muted small">Search a day at a time. Documents turn up only if there is something hidden: money taken inside an empire, an unlawful pact, or a charity paying its own. Three documents and a second source, and the exposé can run.</p>
      </Panel>
      {data.files.map((f) => <FileCard key={f.id} f={f} act={act} />)}
    </>
  );
}

// ---------------------------------------------------------------------------
// The empire's press desk
// ---------------------------------------------------------------------------

export function PressDeskView({ onLoggedOut }: { onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.pressDesk, "press-desk", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [stance, setStance] = useState<Record<number, string>>({});
  const [statement, setStatement] = useState<Record<number, string>>({});
  const [reply, setReply] = useState<Record<number, string>>({});
  if (loading && !data) return <Loading what="the press desk" />;
  if (error && !data) return <Panel title="The press desk"><p className="muted">{error}</p></Panel>;
  if (!data) return null;
  const d: PressDesk = data;
  return (
    <>
      <Notices act={act} />
      <Panel title="Matters to answer" aside="a day to answer each">
        {d.crises.length === 0 && <p className="muted">Nothing has come out about the empire.</p>}
        {d.crises.map((c) => (
          <div key={c.id} className="fact-row">
            <div>
              <div className="strong">{c.words}</div>
              <div className="small muted">{c.status === "open" ? `Answer by ${when(c.due_at)}` : c.status === "silent" ? "Not answered in time" : `Answered: ${c.stance_words}`}
                {c.change !== null ? <> · reputation {c.change > 0 ? "+" : ""}{c.change}</> : c.status !== "open" ? <> · its effect waits on the report being settled</> : null}</div>
              {c.status === "open" && (
                <div className="form-row">
                  <label className="answer">Stance<select value={stance[c.id] ?? ""} onChange={(e) => setStance({ ...stance, [c.id]: e.target.value })}>
                    <option value="">choose…</option>{Object.entries(d.stances).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
                  <label className="answer answer-block">Statement (no figures)<textarea rows={2} maxLength={300} value={statement[c.id] ?? ""} onChange={(e) => setStatement({ ...statement, [c.id]: e.target.value })} /></label>
                  <button className="button-primary" disabled={act.busy || !stance[c.id] || (statement[c.id] ?? "").trim().length < 10}
                    onClick={() => act.run(() => api.post(`/press/crises/${c.id}`, { stance: stance[c.id], statement: statement[c.id] }), "The statement has gone out.")}>Make the statement</button>
                </div>
              )}
            </div>
          </div>
        ))}
        <p className="muted small">Admitting what is true, quickly, costs least. Denying what is true costs most; saying nothing costs a lot. Denying what is false helps.</p>
      </Panel>
      <Panel title="Who has been looking at us" aside="from public traces only">
        {d.looking.length === 0 ? <p className="muted">No journalist has asked about the empire or written about it lately.</p> : (
          d.looking.map((l) => (
            <div key={l.journalist} className="fact-row"><div><div className="strong">{l.journalist}</div><ul className="reasons small">{l.traces.map((t, i) => <li key={i}>{t}</li>)}</ul></div><span className="mono">{l.count}</span></div>
          ))
        )}
      </Panel>
      <Panel title="Stories about us">
        {d.stories.length === 0 && <p className="muted">No story about the empire yet.</p>}
        {d.stories.map((s) => (
          <div key={s.id} className="fact-row">
            <div><div className="strong">{s.headline}</div><div className="small muted">{s.when} · {s.readers.toLocaleString("en-NG")} readers</div>
              <label className="answer answer-block">An honest reply (no figures)<textarea rows={2} maxLength={300} value={reply[s.id] ?? ""} onChange={(e) => setReply({ ...reply, [s.id]: e.target.value })} /></label></div>
            <div className="intel-actions">
              <button className="button-quiet" disabled={act.busy || (reply[s.id] ?? "").trim().length < 20} onClick={() => act.run(() => api.post("/press/reply", { story_id: s.id, words: reply[s.id] }), "Your reply has gone out.")}>Reply</button>
              {d.head && !s.asked && <button className="button-quiet" disabled={act.busy} onClick={() => act.run(() => api.post("/press/spin", { story_id: s.id }), "Asked. Your journalist decides.")}>Ask our journalist to answer it our way</button>}
            </div>
          </div>
        ))}
      </Panel>
      {d.requests.length > 0 && (
        <Panel title={d.head ? "What you asked of your journalist" : "The head's requests"} aside="refusing keeps a clean name">
          {d.requests.map((r) => (
            <div key={r.id} className="fact-row">
              <div><div className="strong">{r.headline}</div><div className="small muted">{r.status}</div></div>
              {!d.head && r.status === "asked" && (
                <div className="intel-actions">
                  <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.post(`/press/spin/${r.id}`, { comply: false }), "You refused.")}>Refuse</button>
                  <button className="button-quiet" disabled={act.busy || (reply[-r.id] ?? "").trim().length < 20}
                    onClick={() => act.run(() => api.post(`/press/spin/${r.id}`, { comply: true, words: reply[-r.id] }), "Your reply has gone out.")}>Go along</button>
                  <label className="answer answer-block small">The reply they want<textarea rows={2} maxLength={300} value={reply[-r.id] ?? ""} onChange={(e) => setReply({ ...reply, [-r.id]: e.target.value })} /></label>
                </div>
              )}
            </div>
          ))}
          <p className="muted small">A reply written to mislead helps for now; one in four comes out each quarter, and then it costs the empire and the journalist.</p>
        </Panel>
      )}
      <Panel title="Leaks" aside="hunt each once">
        {d.leaks.length === 0 ? <p className="muted">Nothing from inside the empire has been printed.</p> : d.leaks.map((l) => (
          <div key={l.id} className="fact-row">
            <div><div className="strong">{l.words}</div><div className="small muted">{when(l.at)}{l.hunted ? (l.found ? " · traced" : " · the hunt found nothing") : ""}</div></div>
            {!l.hunted && <button className="button-outline" disabled={act.busy} onClick={() => act.run(() => api.post(`/press/leaks/${l.id}/hunt`), (r) => String(r.words ?? "Done."))}>Hunt the leaker</button>}
          </div>
        ))}
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------------------
// Charities
// ---------------------------------------------------------------------------

const CAUSES: Record<string, string> = { education: "Education", health: "Health", water: "Clean water", arts: "The arts", relief: "Disaster relief" };
const CITIES = ["Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"];

export function CharitiesWork({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.charities, "charities", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [form, setForm] = useState({ name: "", cause: "education", city: "Lagos", amount: "1000000", for_empire: false });
  const [gift, setGift] = useState<Record<number, string>>({});
  const [grant, setGrant] = useState<Record<number, { amount: string; words: string; to: string }>>({});
  if (loading && !data) return <Loading what="the charities" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const isHead = !!player.empire && !player.empire.forming && player.empire.is_head;
  return (
    <>
      <div className="page-head"><h1>Charities</h1><span className="muted small">Giving builds a name; only what reaches the cause counts</span></div>
      <Notices act={act} />
      <Panel title="Found a charity" aside="at least ₦1,000,000 of your own">
        <div className="form-row">
          <label className="answer">Name<input type="text" maxLength={60} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="answer">Cause<select value={form.cause} onChange={(e) => setForm({ ...form, cause: e.target.value })}>{Object.entries(CAUSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="answer">City<select value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })}>{CITIES.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="answer">₦<input type="number" min={1000000} step={100000} value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
          {isHead && <label className="check-line"><input type="checkbox" checked={form.for_empire} onChange={(e) => setForm({ ...form, for_empire: e.target.checked })} /> For my empire</label>}
          <button className="button-primary" disabled={act.busy || form.name.trim().length < 4}
            onClick={() => act.run(() => api.post("/charities", { name: form.name, cause: form.cause, city: form.city, amount_naira: Math.round(Number(form.amount)), for_empire: form.for_empire }), "Founded.")}>Found it</button>
        </div>
      </Panel>
      {data.charities.length === 0 && <Panel><p className="muted">No charity has been founded yet.</p></Panel>}
      {data.charities.map((c: Charity) => (
        <Panel key={c.id} title={c.name} aside={`${c.cause} · ${c.city} · since ${c.since}`}>
          <p className="small">Founded by <strong>{c.founder}</strong>{c.under_a_cloud && <> · <span className="tag-bad">exposed: it paid its own</span></>}</p>
          <div className="stat-row">
            <div><div className="muted small">Given to it</div><div className="mono">{formatNaira(c.given)}</div></div>
            <div><div className="muted small">Granted to its cause</div><div className="mono">{formatNaira(c.to_cause)}</div></div>
            <div><div className="muted small">Granted to people</div><div className="mono">{formatNaira(c.to_people)}</div></div>
            <div><div className="muted small">It holds</div><div className="mono">{formatNaira(c.holds)}</div></div>
          </div>
          <div className="form-row">
            <label className="answer">Give ₦<input type="number" min={10000} step={10000} value={gift[c.id] ?? ""} onChange={(e) => setGift({ ...gift, [c.id]: e.target.value })} /></label>
            <button className="button-outline" disabled={act.busy || !Number(gift[c.id])} onClick={() => act.run(() => api.post(`/charities/${c.id}/give`, { amount_naira: Math.round(Number(gift[c.id])) }), "Thank you: given.")}>Give</button>
          </div>
          {c.yours && (
            <>
              <div className="form-row">
                <label className="answer">Grant ₦<input type="number" min={10000} step={10000} value={grant[c.id]?.amount ?? ""} onChange={(e) => setGrant({ ...grant, [c.id]: { ...(grant[c.id] ?? { words: "", to: "" }), amount: e.target.value } })} /></label>
                <label className="answer">For<input type="text" maxLength={200} value={grant[c.id]?.words ?? ""} onChange={(e) => setGrant({ ...grant, [c.id]: { ...(grant[c.id] ?? { amount: "", to: "" }), words: e.target.value } })} placeholder="what it pays for" /></label>
                <label className="answer">To a person (empty: the cause)<input type="text" maxLength={40} value={grant[c.id]?.to ?? ""} onChange={(e) => setGrant({ ...grant, [c.id]: { ...(grant[c.id] ?? { amount: "", words: "" }), to: e.target.value } })} /></label>
                <button className="button-primary" disabled={act.busy || !Number(grant[c.id]?.amount) || (grant[c.id]?.words ?? "").trim().length < 5}
                  onClick={() => act.run(() => api.post(`/charities/${c.id}/grant`, { amount_naira: Math.round(Number(grant[c.id]!.amount)), words: grant[c.id]!.words, to: grant[c.id]!.to.trim() || null }), "Granted.")}>Make the grant</button>
              </div>
              {(c.grants ?? []).length > 0 && <ul className="reasons small">{c.grants!.map((g, i) => <li key={i}>{formatNaira(g.amount)} {g.to_whom ? `to ${g.to_whom}` : "to the cause"}: {g.words}</li>)}</ul>}
              <p className="muted small">Grants to people close to you or your donors move money to insiders under a good name: the Money Watch looks at them, and journalists can investigate.</p>
            </>
          )}
        </Panel>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Media titles at the Auction House
// ---------------------------------------------------------------------------

export function TitlesView({ player, onLoggedOut }: { player: Player; onLoggedOut: () => void }) {
  const { data, error, loading, reload } = useLoad(api.media, "media-titles", onLoggedOut);
  const act = useRun(reload, onLoggedOut);
  const [limit, setLimit] = useState<Record<number, string>>({});
  const [reserve, setReserve] = useState<Record<number, string>>({});
  if (loading && !data) return <Loading what="the titles" />;
  if (error && !data) return <Failed message={error} onRetry={reload} />;
  if (!data) return null;
  const isHead = !!player.empire && !player.empire.forming && player.empire.is_head;
  return (
    <>
      <Notices act={act} />
      {data.auctions.length > 0 && (
        <Panel title="At the Auction House" aside="your top price stays secret">
          {data.auctions.map((a: TitleAuction) => (
            <div key={a.id} className="fact-row">
              <div>
                <div className="strong">{a.title.name} <span className="muted small">· {a.title.kind} · {a.title.city} · {a.title.audience.toLocaleString("en-NG")} readers</span></div>
                <div className="small muted">{a.status === "coming" ? `Opens ${when(a.opens_at)}` : a.status === "open" ? `Ends ${when(a.ends_at)}` : a.status}
                  {" · "}worth about {formatNaira(a.fair)} · {a.price ? `leading bid ${formatNaira(a.price)}` : `opens at ${formatNaira(a.start_price)}`}
                  {a.lowest_price_met ? " · lowest price met" : ""} · {a.bidders} bidder{a.bidders === 1 ? "" : "s"}
                  {a.you_lead ? " · you lead" : a.your_status ? ` · your bid: ${a.your_status}` : ""}</div>
              </div>
              {a.status === "open" && (
                <div className="intel-actions">
                  <label className="answer small">Your top price ₦<input type="number" min={1} value={limit[a.id] ?? ""} onChange={(e) => setLimit({ ...limit, [a.id]: e.target.value })} /></label>
                  <button className="button-outline" disabled={act.busy || !Number(limit[a.id])} onClick={() => act.run(() => api.post(`/auctions/${a.id}/bid`, { limit_kobo: Math.round(Number(limit[a.id]) * 100) }), "Your bid stands.")}>Bid</button>
                  {isHead && <button className="button-quiet" disabled={act.busy || !Number(limit[a.id])} onClick={() => act.run(() => api.post(`/empire/auctions/${a.id}/bid`, { limit_kobo: Math.round(Number(limit[a.id]) * 100) }), "The empire's bid stands.")}>Bid for my empire</button>}
                </div>
              )}
            </div>
          ))}
        </Panel>
      )}
      <Panel title="The titles" aside="an owner earns from readers">
        {data.titles.map((t: MediaTitle) => (
          <div key={t.id} className="fact-row">
            <div>
              <div className="strong">{t.name} <span className="muted small">· {t.kind} · {t.city}</span></div>
              <div className="small muted">{t.audience.toLocaleString("en-NG")} readers · owned by {t.owner} since {t.since} · worth about {formatNaira(t.worth)}
                {t.last[0] ? ` · last quarter's profit ${formatNaira(t.last[0].profit)}` : ""}{t.for_sale ? " · for sale" : ""}</div>
            </div>
            {t.yours && !t.for_sale && (
              <div className="intel-actions">
                <label className="answer small">Lowest price ₦<input type="number" min={0} value={reserve[t.id] ?? ""} onChange={(e) => setReserve({ ...reserve, [t.id]: e.target.value })} /></label>
                <button className="button-quiet" disabled={act.busy || reserve[t.id] === undefined} onClick={() => act.run(() => api.post(`/media/${t.id}/sell`, { reserve_naira: Math.round(Number(reserve[t.id] ?? 0)), for_empire: t.owner === player.empire?.name }), "It is up for auction.")}>Sell at auction</button>
              </div>
            )}
          </div>
        ))}
        <p className="muted small">Each quarter a title brings in ₦40 a reader, and ₦2 for each reader of the stories printed in it; three-fifths go on staff, paper and print, the rest to its owner. A journalist who owns a title, or sits in the empire that owns it, may print in it.</p>
      </Panel>
    </>
  );
}
