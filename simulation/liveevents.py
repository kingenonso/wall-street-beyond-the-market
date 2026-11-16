"""Live events, part 1 (owner, 16 November 2026): moments for the empires to compete in.

Three times a week (Monday, Wednesday and Friday at 20:00, Lagos time) something happens in the shared world, at once for
everybody, and for thirty minutes every empire competes on how it reads and handles it. The market is open, so it is
played in the real market with real money; results are permanent.

Five kinds, each a real thing in the world with a real effect, chosen at the bell from the world's secret so nobody can
know which is coming, or whom it strikes:

  fraud      A listed company is found to have cooked its books. A scandal in the world's quarter (its sales this quarter
             fall, and its accounts will show it), and investors mark the share down.
  oil_spike  The price of energy jumps across the country. Oil and gas companies gain; those that burn fuel lose.
  bank_run   Savers hear that a bank is in trouble. Their trust in it falls for some days, so they really do take their
             money out (the crisis desk works that out, day by day), and its share is marked down.
  rate_move  The Central Bank makes an emergency move: its next rate will be a point higher (inflation above its target)
             or a point lower. Banks and borrowers are marked up or down at once; the rate itself changes at the close.
  takeover   A company makes a bid for another, paid from cash it has to spare. The bid then runs as any other does.

How investors take it: those who read the news at once mark the shares it touches up or down within minutes; the
institutions a day later; the founders not at all. The mark fades over a few trading days.

Scoring, when the thirty minutes end:

  The prediction   Every member of an empire run by players may seal a prediction of their own of how far the featured
                   share will move from the bell to the end, in the first ten minutes; the empire's closest counts. The
                   closest three empires earn 10, 6 and 3 league points, if they missed by no more than five points and
                   at least two empires predicted.
  The money        What the event did to each empire's money: the shares it touched, held and traded in the window,
                   against what the empire was worth at the bell (so a small empire can beat a big one). The best three
                   that made money earn 10, 6 and 3.
  Taking part      An empire run by players that predicted, traded the touched shares, or whose standing plan acted: 2.

Computer-run empires are in the field too: they predict from what an analyst could see, and whatever they hold is
scored as it stands.

A head may leave a standing plan for members who cannot be there: hold, cut (sell half of any holding the news hurts),
buy the fall, or ride a rise, with a budget. It is carried out at the bell by the head's own authority, inside every
limit an order from the head would meet.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, clock, empires, events, exchange, leagues, news, pings
from simulation import world_data as data
from simulation.money import BPS

KINDS = {
    "fraud": "Fraud Uncovered",
    "oil_spike": "Fuel Crisis",
    "bank_run": "Bank Run",
    "rate_move": "Emergency Rate Move",
    "takeover": "Takeover Battle",
}
PLANS = {
    "hold": "Hold: do nothing until somebody is there",
    "cut": "Cut: sell half of any holding the news hurts",
    "buy_the_fall": "Buy the fall: buy the featured share if the news hurts it, up to the budget",
    "ride": "Ride the rise: buy the featured share if the news helps it, up to the budget",
}


class LiveEventError(Exception):
    """A request the rules refuse, in words for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('live_events') IS NOT NULL AND EXISTS (SELECT 1 FROM world_state) AS ok")["ok"])


