import type { Player } from "./api";
import { formatCountdown, formatLagosTime, formatMoney, MARKET_LABEL } from "./format";
import type { LiveClock } from "./useClock";

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="tile panel">
      <div className="tile-label">{label}</div>
      <div className="tile-value mono">{value}</div>
      {note && <div className="tile-note muted">{note}</div>}
    </div>
  );
}

const SESSIONS = [
  { state: "opening_auction", name: "Opening auction", hours: "11:30 to 12:00", detail: "Orders are collected. One opening price is set at 12:00." },
  { state: "open", name: "Open", hours: "12:00 to 22:00", detail: "Normal trading." },
  { state: "closed", name: "Closed", hours: "22:00 to 11:30", detail: "Orders wait for the next auction." },
] as const;

export function Home({ player, live }: { player: Player; live: LiveClock | null }) {
  const gameDate = live?.clock.game_date;
  return (
    <main className="home">
      <h1>Welcome, {player.display_name}</h1>

      <section className="tiles">
        <Tile label="Cash" value={formatMoney(player.cash)} note="Your starting balance" />
        <Tile label="Reputation" value={`${player.reputation} / 100`} note="Everyone starts at 50" />
        <Tile
          label="Game date"
          value={gameDate ? `Year ${gameDate.year} · Q${gameDate.quarter}` : "Not started"}
          note={gameDate ? `Day ${gameDate.day_of_quarter} of 90` : "The world has not opened yet"}
        />
        <Tile
          label="Broad Street Exchange"
          value={live ? MARKET_LABEL[live.clock.market_state] : "…"}
          note={live ? `${MARKET_LABEL[live.clock.next_state]} ${formatCountdown(live.msToNextChange)}` : undefined}
        />
      </section>

      <section className="columns">
        <div className="panel">
          <h2>Exchange hours</h2>
          <p className="muted">Lagos time, every day. One clock for every player, wherever they are.</p>
          <table>
            <thead>
              <tr><th>Session</th><th>Hours</th><th>What happens</th></tr>
            </thead>
            <tbody>
              {SESSIONS.map((session) => (
                <tr key={session.state} className={live?.clock.market_state === session.state ? "row-current" : undefined}>
                  <td>{session.name}</td>
                  <td className="mono">{session.hours}</td>
                  <td className="muted">{session.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {live && (
            <p className="next-change">
              Next change: <strong>{MARKET_LABEL[live.clock.next_state]}</strong> at{" "}
              <span className="mono">{formatLagosTime(new Date(live.clock.next_change_at), false)}</span>
            </p>
          )}
        </div>

        <div className="panel">
          <h2>Game calendar</h2>
          <p className="muted">The business calendar runs faster than real time.</p>
          <table>
            <tbody>
              <tr><td>One real week</td><td className="mono">One game quarter</td></tr>
              <tr><td>Four real weeks</td><td className="mono">One game year</td></tr>
              <tr><td>Company results</td><td className="mono">Every game quarter</td></tr>
              <tr><td>Elections and tax</td><td className="mono">Every game year</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
