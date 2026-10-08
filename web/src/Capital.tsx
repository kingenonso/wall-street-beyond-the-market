import { useState } from "react";
import { api, ApiError, type Bond, type BondHolding, type Corporate, type Offer, type Takeover, type Vote } from "./api";
import { formatCompact, formatNaira, formatPercent } from "./format";
import { useLoad } from "./hooks";
import { Change, Failed, Loading, Panel, Rating } from "./Shell";

const count = (n: number) => n.toLocaleString("en-NG");
const message = (failure: unknown) => (failure instanceof ApiError ? failure.message : "Could not reach the server.");
const wholeNumber = (text: string) => (/^\d+$/.test(text.trim()) ? Number(text.trim()) : null);

/** The yearly return of a bill or bond bought at the desk's selling price and held to the end, roughly. */
function GroupTitle({ children }: { children: string }) {
  return <div className="why-title" style={{ marginTop: 14 }}>{children}</div>;
}

function BondLine({ bond, mine, deskOpen, onDone }: { bond: Bond; mine?: BondHolding; deskOpen: boolean; onDone: (text: string) => void }) {
  const [units, setUnits] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const wanted = wholeNumber(units);
  const canBuy = bond.kind === "bill" || deskOpen;

  async function act(what: "buy" | "sell" | "swap") {
    if (!wanted) return setProblem("Type a whole number of bonds.");
    setBusy(true);
    setProblem(null);
    try {
      if (what === "swap") {
        await api.swapBond(bond.code, wanted);
        onDone(`${count(wanted)} of ${bond.name} will be swapped for ${count(wanted * (bond.conversion_shares ?? 0))} shares when the quarter closes.`);
      } else {
        const done = await api.tradeBond(bond.code, what, wanted);
        onDone(`${what === "buy" ? "Bought" : "Sold"} ${count(done.units)} of ${done.name} at ${formatNaira(done.price_kobo)} each: ${formatNaira(done.value_kobo)} in all.`);
      }
      setUnits("");
    } catch (failure) {
      setProblem(message(failure));
    }
    setBusy(false);
  }

  return (
    <div className="bond">
      <div className="bond-head">
        <div>
          <div className="strong">{bond.name}</div>
          <div className="small muted">
            <span className="bond-kind">{bond.kind_label}</span>
            {bond.rating && <> · <Rating value={bond.rating} /></>}
            {bond.ticker && <> · <a href={`#/companies/${bond.ticker}`}>{bond.issuer}</a></>}
            {" "}· repaid at {formatNaira(bond.face_kobo)} at the end of {bond.maturity_label}
          </div>
          <div className="small">{bond.pays}.
            {bond.conversion_shares && ` Each can be swapped for ${count(bond.conversion_shares)} shares.`}
            {bond.project && ` Raised for ${bond.project}.`}
            {bond.distressed && " Its issuer is in trouble: investors no longer count on being repaid in full."}
          </div>
        </div>
        <div className="bond-prices">
          <div><span className="muted small">Fair value</span> <span className="mono">{formatNaira(bond.fair_kobo)}</span></div>
          <div><span className="muted small">You buy at</span> <span className="mono strong">{formatNaira(bond.ask_kobo)}</span></div>
          <div><span className="muted small">You sell at</span> <span className="mono strong">{formatNaira(bond.bid_kobo)}</span></div>
          <div><span className="muted small">Yearly return wanted</span> <span className="mono">{formatPercent(bond.yield_bps, 2)}</span></div>
        </div>
      </div>
      {mine && (
        <div className="small bond-mine">
          You hold <span className="mono strong">{count(mine.units)}</span>, worth {formatNaira(mine.value_kobo)}
          {BigInt(mine.cost_kobo) > 0n && <> (cost {formatNaira(mine.cost_kobo)})</>}
          {mine.held_for_swap > 0 && <>; {count(mine.held_for_swap)} waiting to be swapped for shares</>}.
        </div>
      )}
      <div className="bond-form">
        <label className="small">How many{" "}
          <input inputMode="numeric" value={units} onChange={(e) => setUnits(e.target.value)} placeholder="0" aria-label={`How many of ${bond.name}`} />
        </label>
        <button className="button-outline" disabled={busy || !canBuy} onClick={() => act("buy")}>Buy</button>
        <button className="button-quiet" disabled={busy || !deskOpen || !mine} onClick={() => act("sell")}>Sell</button>
        {bond.kind === "convertible" && <button className="button-quiet" disabled={busy || !mine} onClick={() => act("swap")}>Swap for shares</button>}
        <span className="small muted">
          {wanted ? `${count(wanted)} cost ${formatNaira((BigInt(bond.ask_kobo) * BigInt(wanted)).toString())}` : ""}
          {bond.on_offer !== null && ` · ${count(bond.on_offer)} on offer`}
        </span>
      </div>
      {problem && <div className="error" role="alert">{problem}</div>}
    </div>
  );
}