def _unit(seed: str, *key) -> float:
    """A number from 0 up to 1, fixed by the world's secret and the key: unknowable outside the server."""
    digest = hashlib.sha256(f"{seed}:live:{':'.join(str(k) for k in key)}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _between(seed: str, low: int, high: int, *key) -> int:
    return low + round(_unit(seed, *key) * (high - low))


def _pct(bps: int) -> str:
    return f"{bps / 100:+.1f}%"


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


# ---------------------------------------------------------------------------
# The timetable
# ---------------------------------------------------------------------------

def _slot_on(day) -> datetime:
    return datetime(day.year, day.month, day.day, data.LIVE_EVENT_HOUR, 0, tzinfo=clock.LAGOS)


def slot_now(now: datetime) -> datetime | None:
    """The bell of the event running at `now` (from the bell to its end), if one is."""
    lagos = clock.to_lagos(now)
    if lagos.weekday() not in data.LIVE_EVENT_DAYS:
        return None
    bell = _slot_on(lagos.date())
    return bell if bell <= lagos < bell + timedelta(minutes=data.LIVE_EVENT_MINUTES) else None


def next_slot(now: datetime) -> datetime:
    """The next bell after `now`."""
    lagos = clock.to_lagos(now)
    for ahead in range(8):
        day = (lagos + timedelta(days=ahead)).date()
        if day.weekday() in data.LIVE_EVENT_DAYS and _slot_on(day) > lagos:
            return _slot_on(day)
    raise AssertionError("There is always a bell within a week.")


# ---------------------------------------------------------------------------
# What the market says
# ---------------------------------------------------------------------------

def _price(conn: Connection, company_id) -> int:
    row = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s", (company_id,))
    return row["p"] if row else 0


def _price_at(conn: Connection, company_id, moment: datetime, fallback: int) -> int:
    """The last price paid for a share at or before `moment` (and after the bell the caller gives as `fallback`)."""
    row = _one(conn, "SELECT price FROM market_trades WHERE company_id = %s AND traded_at <= %s ORDER BY traded_at DESC, id DESC LIMIT 1",
               (company_id, moment))
    return row["price"] if row else fallback


def _held(conn: Connection, account, share_asset: str) -> int:
    row = _one(conn, "SELECT balance FROM ledger_balances WHERE account_id = %s AND asset = %s", (account, share_asset))
    return max(row["balance"], 0) if row else 0


def _listed(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT c.id, c.ticker, c.name, c.sector, c.headquarters, c.share_asset, c.account_id,"
                       " coalesce(m.last_price, m.reference_price) AS price FROM companies c"
                       " JOIN market_instruments m ON m.company_id = c.id WHERE c.listed AND m.halted_reason IS NULL ORDER BY c.ticker")


def _market_value(conn: Connection, company: dict) -> int:
    from simulation import ledger
    return company["price"] * ledger.amount_in_existence(conn, company["share_asset"])


# ---------------------------------------------------------------------------
# The bell: choosing and making it happen
# ---------------------------------------------------------------------------

def _field(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id")


def _held_by_players(conn: Connection, listed: list[dict]) -> set:
    """Companies some player-run empire holds: the drama is where the players are."""
    held = set()
    for e in _rows(conn, "SELECT account_id FROM empires WHERE status = 'active' AND kind = 'player'"):
        for c in listed:
            if _held(conn, e["account_id"], c["share_asset"]) > 0:
                held.add(c["id"])
    return held


def _pick(seed: str, key: str, options: list):
    return min(options, key=lambda o: _unit(seed, key, o["ticker"])) if options else None


def _plan_kind(conn: Connection, seed: str, bell: datetime) -> list[str]:
    """The kinds, in the order to try them for this bell: never the same kind twice in a row."""
    last = _one(conn, "SELECT kind FROM live_events WHERE starts_at < %s ORDER BY starts_at DESC LIMIT 1", (bell,))
    order = sorted(KINDS, key=lambda k: _unit(seed, bell.isoformat(), "kind", k))
    if last and order[0] == last["kind"]:
        order = order[1:] + order[:1]
    return order


def _touch(company: dict, bps: int) -> dict:
    return {"company_id": str(company["id"]), "ticker": company["ticker"], "name": company["name"], "bps": bps}


def _world_event(conn: Connection, period: int, day: int, kind: str, company: dict | None, seed: str, key: str) -> dict:
    """Add the event to the world's quarter, so it is in the companies' accounts when the quarter closes."""
    spec = events.BY_NAME[kind]
    def pick(span, what):
        return _between(seed, span[0], span[1], key, kind, what) if span != (0, 0) else 0
    event = {"period": period, "day": day, "kind": kind, "location": company["headquarters"] if company else None, "sector": None,
             "company_id": company["id"] if company else None, "sales_bps": pick(spec.sales, "sales"), "cost_bps": pick(spec.cost, "cost"),
             "damage_bps": pick(spec.damage, "damage"), "mood_bps": pick(spec.mood, "mood"), "commodity": spec.commodity,
             "price_bps": pick(spec.price, "price"), "severe": spec.severe,
             "facts": ({"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"]} if company else {})}
    columns = list(event)
    from simulation import ledger
    event["id"] = ledger._first(conn.execute(f"INSERT INTO events ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) RETURNING id",
                                             [Jsonb(v) if c == "facts" else v for c, v in event.items()]).fetchone())
    news.for_events(conn, [event])
    return event


def _fraud(conn, seed, key, listed, held, period, day):
    candidates = [c for c in listed if c["sector"] not in events.FINANCIAL and c["price"] >= 100]
    target = _pick(seed, key + ":fraud", [c for c in candidates if c["id"] in held] or candidates)
    if target is None:
        return None
    happened = _world_event(conn, period, day, "scandal", target, seed, key)
    return {"featured": target, "touched": [_touch(target, -data.LIVE_SHOCK_BPS["fraud"])], "world_event_id": happened["id"],
            "headline": f"Fraud uncovered at {target['name']}",
            "story": (f"Investigators have found that {target['name']} ({target['ticker']}) has been overstating its sales. Its customers "
                      f"are leaving: its sales this quarter will be {abs(happened['sales_bps']) / 100:.0f}% lower than they would have "
                      "been, and its accounts will show it at the close. Investors who read the news at once are marking the share down.")}


def _oil(conn, seed, key, listed, held, period, day):
    oil = [c for c in listed if c["sector"] == "oil_gas"]
    if not oil:
        return None
    featured = max(oil, key=lambda c: (_market_value(conn, c), c["ticker"]))
    happened = _world_event(conn, period, day, "energy_price_jump", None, seed, key)
    gain, loss = data.LIVE_SHOCK_BPS["oil_gain"], data.LIVE_SHOCK_BPS["oil_loss"]
    touched = [_touch(c, gain) for c in oil] + [_touch(c, -loss) for c in listed if c["sector"] in data.LIVE_FUEL_USERS]
    return {"featured": featured, "touched": touched, "world_event_id": happened["id"],
            "headline": f"Fuel crisis: energy prices jump {happened['price_bps'] / 100:.0f}%",
            "story": (f"The price of energy has jumped {happened['price_bps'] / 100:.0f}% across the country. Oil and gas companies will "
                      "earn more on every barrel; airlines, shippers, transport firms, factories and cement makers will pay more for "
                      f"fuel. Investors are marking them up and down. Watch {featured['name']} ({featured['ticker']}).")}


def _bank_run(conn, seed, key, listed, held, period, day):
    banks = [c for c in listed if c["sector"] == "banking"]
    target = _pick(seed, key + ":bank", [c for c in banks if c["id"] in held] or banks)
    if target is None:
        return None
    touched = [_touch(target, -data.LIVE_SHOCK_BPS["bank_run"])] + [
        _touch(c, -data.LIVE_SHOCK_BPS["other_banks"]) for c in banks if c["id"] != target["id"]]
    return {"featured": target, "touched": touched,
            "headline": f"Queues outside {target['name']}",
            "story": (f"Word is going round that {target['name']} ({target['ticker']}) is in trouble, and savers are queuing to take their "
                      f"money out. Their trust in the bank has fallen for the next {data.LIVE_RUN_GAME_DAYS} days: watch the crisis "
                      "desk for how much leaves each day, and whether the Central Bank steps in. Its share and other banks' are "
                      "being marked down.")}


def _rate(conn, seed, key, listed, held, period, day):
    row = _one(conn, "SELECT inflation_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    hike = bool(row) and row["inflation_bps"] > data.INFLATION_TARGET_BPS
    move = data.LIVE_RATE_MOVE_BPS if hike else -data.LIVE_RATE_MOVE_BPS
    sign = 1 if hike else -1
    banks = [c for c in listed if c["sector"] == "banking"]
    borrowers = [c for c in listed if c["sector"] in data.LIVE_RATE_BORROWERS]
    touched = [_touch(c, sign * data.LIVE_SHOCK_BPS["rate_banks"]) for c in banks] + \
              [_touch(c, -sign * data.LIVE_SHOCK_BPS["rate_borrowers"]) for c in borrowers]
    pool = borrowers or banks
    if not pool:
        return None
    featured = max(pool, key=lambda c: (_market_value(conn, c), c["ticker"]))
    inflation = f"{row['inflation_bps'] / 100:.1f}%" if row else "unknown"
    return {"featured": featured, "touched": touched, "rate_bps": move,
            "headline": f"Emergency move: the Central Bank {'raises' if hike else 'cuts'} its rate by {abs(move) / 100:.0f} point",
            "story": (f"In an emergency meeting the Central Bank has decided that its rate will be {abs(move) / 100:.0f} point "
                      f"{'higher' if hike else 'lower'} than its rule would set, from the quarter's close: inflation is {inflation}, "
                      f"against its target of {data.INFLATION_TARGET_BPS / 100:.0f}%. "
                      + ("Banks earn more on their loans; builders, property and cement companies, who borrow, lose. "
                         if hike else "Borrowing gets cheaper: builders, property and cement companies gain; banks earn less on their loans. ")
                      + f"Watch {featured['name']} ({featured['ticker']}).")}


def _takeover(conn, seed, key, listed, held, period, day, now):
    """A company makes a bid, from cash it has to spare (no borrowing in the middle of a quarter)."""
    from simulation import corporate
    closed = period - 1
    results = {r["company_id"]: r for r in _rows(conn, "SELECT * FROM company_results WHERE period = %s", (closed,))}
    shares = {r["company_id"]: r["shares_in_issue"] for r in _rows(
        conn, "SELECT DISTINCT ON (company_id) company_id, shares_in_issue FROM company_valuations ORDER BY company_id, period DESC")}
    ratings = {r["company_id"]: r["credit_rating"] for r in _rows(
        conn, "SELECT DISTINCT ON (company_id) company_id, credit_rating FROM company_reports ORDER BY company_id, period DESC, version DESC")}
    pairs = [(c, {**results[c["id"]], "shares_in_issue": shares[c["id"]]}) for c in listed if c["id"] in results and c["id"] in shares]
    prices = {c["id"]: c["price"] for c, _ in pairs}
    busy = corporate._busy(conn)
    targets = sorted((c for c, _ in pairs if c["id"] not in busy), key=lambda c: (c["id"] not in held, _unit(seed, key, "target", c["ticker"])))
    for target in targets[:12]:
        corporate._propose_takeover(conn, closed, seed, now, pairs, ratings, prices, set(busy), {}, 0, only_target=target["id"])
        bid = _one(conn, "SELECT * FROM takeovers WHERE target_company_id = %s AND status = 'open' AND opens_period = %s", (target["id"], closed))
        if bid is None:
            continue
        bidder = next(c for c, _ in pairs if c["id"] == bid["bidder_company_id"])
        return {"featured": target, "touched": [_touch(target, 0), _touch(bidder, -data.LIVE_SHOCK_BPS["bidder"])], "takeover_id": bid["id"],
                "headline": f"{bidder['name']} bids for {target['name']}",
                "story": (f"{bidder['name']} ({bidder['ticker']}) has offered {_naira(bid['price'])} a share for "
                          f"{bid['shares_sought'] * BPS // max(shares[target['id']], 1) / 100:.0f}% of {target['name']} ({target['ticker']}), "
                          f"{bid['premium_bps'] / 100:.0f}% above the market price"
                          + (", over its board's head" if bid["hostile"] else ", with its board's blessing")
                          + ". The offer closes when the quarter closes; owners of more than half the shares must accept. The target's "
                          "price has jumped to what a share is worth if the bid succeeds. Will it hold? The bidder is being marked down "
                          "for what it is paying.")}
    return None


def open_event(conn: Connection, bell: datetime, now: datetime) -> dict | None:
    """Ring the bell: decide what happens, make it happen, and take a snapshot of every empire. Once for each bell."""
    world = _one(conn, "SELECT fortune_seed FROM world_state")
    state = careers.world_now(conn, now)
    if world is None or not state["started"]:
        return None
    seed = world["fortune_seed"]
    with conn.transaction():
        if _one(conn, "SELECT 1 AS x FROM live_events WHERE starts_at = %s FOR UPDATE", (bell,)):
            return None
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('live_event_bell'))")
        if _one(conn, "SELECT 1 AS x FROM live_events WHERE starts_at = %s", (bell,)):
            return None
        listed = _listed(conn)
        if len(listed) < 2:
            return None
        held = _held_by_players(conn, listed)
        key = bell.isoformat()
        made, kind = None, None
        for kind in _plan_kind(conn, seed, bell):
            with conn.transaction():          # a kind that cannot happen today leaves nothing behind
                if kind == "takeover":
                    made = _takeover(conn, seed, key, listed, held, state["period"], state["day"], now)
                else:
                    made = {"fraud": _fraud, "oil_spike": _oil, "bank_run": _bank_run, "rate_move": _rate}[kind](
                        conn, seed, key, listed, held, state["period"], state["day"])
            if made:
                break
        if not made:
            return None
        featured = made["featured"]
        day = exchange.session_of(now)[0]
        # The prices at the bell, once the news is out (a bid's target has already been repriced).
        for t in made["touched"]:
            t["price"] = _price(conn, t["company_id"])
        event = _one(conn, (
            "INSERT INTO live_events (starts_at, ends_at, predict_until, kind, period, day, featured_company_id, start_price, rate_bps,"
            " world_event_id, takeover_id, headline, story, touched) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING *"),
            (bell, bell + timedelta(minutes=data.LIVE_EVENT_MINUTES), bell + timedelta(minutes=data.LIVE_PREDICT_MINUTES), kind,
             state["period"], state["day"], featured["id"], _price(conn, featured["id"]), made.get("rate_bps", 0),
             made.get("world_event_id"), made.get("takeover_id"), made["headline"], made["story"], Jsonb(made["touched"])))
        for t in made["touched"]:
            if t["bps"]:
                conn.execute("INSERT INTO live_event_shocks (event_id, company_id, bps, session_date, days) VALUES (%s, %s, %s, %s, %s)",
                             (event["id"], t["company_id"], max(min(t["bps"], data.LIVE_SHOCK_MOST_BPS), -data.LIVE_SHOCK_MOST_BPS),
                              day, data.LIVE_SHOCK_DAYS))
        # The field at the bell: every empire, what it was worth and what it held of the shares the event touches.
        assets = {r["id"]: r["share_asset"] for r in _rows(conn, "SELECT id, share_asset FROM companies WHERE id = ANY(%s)",
                                                           ([t["company_id"] for t in made["touched"]],))}
        for e in _field(conn):
            worth = empires.worth(conn, e, now)["total"]
            holding = {str(c): _held(conn, e["account_id"], a) for c, a in assets.items()}
            guess = None
            if e["head_player_id"] is None:
                # A computer-run empire's analyst reads the same news: the direction, and a guess at the size.
                lean = next((t["bps"] for t in made["touched"] if t["company_id"] == str(featured["id"])), 0)
                guess = lean * 6 // 10 + _between(seed, -250, 250, key, "guess", e["id"])
            conn.execute(
                "INSERT INTO live_event_entries (event_id, empire_id, run_by_players, worth_at_bell, held_at_bell, prediction_bps, predicted_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (event["id"], e["id"], e["head_player_id"] is not None, worth, Jsonb({k: v for k, v in holding.items() if v}),
                 guess, now if guess is not None else None))
        news.publish(conn, period=state["period"], day=state["day"], kind="live_event_open", story=f"live:{event['id']}",
                     facts={"show": KINDS[kind], "happening": made["headline"], "detail_line": made["story"].split(". ")[0] + "."},
                     tickers=[t["ticker"] for t in made["touched"]][:4])
    _carry_out_plans(conn, event, now)
    pings.ping(conn, "event")                 # every open screen shows the bell at once
    return event


