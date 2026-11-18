// Alerts (owner, 18 November 2026: "Alerts", for a Bloomberg-like Floor). Set an alert on a price, a day's move, the news
// about a company, a flash storm or a new wealth client; the moment one is hit it shows here, as on a Bloomberg terminal.
// The command line takes them too: ALERT HMB > 9.50, ALERT HMB MOVE 5, ALERT HMB NEWS, ALERT STORM.

import { useEffect, useState } from "react";
import { api, ApiError, type Alerts } from "./api";
import { useLoad } from "./hooks";
import { useLivePushes } from "./pushes";
import { Panel } from "./Shell";

const lagosTime = (iso: string) => new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "short", hour: "2-digit", minute: "2-digit" });
const KINDS = [
  { kind: "above", label: "Price at or above", needs: "price" },
  { kind: "below", label: "Price at or below", needs: "price" },
  { kind: "move", label: "A day's move of at least", needs: "pct" },
  { kind: "news", label: "Any story naming", needs: "share" },
  { kind: "storm", label: "A flash storm on the Floor", needs: "" },
  { kind: "wealth", label: "A new wealth client", needs: "" },
] as const;

/** The Floor's alerts: those hit (newest first), those set, and a form to set another. */
export function AlertsPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const page = useLoad(api.alerts, "alerts", onLoggedOut);
  const market = useLoad(api.ticker, "alerts-shares", onLoggedOut);
  const tickers = (market.data?.shares ?? []).map((s) => s.ticker).sort();
  const reload = page.reload;
  useLivePushes(reload, ["floor"]);
  useEffect(() => {
    const id = window.setInterval(reload, 20_000);
    return () => window.clearInterval(id);
  }, [reload]);
  const [fresh, setFresh] = useState<Alerts | null>(null);
  useEffect(() => setFresh(null), [page.data]);
  const a = fresh ?? page.data;
  const [kind, setKind] = useState<(typeof KINDS)[number]["kind"]>("above");
  const [ticker, setTicker] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!a?.ready) return null;
  const needs = KINDS.find((k) => k.kind === kind)!.needs;

  async function act(run: () => Promise<Alerts>, done: (p: Alerts) => string) {
    setBusy(true); setSaid(null);
    try { const p = await run(); setFresh(p); setSaid(done(p)); }
    catch (e) { setSaid(e instanceof ApiError ? e.message : "Could not reach the server."); }
    finally { setBusy(false); }
  }
  function set() {
    const level = needs === "price" ? Math.round(Number(value) * 100) : needs === "pct" ? Math.round(Number(value) * 100) : null;
    act(() => api.setAlert(kind, needs ? ticker : null, level, note), (p) => `Alert set: ${p.result?.words}.${p.result?.warning ? ` ${p.result.warning}` : ""}`);
    setValue(""); setNote("");
  }
  const unseen = a.unseen ?? 0;
  return (
    <Panel title="Alerts" aside={unseen ? `${unseen} new` : `${a.alerts?.length ?? 0} set of ${a.most}`}>
      {(a.hits ?? []).length === 0 && <p className="small muted">Nothing hit yet. Set an alert below, or type ALERT on the terminal's command line.</p>}
      {(a.hits ?? []).length > 0 && (
        <ul className="alert-hits">
          {(a.hits ?? []).slice(0, 8).map((h) => (
            <li key={h.id} className={h.seen ? "small muted" : "small alert-new"}><span className="mono">{lagosTime(h.at)}</span> {h.words}</li>
          ))}
        </ul>
      )}
      {unseen > 0 && <button className="button-outline small" disabled={busy} onClick={() => act(api.alertsSeen, () => "Marked as seen.")}>Mark as seen</button>}
      <div className="alert-form">
        <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="What to watch">
          {KINDS.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
        </select>
        {needs && (
          <select value={ticker} onChange={(e) => setTicker(e.target.value)} aria-label="The company">
            <option value="">Company</option>
            {tickers.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        )}
        {needs === "price" && <label className="small">₦<input className="mono" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="9.50" /></label>}
        {needs === "pct" && <label className="small"><input className="mono" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="5" />%</label>}
        <input className="alert-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="A note to yourself (optional)" maxLength={80} />
        <button className="button-outline small" disabled={busy || (needs !== "" && !ticker) || ((needs === "price" || needs === "pct") && !(Number(value) > 0))} onClick={set}>Set the alert</button>
      </div>
      {said && <p className="small">{said}</p>}
      {(a.alerts ?? []).map((x) => (
        <p key={x.id} className="small">{x.words}{x.note ? ` (${x.note})` : ""}{x.hits ? `, hit ${x.hits} ${x.hits === 1 ? "time" : "times"}` : ""}{" "}
          <button className="button-outline small" disabled={busy} onClick={() => act(() => api.removeAlert(x.id), () => "Removed.")}>Remove</button></p>
      ))}
      <p className="small muted">A price alert is spent once hit; a move alert fires at most once a trading day; news, storm and client alerts stay set.
        On the terminal: ALERT HMB &gt; 9.50, ALERT HMB MOVE 5, ALERT HMB NEWS, ALERT STORM, and ALERTS to come here.</p>
    </Panel>
  );
}