const GROUPS: [string, (b: Bond) => boolean, string][] = [
  ["GOVERNMENT BILLS", (b) => b.kind === "bill", "A three-month loan to the Government. The safest place for cash you do not need for a few weeks."],
  ["GOVERNMENT BONDS", (b) => b.issuer === "Federal Government" && b.kind !== "bill", "Longer loans to the Government. Their prices fall when interest rates rise, and rise when rates fall; the longer the bond, the more."],
  ["COMPANY BONDS", (b) => b.issuer !== "Federal Government", "Loans to companies. They pay more than the Government's because a company can fail to repay."],
];

export function BondsWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const desk = useLoad(api.bonds, "bonds", onLoggedOut);
  const [done, setDone] = useState<string | null>(null);
  if (desk.loading && !desk.data) return <Loading what="the bond desk" />;
  if (desk.error) return <Failed message={desk.error} onRetry={desk.reload} />;
  if (!desk.data) return null;
  const d = desk.data;
  const mine = new Map(d.holdings.map((h) => [h.code, h]));
  const finished = (text: string) => { setDone(text); desk.reload(); onChanged(); };

  return (
    <>
      <Panel title="Bonds and bills" aside={d.desk_open ? "The bond desk is open" : "The bond desk is closed: bills can still be bought"}>
        <p className="small">
          A bond is a loan you can buy and sell. Whoever holds it is paid the interest each quarter, and ₦1,000 for each bond at
          the end. You trade with the pension funds' bond desk, at its prices. Every bond shows two prices: its fair value,
          worked out in the open, and what the desk will actually sell and buy it for.
        </p>
        {done && <div className="notice" role="status">{done}</div>}
        {d.holdings.length > 0 && (
          <p className="small">
            You hold {d.holdings.length} kind{d.holdings.length === 1 ? "" : "s"} of bond, worth{" "}
            <span className="mono strong">{formatNaira(d.holdings.reduce((sum, h) => sum + BigInt(h.value_kobo), 0n).toString())}</span>.
            Interest received so far: <span className="mono">{formatNaira(d.income_kobo)}</span>.
          </p>
        )}
        {d.swaps.map((s) => (
          <div key={s.id} className="order-line">
            <span>{count(s.units)} of {s.name} waiting to become {count(s.shares)} shares when the quarter closes</span>
            <button className="button-quiet" onClick={async () => { await api.cancelSwap(s.id).catch(() => undefined); desk.reload(); }}>Cancel</button>
          </div>
        ))}
        {GROUPS.map(([title, belongs, words]) => {
          const rows = d.bonds.filter(belongs);
          if (rows.length === 0) return null;
          return (
            <div key={title}>
              <GroupTitle>{title}</GroupTitle>
              <p className="small muted">{words}</p>
              {rows.map((bond) => <BondLine key={bond.code} bond={bond} mine={mine.get(bond.code)} deskOpen={d.desk_open} onDone={finished} />)}
            </div>
          );
        })}
      </Panel>

      <Panel title="The yield curve" aside={`The Central Bank's rate is ${formatPercent(d.policy_rate_bps, 2)}`}>
        <p className="small muted">The yearly return investors want for lending to the Government, by length of loan.</p>
        <div className="tiles">
          {d.curve.map((p) => (
            <div key={p.label} className="tile">
              <div className="muted small">{p.label}</div>
              <div className="mono figure-small">{formatPercent(p.yield_bps, 2)}</div>
            </div>
          ))}
        </div>
        <GroupTitle>CREDIT SPREADS</GroupTitle>
        <p className="small muted">The extra yearly return wanted for lending to a company, by its credit rating.</p>
        <div className="spreads">
          {d.spreads.map((s) => <span key={s.rating} className="spread"><Rating value={s.rating} /> <span className="mono">+{formatPercent(s.spread_bps, 1)}</span></span>)}
        </div>
      </Panel>
    </>
  );
}