def _carry_out_plans(conn: Connection, event: dict, now: datetime) -> None:
    """Every head's standing plan, at the bell, by the head's own authority and inside the head's limits."""
    touched = event["touched"]
    featured = next(t for t in touched if t["company_id"] == str(event["featured_company_id"]))
    for plan in _rows(conn, "SELECT p.*, e.head_player_id, e.account_id FROM live_event_plans p JOIN empires e ON e.id = p.empire_id"
                            " WHERE e.status = 'active' AND e.kind = 'player' AND p.plan <> 'hold'"):
        orders = []
        if plan["plan"] == "cut":
            for t in touched:
                if t["bps"] < 0:
                    asset = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (t["company_id"],))["share_asset"]
                    half = _held(conn, plan["account_id"], asset) // 2
                    if half > 0:
                        orders.append(("sell", t, half))
        elif (plan["plan"] == "buy_the_fall" and featured["bps"] < 0) or (plan["plan"] == "ride" and featured["bps"] > 0):
            count = plan["budget"] // max(featured["price"], 1)
            if count > 0:
                orders.append(("buy", featured, count))
        if not orders and plan["plan"] != "hold":
            conn.execute("INSERT INTO live_event_actions (event_id, empire_id, what, done, at) VALUES (%s, %s, %s, false, %s)",
                         (event["id"], plan["empire_id"], f"{PLANS[plan['plan']].split(':')[0]}: nothing to do for this event.", now))
        for side, t, count in orders:
            what = f"{side.capitalize()} {count:,} {t['ticker']} at the best price (the standing plan)"
            try:
                empires.trade_shares(conn, plan["head_player_id"], ticker=t["ticker"], side=side, kind="market", quantity=count,
                                     limit_price=None, now=now)
                done = True
            except (empires.EmpireError, exchange.ExchangeError, careers.CareerError) as refused:
                what, done = f"{what}: refused. {refused}", False
            conn.execute("INSERT INTO live_event_actions (event_id, empire_id, what, done, at) VALUES (%s, %s, %s, %s, %s)",
                         (event["id"], plan["empire_id"], what[:300], done, now))


