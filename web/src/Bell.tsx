import { api } from "./api";
import { formatCompact, formatLagosTime, formatNaira } from "./format";
import { useLoad } from "./hooks";
import { shortDate } from "./Market";
import { Change, Panel } from "./Shell";

const count = (n: number) => n.toLocaleString("en-NG");

/** The Closing Rush while it is on, and the latest Closing Bell broadcast. */
export function ClosingBellPanel({ onLoggedOut, brief = false }: { onLoggedOut: () => void; brief?: boolean }) {
  const { data } = useLoad(api.closingBell, "closing-bell", onLoggedOut);
  if (!data) return null;
  const bell = data.bell;
  return (
    <>
      {(data.in_rush || data.large_orders.length > 0) && (
        <Panel title="The Closing Rush" aside={data.in_rush ? "On now, until 22:00 Lagos time" : "Today's, 21:50 to 22:00"}>
          {data.in_rush && (
            <p>
              For the last ten minutes of the trading day, buyer and seller each pay <span className="mono strong">{(data.fee_bps / 100).toFixed(2)}%</span>{" "}
              in fees instead of {(data.usual_fee_bps / 100).toFixed(2)}%. Every large order is shown here as it arrives: its size, never who placed it.
            </p>
          )}
          {data.large_orders.length === 0 ? (
            <p className="muted small">No large order yet.</p>
          ) : data.large_orders.map((o, i) => (
            <div key={i} className="row">
              <span>
                <span className={o.side === "buy" ? "change-up" : "change-down"}>{o.side === "buy" ? "▲ Buy" : "▼ Sell"}</span>{" "}
                {count(o.quantity)} <a href={`#/companies/${o.ticker}`}>{o.name}</a>
              </span>
              <span className="mono">{formatCompact(o.value_kobo)} · {formatLagosTime(new Date(o.shown_at))}</span>
            </div>
          ))}
        </Panel>
      )}
      {bell && (
        <Panel title="The Closing Bell" aside={`Trading day of ${shortDate(bell.session_date)}`}>
          <div className="tiles">
            <div className="tile">
              <div className="muted small">BSX 50 at the close</div>
              <div className="mono figure-small">{bell.index.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
              <div className="small"><Change bps={bell.index_change_bps} /> <span className="muted">on the day</span></div>
            </div>
            {bell.winner && bell.winner.change_bps > 0 && (
              <div className="tile">
                <div className="muted small">Biggest winner</div>
                <div className="strong"><a href={`#/companies/${bell.winner.ticker}`}>{bell.winner.name}</a></div>
                <div className="small"><Change bps={bell.winner.change_bps} /> <span className="mono">{formatNaira(bell.winner.close_kobo)}</span></div>
              </div>
            )}
            {bell.loser && bell.loser.change_bps < 0 && (
              <div className="tile">
                <div className="muted small">Biggest loser</div>
                <div className="strong"><a href={`#/companies/${bell.loser.ticker}`}>{bell.loser.name}</a></div>
                <div className="small"><Change bps={bell.loser.change_bps} /> <span className="mono">{formatNaira(bell.loser.close_kobo)}</span></div>
              </div>
            )}
            <div className="tile">
              <div className="muted small">Shares up and down</div>
              <div className="mono figure-small">▲ {bell.risers} · ▼ {bell.fallers}</div>
              <div className="small muted">of those that traded</div>
            </div>
          </div>
          <ul className="reasons">
            {bell.lines.filter((line) => !line.startsWith("Biggest")).map((line) => <li key={line}>{line}</li>)}
          </ul>
          {!brief && bell.stories.length > 0 && (
            <>
              <div className="why-title">The day’s main stories</div>
              <ul className="reasons">{bell.stories.map((story) => <li key={story}>{story}</li>)}</ul>
            </>
          )}
          <div className="why-title">Market advisory</div>
          <ul className="reasons">{bell.advisory.map((line) => <li key={line}>{line}</li>)}</ul>
          <div className="why-title">NEXT</div>
          <p className="small">{bell.next}</p>
        </Panel>
      )}
    </>
  );
}