function NumberAction({ label, start, button, onSubmit }: { label: string; start: number; button: string; onSubmit: (n: number) => Promise<void> }) {
  const [text, setText] = useState(start ? String(start) : "");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  async function go() {
    const n = wholeNumber(text || "0");
    if (n === null) return setProblem("Type a whole number.");
    setBusy(true);
    setProblem(null);
    try { await onSubmit(n); } catch (failure) { setProblem(message(failure)); }
    setBusy(false);
  }
  return (
    <>
      <div className="bond-form">
        <label className="small">{label}{" "}
          <input inputMode="numeric" value={text} onChange={(e) => setText(e.target.value)} placeholder="0" />
        </label>
        <button className="button-outline" disabled={busy} onClick={go}>{button}</button>
      </div>
      {problem && <div className="error" role="alert">{problem}</div>}
    </>
  );
}

function OfferCard({ offer, update }: { offer: Offer; update: (c: Corporate) => void }) {
  const open = offer.status === "open";
  const title = { ipo: "First sale of shares to the public", public: "Sale of new shares", rights: "Rights issue" }[offer.kind];
  return (
    <div className="bond">
      <div className="strong"><a href={`#/companies/${offer.ticker}`}>{offer.name}</a>: {title}</div>
      <div className="small">
        {count(offer.shares)} new shares at <span className="mono strong">{formatNaira(offer.price_kobo)}</span> each
        {offer.kind === "rights" && `, ${offer.rights_new} new for every ${offer.rights_held} you hold when the offer closes`}. {offer.reason}
        {offer.needs_vote && " It goes ahead only if shareholders vote for it."}
      </div>
      {open ? (
        <>
          <div className="small muted">Closes {offer.closes_label}. The cash for your application is held until then; whatever is not used comes back.</div>
          {offer.asked > 0 && <div className="small bond-mine">You have applied for {count(offer.asked)} shares; {formatNaira(offer.held_kobo)} is held.</div>}
          <NumberAction label="Shares to apply for (0 withdraws)" start={offer.asked} button="Apply"
                        onSubmit={async (n) => update(await api.applyForShares(offer.id, n))} />
        </>
      ) : (
        <div className="small muted">{offer.outcome}{offer.allotted !== null && offer.allotted > 0 && ` You were allotted ${count(offer.allotted)}.`}</div>
      )}
    </div>
  );
}