# ---------------------------------------------------------------------------
# During the event
# ---------------------------------------------------------------------------

def _event(conn: Connection, event_id: int, *, lock: bool = False) -> dict:
    e = _one(conn, "SELECT * FROM live_events WHERE id = %s" + (" FOR UPDATE" if lock else ""), (event_id,))
    if e is None:
        raise LiveEventError("There is no such live event.")
    return e


def predict(conn: Connection, player_id, event_id: int, move_bps: int, now: datetime) -> dict:
    """A member's own sealed prediction of how far the featured share will move from the bell to the end. One each; the
    empire's closest counts."""
    if not isinstance(move_bps, int) or isinstance(move_bps, bool) or not -5_000 <= move_bps <= 5_000:
        raise LiveEventError("Predict a move between −50% and +50%.")
    with conn.transaction():
        event = _event(conn, event_id)
        if not event["starts_at"] <= now < event["predict_until"]:
            raise LiveEventError("Predictions are taken in the first ten minutes after the bell.")
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] != "player":
            raise LiveEventError("Predictions are made by members of an empire run by players. Join one to take part.")
        if _one(conn, "SELECT 1 AS x FROM live_event_entries WHERE event_id = %s AND empire_id = %s", (event_id, seat["empire_id"])) is None:
            raise LiveEventError("Your empire was not in the field at the bell (it joined the league afterwards).")
        done = conn.execute("INSERT INTO live_event_predictions (event_id, player_id, empire_id, move_bps, at) VALUES (%s, %s, %s, %s, %s)"
                            " ON CONFLICT (event_id, player_id) DO NOTHING", (event_id, player_id, seat["empire_id"], move_bps, now)).rowcount
        if not done:
            raise LiveEventError("You have already made your prediction. It is sealed and cannot be changed.")
        pings.ping(conn, "prediction", seat["empire_id"])
    return {"event_id": event_id, "prediction_bps": move_bps}


