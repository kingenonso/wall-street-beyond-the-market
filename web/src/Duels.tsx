// Duels on the Floor (owner, 16 November 2026: "Duel on the Floor"): The Floor → Duels. The head challenges another
// empire for the next live event; both are scored on what the event did to their money plus what their bankers earned on
// the Floor during it, against what each was worth at the bell. The score runs live; the higher wins league points.
// Declining is free, but three declines in a season are shown here beside the empire's name.

import { useEffect, useState } from "react";
import { api, ApiError, type Duel, type DuelsPage, type Player } from "./api";
import { useLoad } from "./hooks";
import { useLivePushes } from "./pushes";
import { Failed, Loading, PageHead, Panel } from "./Shell";

type Props = { player: Player; onLoggedOut: () => void };
const signed = (bps: number | null | undefined) => (bps === null || bps === undefined ? "—" : `${bps > 0 ? "+" : bps < 0 ? "−" : ""}${(Math.abs(bps) / 100).toFixed(2)}%`);
const tone = (bps: number | null | undefined) => (!bps ? "" : bps > 0 ? "change-up" : "change-down");
const when = (iso: string) => new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", weekday: "long", hour: "2-digit", minute: "2-digit" });
const STATUS: Record<Duel["status"], string> = { offered: "Waiting for an answer", accepted: "On", declined: "Declined", lapsed: "Not answered",
  withdrawn: "Withdrawn", scored: "Over", void: "No event that evening" };

function LiveScore({ d }: { d: Duel }) {
  if (!d.live) return null;
  const { you, rival } = d.live;
  const ahead = you.bps > rival.bps ? "You lead" : you.bps < rival.bps ? `${d.rival} leads` : "Level";
  return (
    <div className="duel-live" role="status">
      <span className="live-dot" aria-hidden="true" /><span className="live-word">Live</span>
      <span className={`mono strong ${tone(you.bps)}`}>You {signed(you.bps)}</span>
      <span className={`mono strong ${tone(rival.bps)}`}>{d.rival} {signed(rival.bps)}</span>
      <span className="small">{ahead}. The event: you {signed(you.event_bps)}, them {signed(rival.event_bps)}; the Floor: you {signed(you.floor_bps)}, them {signed(rival.floor_bps)}.</span>
    </div>
  );
}

export function DuelsWork({ onLoggedOut }: Props) {
  const page = useLoad(api.duels, "floor-duels", onLoggedOut);
  const [fresh, setFresh] = useState<DuelsPage | null>(null);
  const d = fresh ?? page.data;
  useEffect(() => { if (page.data) setFresh(null); }, [page.data]);
  const reload = page.reload;
  useLivePushes(reload, ["plan", "event"]);
  const running = Boolean(d?.duels?.some((x) => x.live));
  useEffect(() => {
    const id = window.setInterval(reload, running ? 10_000 : 60_000);
    return () => window.clearInterval(id);
  }, [running, reload]);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; words: string } | null>(null);
  async function run(ask: () => Promise<DuelsPage>, words: string) {
    setBusy(true); setSaid(null);
    try { setFresh(await ask()); setSaid({ ok: true, words }); }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
      setSaid({ ok: false, words: problem instanceof ApiError ? problem.message : "Could not reach the server." });
    } finally { setBusy(false); }
  }
  if (page.loading && !d) return <Loading what="the duels" />;
  if (page.error || !d) return <Failed message={page.error ?? "Could not load the duels."} onRetry={page.reload} />;
  if (!d.ready) return <Panel title="Duels"><p className="small">Duels have not started in this world yet.</p></Panel>;
  const duels = d.duels ?? [];
  const offered = duels.filter((x) => x.status === "offered");
  const current = duels.filter((x) => x.status === "accepted");
  const past = duels.filter((x) => !["offered", "accepted"].includes(x.status));
  return (
    <>
      <PageHead title="Duels" sub="Two empires against each other in a live event: the event's result for each, plus what its bankers earn on the Floor"
                aside={`next bell ${when(d.next_bell!)}`} />
      {said && <p className={`small ${said.ok ? "" : "change-down"}`} role={said.ok ? "status" : "alert"}>{said.words}</p>}
      {!d.empire && <Panel title="Duels"><p className="small">Join an empire run by players to duel. Its head challenges.</p></Panel>}
      {current.length > 0 && (
        <Panel title="Your duel" aside="scored when the live event ends">
          {current.map((x) => (
            <div key={x.id} className="duel-card">
              <p><strong>{d.empire}</strong> against <strong>{x.rival}</strong>, at the bell on {when(x.bell)}.</p>
              <LiveScore d={x} />
              {!x.live && <p className="small muted">The score runs from the bell.</p>}
            </div>
          ))}
        </Panel>
      )}
      {offered.length > 0 && (
        <Panel title="Challenges waiting" aside={`answer before ${when(d.closes_at ?? d.next_bell!)}`}>
          {offered.map((x) => (
            <div key={x.id} className="duel-card">
              <p>{x.you_challenged ? <>You challenged <strong>{x.rival}</strong>: waiting for their head.</> : <><strong>{x.rival}</strong> challenges {d.empire} to a duel at the bell on {when(x.bell)}.</>}</p>
              {d.is_head && !x.you_challenged && (
                <div className="duel-actions">
                  <button className="button-primary" disabled={busy} onClick={() => run(() => api.duelAnswer(x.id, true), `You accepted: ${d.empire} duels ${x.rival} at the next bell.`)}>Accept</button>
                  <button className="button-outline" disabled={busy} onClick={() => run(() => api.duelAnswer(x.id, false), "You declined. Three declines in a season are shown on your record.")}>Decline</button>
                </div>
              )}
              {d.is_head && x.you_challenged && <button className="button-outline" disabled={busy} onClick={() => run(() => api.duelWithdraw(x.id), "Withdrawn.")}>Withdraw</button>}
            </div>
          ))}
        </Panel>
      )}
      {d.empire && (
        <Panel title="Challenge an empire" aside={d.is_head ? `for the bell on ${when(d.next_bell!)}` : "only the head challenges"}>
          <p className="small muted">Win: {d.points?.win} league points; a draw: {d.points?.draw} each. An empire the computer runs always accepts. Challenges close ten minutes before the bell.</p>
          <ul className="duel-rivals">{(d.rivals ?? []).map((r) => (
            <li key={r.id}>
              <span className="strong">{r.name}</span>{r.computer && <span className="muted small"> · computer</span>}
              {r.declines >= (d.shown_declines ?? 3) && <span className="change-down small"> · declined {r.declines} challenges this season</span>}
              {d.is_head && <button className="button-outline small" disabled={busy || !r.free || current.length > 0 || offered.some((o) => o.you_challenged)}
                onClick={() => run(() => api.duelChallenge(r.id), `Challenge sent to ${r.name}.`)}>{r.free ? "Challenge" : "Busy"}</button>}
            </li>
          ))}</ul>
        </Panel>
      )}
      {past.length > 0 && (
        <Panel title="Past duels">
          <ul className="duel-rivals">{past.map((x) => (
            <li key={x.id}>
              <span>{when(x.bell)} · against <strong>{x.rival}</strong></span>
              <span className="small">{x.status === "scored" ? <>{x.won === true ? <span className="change-up">Won</span> : x.won === false ? <span className="change-down">Lost</span> : "Drawn"} · you {signed(x.you_bps)}, them {signed(x.rival_bps)}</> : STATUS[x.status]}</span>
            </li>
          ))}</ul>
        </Panel>
      )}
    </>
  );
}