function VoteCard({ vote, update }: { vote: Vote; update: (c: Corporate) => void }) {
  const [problem, setProblem] = useState<string | null>(null);
  const open = vote.status === "open";
  const cast = async (choice: "for" | "against") => {
    setProblem(null);
    try { update(await api.castVote(vote.id, choice)); } catch (failure) { setProblem(message(failure)); }
  };
  const total = (vote.votes_for ?? 0) + (vote.votes_against ?? 0);
  return (
    <div className="bond">
      <div className="strong"><a href={`#/companies/${vote.ticker}`}>{vote.name}</a>: shareholders' vote</div>
      <div className="small strong">{vote.question}</div>
      <div className="small">{vote.explanation} The board recommends voting {vote.board}.</div>
      {open ? (
        <>
          <div className="small muted">
            Counted {vote.closes_label}. Your vote counts for the shares you hold at that moment
            {vote.my_shares > 0 ? `: ${count(vote.my_shares)} today.` : ". You hold none today."}
          </div>
          <div className="bond-form">
            <button className={vote.my_choice === "for" ? "button-primary" : "button-outline"} aria-pressed={vote.my_choice === "for"} onClick={() => cast("for")}>▲ Vote for</button>
            <button className={vote.my_choice === "against" ? "button-primary" : "button-outline"} aria-pressed={vote.my_choice === "against"} onClick={() => cast("against")}>▼ Vote against</button>
            {vote.my_choice && <span className="small muted">You have voted {vote.my_choice}. You can change it until the count.</span>}
          </div>
          {problem && <div className="error" role="alert">{problem}</div>}
        </>
      ) : (
        <div className="small">
          <span className="strong">{vote.status === "passed" ? "Approved" : "Rejected"}</span>
          {total > 0 && `: ${formatPercent(Math.floor(((vote.votes_for ?? 0) * 10000) / total))} of votes cast in favour.`}
          {vote.tally && (
            <span className="muted"> {Object.entries(vote.tally).map(([who, t]) =>
              `${who}: ${t.for >= t.against ? "mostly for" : "mostly against"}`).join(" · ")}</span>
          )}
        </div>
      )}
    </div>
  );
}

function TakeoverCard({ bid, update }: { bid: Takeover; update: (c: Corporate) => void }) {
  const open = bid.status === "open";
  return (
    <div className="bond">
      <div className="strong">
        {bid.bidder_ticker ? <a href={`#/companies/${bid.bidder_ticker}`}>{bid.bidder}</a> : <span>{bid.bidder} (an empire)</span>} offers for <a href={`#/companies/${bid.ticker}`}>{bid.target}</a>{" "}
        <span className={bid.hostile ? "pill pill-test" : "pill pill-open"}>{bid.hostile ? "Hostile: the board rejected it" : "Agreed: the board recommends it"}</span>
      </div>
      <div className="small">
        <span className="mono strong">{formatNaira(bid.price_kobo)}</span> for each share, <Change bps={bid.premium_bps} /> above the market price when it was made
        {bid.market_price_kobo && <> (the share now trades at {formatNaira(bid.market_price_kobo)})</>}, for up to {count(bid.shares_sought)} shares.
        It succeeds only if owners of more than half the shares accept.{bid.needs_vote && " The bidder's own shareholders must also approve."}
      </div>
      {open ? (
        <>
          <div className="small muted">
            Closes {bid.closes_label}. Shares you offer are held until then. If the offer fails, or more are offered than the bidder
            wants, they come back to you.
          </div>
          {bid.offered > 0 && <div className="small bond-mine">You have offered {count(bid.offered)} shares, worth {formatCompact((BigInt(bid.price_kobo) * BigInt(bid.offered)).toString())} at the offer price.</div>}
          <NumberAction label={`Shares to offer (you hold ${count(bid.free + bid.offered)}; 0 takes them back)`} start={bid.offered} button="Offer my shares"
                        onSubmit={async (n) => update(await api.answerTakeover(bid.id, n))} />
        </>
      ) : (
        <div className="small"><span className="strong">{bid.status === "won" ? "Succeeded." : "Failed."}</span> {bid.outcome}</div>
      )}
    </div>
  );
}