def set_plan(conn: Connection, player_id, plan: str, budget: int, now: datetime) -> dict:
    if plan not in PLANS:
        raise LiveEventError("That is not a standing plan.")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise LiveEventError("The budget is a sum of money, nought or more.")
    with conn.transaction():
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat["head_player_id"] != player_id:
            raise LiveEventError("Only the head of an empire sets its standing plan.")
        if slot_now(now) is not None:
            raise LiveEventError("An event is running: the plan for it was carried out at the bell. Set the next one after it ends.")
        conn.execute("INSERT INTO live_event_plans (empire_id, plan, budget, set_by, at) VALUES (%s, %s, %s, %s, %s)"
                     " ON CONFLICT (empire_id) DO UPDATE SET plan = EXCLUDED.plan, budget = EXCLUDED.budget, set_by = EXCLUDED.set_by, at = EXCLUDED.at",
                     (seat["empire_id"], plan, budget if plan in ("buy_the_fall", "ride") else 0, player_id, now))
        pings.ping(conn, "plan", seat["empire_id"])
    return {"plan": plan, "budget": budget}


def _results(conn: Connection, event: dict, until: datetime) -> tuple[int, list[dict]]:
    """The featured share's move so far, and each empire's result so far: what the event did to its money."""
    start = event["starts_at"]
    prices = {t["company_id"]: _price_at(conn, t["company_id"], until, t["price"]) if until > start else t["price"] for t in event["touched"]}
    featured = str(event["featured_company_id"])
    move = (prices[featured] - event["start_price"]) * BPS // event["start_price"]
    out = []
    for entry in _rows(conn, "SELECT n.*, e.name, e.account_id FROM live_event_entries n JOIN empires e ON e.id = n.empire_id"
                             " WHERE n.event_id = %s ORDER BY n.empire_id", (event["id"],)):
        result, traded = 0, False
        for t in event["touched"]:
            held = int(entry["held_at_bell"].get(t["company_id"], 0))
            result += held * (prices[t["company_id"]] - t["price"])
            for trade in _rows(conn, "SELECT price, quantity, buyer_account_id = %s AS bought, seller_account_id = %s AS sold, buyer_fee, seller_fee"
                                     " FROM market_trades WHERE company_id = %s AND traded_at >= %s AND traded_at <= %s"
                                     " AND (buyer_account_id = %s OR seller_account_id = %s)",
                               (entry["account_id"], entry["account_id"], t["company_id"], start, until, entry["account_id"], entry["account_id"])):
                traded = True
                if trade["bought"]:
                    result += trade["quantity"] * (prices[t["company_id"]] - trade["price"]) - trade["buyer_fee"]
                if trade["sold"]:
                    result += trade["quantity"] * (trade["price"] - prices[t["company_id"]]) - trade["seller_fee"]
            # Deals on the Floor in the touched shares during the window count too (no exchange fee).
            if _one(conn, "SELECT to_regclass('floor_trades') IS NOT NULL AS ok")["ok"]:
                for trade in _rows(conn, "SELECT price, quantity, buyer_account = %s AS bought, seller_account = %s AS sold FROM floor_trades"
                                         " WHERE company_id = %s AND at >= %s AND at <= %s AND (buyer_account = %s OR seller_account = %s)",
                                   (entry["account_id"], entry["account_id"], t["company_id"], start, until, entry["account_id"], entry["account_id"])):
                    traded = True
                    if trade["bought"]:
                        result += trade["quantity"] * (prices[t["company_id"]] - trade["price"])
                    if trade["sold"]:
                        result += trade["quantity"] * (trade["price"] - prices[t["company_id"]])
        if entry["run_by_players"] and entry["prediction_bps"] is None:
            # The members' closest prediction counts for the empire; on a tie, the one sealed first.
            members = _rows(conn, "SELECT player_id, move_bps, at FROM live_event_predictions WHERE event_id = %s AND empire_id = %s",
                            (event["id"], entry["empire_id"]))
            best = min(members, key=lambda m: (abs(m["move_bps"] - move), m["at"]), default=None)
            entry = {**entry, "predictions": len(members)}
            if best:
                entry.update(prediction_bps=best["move_bps"], predicted_by=best["player_id"], predicted_at=best["at"])
        out.append({**entry, "result_kobo": result, "traded": traded,
                    "result_bps": result * BPS // entry["worth_at_bell"] if entry["worth_at_bell"] > 0 else 0,
                    "miss_bps": abs(entry["prediction_bps"] - move) if entry["prediction_bps"] is not None else None})
    return move, out


def _places(rows: list[dict], key, least: int) -> dict:
    """The first three by `key` (lower first), with the points for each place; none if fewer than `least` took part."""
    if len(rows) < least:
        return {}
    ranked = sorted(rows, key=key)
    return {r["empire_id"]: data.LIVE_PLACES[i] for i, r in enumerate(ranked[:len(data.LIVE_PLACES)])}


def score(conn: Connection, event_id: int, now: datetime) -> dict:
    """When the thirty minutes end: rank the predictions and the results, and give the league its points. Once."""
    with conn.transaction():
        event = _event(conn, event_id, lock=True)
        if event["status"] == "scored":
            return event
        move, rows = _results(conn, event, event["ends_at"])
        predicted = [r for r in rows if r["prediction_bps"] is not None]
        guessed = [r for r in predicted if r["miss_bps"] <= data.LIVE_MOST_MISS_BPS]
        # Earlier is better on a tie: the sooner a prediction was sealed, the less of the market it had seen.
        by_guess = (_places(guessed, lambda r: (r["miss_bps"], r["predicted_at"], r["empire_id"]), least=1)
                    if len(predicted) >= data.LIVE_LEAST_EMPIRES else {})
        gained = [r for r in rows if r["result_kobo"] > 0]
        by_money = _places(gained, lambda r: (-r["result_bps"], -r["result_kobo"], r["empire_id"]), least=1)
        acted = {r["empire_id"] for r in _rows(conn, "SELECT DISTINCT empire_id FROM live_event_actions WHERE event_id = %s AND done", (event_id,))}
        period = careers.world_now(conn, now)["period"]
        name = KINDS[event["kind"]]
        for r in rows:
            points = 0
            if r["empire_id"] in by_guess:
                points += by_guess[r["empire_id"]]
                leagues.award(conn, r["empire_id"], by_guess[r["empire_id"]], f"Live event, {name}: one of the closest predictions",
                              period, now, reference=f"live:{event_id}:prediction")
            if r["empire_id"] in by_money:
                points += by_money[r["empire_id"]]
                leagues.award(conn, r["empire_id"], by_money[r["empire_id"]], f"Live event, {name}: one of the best results",
                              period, now, reference=f"live:{event_id}:money")
            if r["run_by_players"] and (r["prediction_bps"] is not None or r["traded"] or r["empire_id"] in acted):
                points += data.LIVE_TOOK_PART
                leagues.award(conn, r["empire_id"], data.LIVE_TOOK_PART, f"Live event, {name}: took part", period, now,
                              reference=f"live:{event_id}:took_part")
            if r["run_by_players"] and r["prediction_bps"] is not None:
                conn.execute("UPDATE live_event_entries SET prediction_bps = %s, predicted_by = %s, predicted_at = %s"
                             " WHERE event_id = %s AND empire_id = %s AND prediction_bps IS NULL",
                             (r["prediction_bps"], r["predicted_by"], r["predicted_at"], event_id, r["empire_id"]))
            conn.execute("UPDATE live_event_entries SET result_kobo = %s, result_bps = %s, miss_bps = %s, points = %s"
                         " WHERE event_id = %s AND empire_id = %s",
                         (r["result_kobo"], r["result_bps"], r["miss_bps"], points, event_id, r["empire_id"]))
        # The Floor (16 November 2026): its best banks and clients during the event earn their empires points too.
        from simulation import floor
        floor.live_scores(conn, event, now)
        end_price = event["start_price"] * (BPS + move) // BPS
        conn.execute("UPDATE live_events SET status = 'scored', scored_at = %s, end_price = %s WHERE id = %s", (now, end_price, event_id))
        from simulation import duels               # Duels on the Floor fought in this event are decided
        duels.score(conn, event, now)
        top = _one(conn, "SELECT e.name, n.points FROM live_event_entries n JOIN empires e ON e.id = n.empire_id WHERE n.event_id = %s"
                         " AND n.points > 0 ORDER BY n.points DESC, n.result_bps DESC NULLS LAST, n.empire_id LIMIT 1", (event_id,))
        state = careers.world_now(conn, now)
        featured = _one(conn, "SELECT name, ticker FROM companies WHERE id = %s", (event["featured_company_id"],))
        news.publish(conn, period=state["period"], day=state["day"], kind="live_event_result", story=f"live-result:{event_id}",
                     facts={"show": name, "winner": top["name"] if top else "nobody", "points": str(top["points"] if top else 0),
                            "company": featured["name"], "move": _pct(move)},
                     tickers=[featured["ticker"]])
        pings.ping(conn, "event")             # heard once the scores are saved
    return _event(conn, event_id)