export function CorporateWork({ onLoggedOut, onChanged }: { onLoggedOut: () => void; onChanged: () => void }) {
  const loaded = useLoad(api.corporate, "corporate", onLoggedOut);
  const [fresh, setFresh] = useState<Corporate | null>(null);
  if (loaded.loading && !loaded.data) return <Loading what="offers, votes and bids" />;
  if (loaded.error) return <Failed message={loaded.error} onRetry={loaded.reload} />;
  const c = fresh ?? loaded.data;
  if (!c) return null;
  const update = (next: Corporate) => { setFresh(next); onChanged(); };
  const nothing = c.offers.length + c.votes.length + c.takeovers.length === 0;
  return (
    <>
      <Panel title="Offers, votes and bids" aside="Announced as one quarter closes, settled as the next one closes">
        {nothing && <p className="muted">Nothing is open. Companies announce share offers, votes and takeover offers when a quarter's results are filed.</p>}
        {c.takeovers.length > 0 && <GroupTitle>TAKEOVER OFFERS</GroupTitle>}
        {c.takeovers.map((bid) => <TakeoverCard key={bid.id} bid={bid} update={update} />)}
        {c.offers.length > 0 && <GroupTitle>NEW SHARES ON OFFER</GroupTitle>}
        {c.offers.map((offer) => <OfferCard key={offer.id} offer={offer} update={update} />)}
        {c.votes.length > 0 && <GroupTitle>SHAREHOLDERS' VOTES</GroupTitle>}
        {c.votes.map((vote) => <VoteCard key={vote.id} vote={vote} update={update} />)}
      </Panel>

      {c.integrations.length > 0 && (
        <Panel title="After a takeover: joining the two businesses" aside="▲ green: costs saved · ▼ red: extra costs">
          {c.integrations.map((i) => (
            <div key={i.ticker} className="bond">
              <div className="strong"><a href={`#/companies/${i.ticker}`}>{i.target}</a>, now controlled by {i.bidder}</div>
              <div className="small muted">The plan: costs lower by {formatPercent(i.planned_saving_bps)} of sales, over {i.quarters} quarters.</div>
              {i.done.map((q) => (
                <div key={q.label} className="row">
                  <span><span className="mono">{q.label}</span> {q.notes.join(" ")}</span>
                  <span className={q.cost_bps <= 0 ? "change-up mono" : "change-down mono"}>
                    {q.cost_bps <= 0 ? `▲ ${formatPercent(Math.abs(q.cost_bps))} of sales saved` : `▼ ${formatPercent(Math.abs(q.cost_bps))} of sales in extra costs`}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </Panel>
      )}

      <Panel title="Notices from the exchange" aside="Newest first">
        {c.notices.length === 0 && <p className="muted small">No notices yet.</p>}
        {c.notices.map((n, i) => (
          <div key={i} className="news-line">
            <div className="small muted">{n.period_label}{n.ticker && <> · <a href={`#/companies/${n.ticker}`}>{n.ticker}</a></>}</div>
            <div className="strong">{n.title}</div>
            <div className="small">{n.body}</div>
          </div>
        ))}
      </Panel>
    </>
  );
}

export function OwnershipWork({ onLoggedOut }: { onLoggedOut: () => void }) {
  const loaded = useLoad(api.ownership, "ownership", onLoggedOut);
  if (loaded.loading && !loaded.data) return <Loading what="who owns what" />;
  if (loaded.error) return <Failed message={loaded.error} onRetry={loaded.reload} />;
  const rows = loaded.data ?? [];
  const controlled = rows.filter((r) => r.controller);
  return (
    <Panel title="Who owns what" aside="Whoever holds more than half a company's shares controls it">
      <p className="small">
        {controlled.length === 0 ? "No company has a controlling owner today." :
          `${controlled.length} of ${rows.length} companies have a controlling owner.`} A single player's holding is never listed.
      </p>
      <div className="scroll">
        <table>
          <thead><tr><th scope="col">Company</th><th scope="col">Control</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker}>
                <th scope="row"><a href={`#/companies/${r.ticker}`}>{r.name}</a> <span className="ticker mono">{r.ticker}</span></th>
                <td className="small">{r.controller ? <span className="strong">{r.summary}</span> : <span className="muted">{r.summary}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