def tick(conn: Connection, now: datetime) -> bool:
    """Every few minutes: ring the bell when it is due, and score each event when its thirty minutes are up. True if the
    bell rang just now."""
    if not ready(conn):
        return False
    from simulation import duels               # Duels on the Floor: challenges not answered lapse at the bell
    duels.tick(conn, now)
    rang = False
    bell = slot_now(now)
    if bell is not None and now < bell + timedelta(minutes=data.LIVE_LATE_OPEN_MINUTES):
        rang = open_event(conn, bell, now) is not None
    for e in _rows(conn, "SELECT id FROM live_events WHERE status = 'open' AND ends_at <= %s ORDER BY id", (now,)):
        score(conn, e["id"], now)
    return rang


# ---------------------------------------------------------------------------
# What the rest of the world reads
# ---------------------------------------------------------------------------

def shocks_today(conn: Connection, session, *, lag_days: int = 0) -> dict:
    """What live events add to how investors value each share on a trading day: in full on its first day, fading over its
    days. `lag_days`: an investor who reads the news late sees it that many days later."""
    if not _one(conn, "SELECT to_regclass('live_event_shocks') IS NOT NULL AS ok")["ok"]:
        return {}
    seen = session - timedelta(days=lag_days)
    out: dict = {}
    for s in _rows(conn, "SELECT company_id, bps, session_date, days FROM live_event_shocks WHERE session_date <= %s AND session_date > %s",
                   (seen, seen - timedelta(days=10))):
        gone = (seen - s["session_date"]).days
        if 0 <= gone < s["days"]:
            out[s["company_id"]] = out.get(s["company_id"], 0) + s["bps"] * (s["days"] - gone) // s["days"]
    return {k: max(min(v, data.LIVE_SHOCK_MOST_BPS), -data.LIVE_SHOCK_MOST_BPS) for k, v in out.items()}


def trust_hit(conn: Connection, company_id, period: int, day: int) -> int:
    """A run started by a live event: savers' trust in the bank is down for some game days."""
    if not _one(conn, "SELECT to_regclass('live_events') IS NOT NULL AS ok")["ok"]:
        return 0
    hit = _one(conn, "SELECT 1 AS x FROM live_events WHERE kind = 'bank_run' AND featured_company_id = %s"
                     " AND (period * 100 + day) BETWEEN %s AND %s", (company_id, period * 100 + day - data.LIVE_RUN_GAME_DAYS, period * 100 + day))
    return -data.LIVE_RUN_TRUST_POINTS if hit else 0


def rate_extra_bps(conn: Connection, period: int) -> int:
    """The Central Bank's emergency moves this quarter, added to its next decision at the close."""
    if not _one(conn, "SELECT to_regclass('live_events') IS NOT NULL AS ok")["ok"]:
        return 0
    return _one(conn, "SELECT coalesce(sum(rate_bps), 0)::int AS r FROM live_events WHERE kind = 'rate_move' AND period = %s", (period,))["r"]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def _public(conn: Connection, event: dict, empire_id, now: datetime) -> dict:
    running = event["status"] == "open"
    move, rows = _results(conn, event, min(now, event["ends_at"]) if running else event["ends_at"])
    featured = _one(conn, "SELECT name, ticker FROM companies WHERE id = %s", (event["featured_company_id"],))
    names = {r["id"]: r["display_name"] for r in _rows(
        conn, "SELECT id, display_name FROM players WHERE id IN (SELECT player_id FROM live_event_predictions WHERE event_id = %s"
              " UNION SELECT predicted_by FROM live_event_entries WHERE event_id = %s AND predicted_by IS NOT NULL)", (event["id"], event["id"]))}
    table = []
    for r in sorted(rows, key=lambda r: (-(r["points"] if not running else 0), -r["result_bps"], r["empire_id"])):
        mine = r["empire_id"] == empire_id
        table.append({
            "empire": r["name"], "yours": mine, "run_by": "players" if r["run_by_players"] else "the computer",
            "result_bps": r["result_bps"], "result_kobo": r["result_kobo"] if mine else None,
            # Sealed until the event is scored: others only see how many of an empire's members have predicted.
            "predicted": r["prediction_bps"] is not None, "predictions": r.get("predictions", 1 if r["prediction_bps"] is not None else 0),
            "prediction_bps": r["prediction_bps"] if not running else None,
            "counted_by": names.get(r["predicted_by"]) if not running and r["run_by_players"] else None,
            "miss_bps": r["miss_bps"] if not running else None, "points": r["points"] if not running else None})
    # The player's own empire: every member's prediction, to its own members only (others' only once scored).
    members = []
    if empire_id:
        for m in _rows(conn, "SELECT player_id, move_bps, at FROM live_event_predictions WHERE event_id = %s AND empire_id = %s ORDER BY at",
                       (event["id"], empire_id)):
            members.append({"name": names.get(m["player_id"], "A member"), "prediction_bps": m["move_bps"],
                            "miss_bps": None if running else abs(m["move_bps"] - move)})
    actions = _rows(conn, "SELECT what, done, at FROM live_event_actions WHERE event_id = %s AND empire_id = %s ORDER BY at",
                    (event["id"], empire_id)) if empire_id else []
    return {
        "id": event["id"], "kind": event["kind"], "name": KINDS[event["kind"]], "headline": event["headline"], "story": event["story"],
        "starts_at": event["starts_at"], "ends_at": event["ends_at"], "predict_until": event["predict_until"],
        "status": event["status"], "featured": {"name": featured["name"], "ticker": featured["ticker"]},
        "start_price": event["start_price"], "price_now": event["start_price"] * (BPS + move) // BPS, "move_bps": move,
        "touched": [{"ticker": t["ticker"], "name": t["name"], "direction": "up" if t["bps"] > 0 else "down" if t["bps"] < 0 else "bid"}
                    for t in event["touched"]],
        "table": table, "your_actions": actions, "your_members": members,
        # The Floor's best banks and clients of the event: places and points only, never what they made.
        "floor": _rows(conn, "SELECT p.display_name AS name, s.role, s.place, s.points FROM floor_scores s JOIN players p ON p.id = s.player_id"
                             " WHERE s.window_key = %s ORDER BY s.role, s.place", (f"live:{event['id']}",))
                 if not running and _one(conn, "SELECT to_regclass('floor_scores') IS NOT NULL AS ok")["ok"] else [],
    }


def view(conn: Connection, player_id, now: datetime) -> dict:
    if not ready(conn):
        return {"ready": False}
    seat = empires.seat_of(conn, player_id)
    empire_id = seat["empire_id"] if seat and seat["empire_status"] == "active" and seat["empire_kind"] == "player" else None
    live = _one(conn, "SELECT * FROM live_events WHERE status = 'open' ORDER BY starts_at DESC LIMIT 1")
    past = _rows(conn, "SELECT * FROM live_events WHERE status = 'scored' ORDER BY starts_at DESC LIMIT 6")
    plan = _one(conn, "SELECT plan, budget, at FROM live_event_plans WHERE empire_id = %s", (empire_id,)) if empire_id else None
    in_field = _one(conn, "SELECT 1 AS x FROM live_event_entries WHERE event_id = %s AND empire_id = %s",
                    (live["id"], empire_id)) if live and empire_id else None
    mine = _one(conn, "SELECT move_bps FROM live_event_predictions WHERE event_id = %s AND player_id = %s",
                (live["id"], player_id)) if live else None
    return {
        "ready": True, "now": now,
        "next_at": next_slot(now), "days": "Monday, Wednesday and Friday", "hour": f"{data.LIVE_EVENT_HOUR}:00 Lagos time",
        "minutes": data.LIVE_EVENT_MINUTES, "predict_minutes": data.LIVE_PREDICT_MINUTES,
        "points": {"places": list(data.LIVE_PLACES), "took_part": data.LIVE_TOOK_PART, "most_miss_bps": data.LIVE_MOST_MISS_BPS},
        "kinds": [{"code": k, "name": v} for k, v in KINDS.items()],
        "plans": [{"code": k, "words": v} for k, v in PLANS.items()],
        "empire": seat["empire_name"] if empire_id else None, "is_head": bool(seat and empire_id and seat["head_player_id"] == player_id),
        "plan": plan,
        "live": _public(conn, live, empire_id, now) if live else None,
        "can_predict": bool(live and in_field and mine is None and now < live["predict_until"]),
        "your_prediction_bps": mine["move_bps"] if mine else None,
        "past": [_public(conn, e, empire_id, now) for e in past],
        # The empire's War Room chat, here too, so members can talk an event over without leaving the page. Only the
        # empire's own members ever see it.
        "chat": list(reversed(_rows(conn, "SELECT m.id, p.display_name AS who, m.body, m.at, m.player_id = %s AS yours FROM empire_messages m"
                                          " JOIN players p ON p.id = m.player_id WHERE m.empire_id = %s ORDER BY m.id DESC LIMIT %s",
                                    (player_id, empire_id, data.LIVE_CHAT_LINES)))) if empire_id else [],
    }
