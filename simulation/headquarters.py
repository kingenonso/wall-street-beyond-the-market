"""Empire headquarters (Stage 8).

Every empire may set up its headquarters in a building it owns outright, in the city of its choice,
and move it later. It is raised level by level, from 1 to 120:

  * Each level costs more than the one before (Level n costs n to the power 1.6 times ₦100,000, more in
    a dear city), and its benefits grow more slowly (with the square root of the level). An average
    active empire reaches about Level 20 in its first game year, a top empire about 60; Level 120 is a
    goal of about two real years.
  * Every ten levels add a seat beyond the twelve (plus the head): a third seat for one build, then the
    next, in turn.
  * Its standing adds to what members learn from work done for the empire: 0.3% times the square root of
    the level, and twice that for work for a client in one of its city's industries.
  * Each city brings its own: Lagos the best deals and recruits (players may join with a reputation five
    lower), but the dearest land and building; Abuja lobbying (felt when the Government stage comes);
    Port Harcourt energy; Kano the cheapest; Aba manufacturing.
  * Its upkeep (1% a quarter of what has been spent on it) is asked for by the Risk Manager and approved
    by the head. Without it the building wears quickly. Warnings go out at 50, 30 and 15; below 15 it may
    fall down. Then the building is lost (insurance pays if the empire bought cover), the headquarters'
    benefits stop and its extra seats are frozen until it is rebuilt. The head and the Risk Manager lose
    reputation if they ignored the warnings. Members keep their seats and their money.
"""

from __future__ import annotations

import math
from datetime import datetime

from psycopg import Connection

from simulation import clock, ledger
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from simulation.property import PropertyError, _one, _rows, _uniform, money


def level_cost(level: int, city: str) -> int:
    """What raising the headquarters to this level costs."""
    return naira(data.HQ_LEVEL_BASE_NAIRA) * int(level ** (data.HQ_LEVEL_POWER / BPS) * 100) // 100 * data.CITY_COST_BPS[city] // BPS


def cost_to(level_from: int, level_to: int, city: str) -> int:
    return sum(level_cost(n, city) for n in range(level_from + 1, level_to + 1))


def extra_seats(level: int) -> int:
    return min(level // data.HQ_SEAT_EVERY, data.HQ_MOST_LEVEL // data.HQ_SEAT_EVERY)


def of(conn: Connection, empire_id: int) -> dict | None:
    return _one(conn, "SELECT q.*, p.name AS building, p.status AS building_status, d.city, d.name AS district FROM headquarters q"
                      " JOIN properties p ON p.id = q.property_id JOIN districts d ON d.id = p.district_id WHERE q.empire_id = %s", (empire_id,))


def standing(hq: dict | None) -> bool:
    return hq is not None and hq["collapsed_period"] is None


def bonus_bps(conn: Connection, empire_id: int, client_sector: str | None = None) -> int:
    """What the headquarters adds to what members learn from the empire's work, in hundredths of a percent."""
    hq = of(conn, empire_id)
    if not standing(hq):
        return 0
    bonus = int(data.HQ_BONUS_PER_ROOT_BPS * math.sqrt(hq["level"]))
    if client_sector and client_sector in data.HQ_CITY_INDUSTRIES.get(hq["city"], ()):
        bonus *= 2
    return bonus


def recruit_points(conn: Connection, empire_id: int) -> int:
    hq = of(conn, empire_id)
    return data.LAGOS_RECRUIT_POINTS if standing(hq) and hq["city"] == data.LAGOS else 0


def _head(conn: Connection, head_id) -> tuple[dict, dict]:
    from simulation import firm
    seat, empire = firm._active(conn, head_id)
    if empire["head_player_id"] != head_id:
        raise PropertyError("The head decides on the headquarters.")
    return seat, empire


def _pay(conn: Connection, empire: dict, amount: int, city: str, why: str, period: int, now: datetime) -> None:
    if ledger.balance(conn, empire["account_id"]) < amount:
        raise PropertyError(f"That costs {money(amount)}. The empire has not the cash.")
    prop._pay_builders(conn, empire["account_id"], amount, city, why, period)
    from simulation import empires
    empires._book(conn, empire["id"], period, "Headquarters", why, amount, True, now, kind="fee")


def sync_seats(conn: Connection, empire_id: int) -> None:
    """The seats beyond the twelve follow the headquarters' level; they are frozen while it is down."""
    hq = of(conn, empire_id)
    want = extra_seats(hq["level"]) if hq else 0
    frozen = not standing(hq)
    have = _rows(conn, "SELECT * FROM empire_seats WHERE empire_id = %s AND slot >= 3 ORDER BY slot, build", (empire_id,))
    existing = {(s["build"], s["slot"]) for s in have}
    for n in range(want):
        build = data.EMPIRE_BUILDS[n % len(data.EMPIRE_BUILDS)]
        slot = 3 + n // len(data.EMPIRE_BUILDS)
        if (build, slot) not in existing:
            conn.execute("INSERT INTO empire_seats (empire_id, build, slot, staffed) VALUES (%s, %s, %s, false)", (empire_id, build, slot))
    conn.execute("UPDATE empire_seats SET hq_frozen = %s WHERE empire_id = %s AND slot >= 3", (frozen, empire_id))


def establish(conn: Connection, head_id, property_id: int, now: datetime) -> dict:
    """Make a building the empire owns outright its headquarters, or move the headquarters there (a move
    costs a tenth of what has been spent on the headquarters; its level goes with it)."""
    from simulation import careers, empires
    with conn.transaction():
        state = careers.world_now(conn, now)
        seat, empire = _head(conn, head_id)
        p = prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, empire["account_id"]) < BPS:
            raise PropertyError("The headquarters must be in a building the empire owns outright.")
        if p["status"] != "standing" or p["kind"] in ("land", "farmland"):
            raise PropertyError("Put up a building here first: a headquarters needs a building.")
        if _one(conn, "SELECT 1 FROM auctions WHERE property_id = %s AND status = 'open'", (property_id,)):
            raise PropertyError("It is up for auction.")
        hq = of(conn, empire["id"])
        if hq is None:
            cost = level_cost(1, p["city"])
            _pay(conn, empire, cost, p["city"], "Headquarters set up (Level 1)", state["period"], now)
            conn.execute("INSERT INTO headquarters (empire_id, property_id, level, spent, condition, since) VALUES (%s, %s, 1, %s, 100, %s)",
                         (empire["id"], property_id, cost, now))
            empires._log(conn, empire["id"], f"The empire set up its headquarters in {p['name']}, {p['city']}.", now)
        else:
            if hq["property_id"] == property_id:
                raise PropertyError("The headquarters is already there.")
            cost = hq["spent"] // 10
            _pay(conn, empire, cost, p["city"], "Moving the headquarters", state["period"], now)
            conn.execute("UPDATE headquarters SET property_id = %s, spent = spent + %s, condition = %s, warnings = 0, collapsed_period = NULL, homeless = false"
                         " WHERE empire_id = %s", (property_id, cost, max(p["condition"], 60), empire["id"]))
            empires._log(conn, empire["id"], f"The empire moved its headquarters to {p['name']}, {p['city']}.", now)
        sync_seats(conn, empire["id"])
        return view(conn, empire, now)


def raise_level(conn: Connection, head_id, levels: int, now: datetime) -> dict:
    from simulation import careers, empires
    with conn.transaction():
        state = careers.world_now(conn, now)
        seat, empire = _head(conn, head_id)
        hq = _one(conn, "SELECT * FROM headquarters WHERE empire_id = %s FOR UPDATE", (empire["id"],))
        if hq is None:
            raise PropertyError("The empire has no headquarters yet.")
        if hq["collapsed_period"] is not None:
            raise PropertyError("The headquarters is down. Rebuild it first.")
        if not isinstance(levels, int) or isinstance(levels, bool) or levels < 1:
            raise PropertyError("Raise it by one level or more.")
        target = hq["level"] + levels
        if target > data.HQ_MOST_LEVEL:
            raise PropertyError(f"Level {data.HQ_MOST_LEVEL} is the highest.")
        city = of(conn, empire["id"])["city"]
        cost = cost_to(hq["level"], target, city)
        _pay(conn, empire, cost, city, f"Headquarters raised to Level {target}", state["period"], now)
        conn.execute("UPDATE headquarters SET level = %s, spent = spent + %s WHERE empire_id = %s", (target, cost, empire["id"]))
        empires._log(conn, empire["id"], f"The headquarters rose to Level {target}.", now)
        sync_seats(conn, empire["id"])
        return {"level": target, "cost": cost}


def ask_upkeep(conn: Connection, player_id, now: datetime) -> None:
    """The Risk Manager asks for the headquarters' upkeep (or the head, if nobody holds that desk)."""
    from simulation import firm
    with conn.transaction():
        seat, empire = firm._active(conn, player_id)
        if seat["build"] != "risk_manager" and not (empire["head_player_id"] == player_id and not firm.desk_members(conn, empire["id"], "risk_manager")):
            raise PropertyError("The Risk Manager asks for the headquarters' upkeep.")
        if of(conn, empire["id"]) is None:
            raise PropertyError("The empire has no headquarters yet.")
        conn.execute("UPDATE headquarters SET upkeep_asked = true WHERE empire_id = %s", (empire["id"],))


def approve_upkeep(conn: Connection, head_id, approve: bool, now: datetime) -> None:
    with conn.transaction():
        seat, empire = _head(conn, head_id)
        if of(conn, empire["id"]) is None:
            raise PropertyError("The empire has no headquarters yet.")
        conn.execute("UPDATE headquarters SET upkeep_approved = %s WHERE empire_id = %s", (approve, empire["id"]))


def lost_building(conn: Connection, property_id: int, new_owner, period: int, now: datetime,
                  why: str = "The headquarters' building was sold at the Auction House.") -> None:
    """The headquarters' building was sold to somebody else (a forced sale for unpaid tax or a mortgage):
    its benefits stop and its extra seats freeze until the empire moves the headquarters to a building it owns."""
    from simulation import empires
    for hq in _rows(conn, "SELECT q.*, e.account_id FROM headquarters q JOIN empires e ON e.id = q.empire_id WHERE q.property_id = %s"
                          " AND NOT q.homeless", (property_id,)):
        if hq["account_id"] == new_owner:
            continue
        conn.execute("UPDATE headquarters SET collapsed_period = %s, homeless = true WHERE empire_id = %s", (period, hq["empire_id"]))
        sync_seats(conn, hq["empire_id"])
        empires._log(conn, hq["empire_id"], why + " Its benefits stop and its extra seats "
                                            "are frozen until the head moves the headquarters to a building the empire owns.", now)


def rebuild(conn: Connection, head_id, now: datetime) -> dict:
    from simulation import careers, empires
    with conn.transaction():
        state = careers.world_now(conn, now)
        seat, empire = _head(conn, head_id)
        hq = of(conn, empire["id"])
        if hq is None or hq["collapsed_period"] is None:
            raise PropertyError("The headquarters is standing.")
        if hq["homeless"] or prop.share_of(conn, hq["property_id"], empire["account_id"]) < BPS:
            raise PropertyError("The empire no longer owns that building. Move the headquarters to a building it owns.")
        p = prop._property(conn, hq["property_id"], lock=True)
        cost = prop.build_cost(p)
        _pay(conn, empire, cost, p["city"], "Rebuilding the headquarters", state["period"], now)
        kind = data.DISTRICT_BUILDINGS[p["district_kind"]][0]
        kind = kind if kind != "farmland" else "office"
        conn.execute("UPDATE properties SET kind = %s, status = 'standing', condition = 100, base_rent = %s, built_period = %s WHERE id = %s",
                     (kind, prop.base_rent(p["city"], kind, p["size_m2"]), state["period"], p["id"]))
        conn.execute("UPDATE headquarters SET condition = 100, warnings = 0, collapsed_period = NULL WHERE empire_id = %s", (empire["id"],))
        empires._log(conn, empire["id"], "The headquarters was rebuilt.", now)
        sync_seats(conn, empire["id"])
        return {"cost": cost}


def close(conn: Connection, period: int, now: datetime, seed: str) -> None:
    """Each headquarters' quarter: upkeep (if approved), wear, warnings, and perhaps a collapse."""
    from simulation import empires
    label = clock.period_label(period)
    for hq in _rows(conn, "SELECT q.*, e.account_id, e.name, e.head_player_id, p.name AS building, d.city FROM headquarters q"
                          " JOIN empires e ON e.id = q.empire_id JOIN properties p ON p.id = q.property_id JOIN districts d ON d.id = p.district_id"
                          " WHERE q.collapsed_period IS NULL AND e.status = 'active' ORDER BY q.empire_id"):
        wear = data.HQ_WEAR_WITHOUT_UPKEEP
        if hq["upkeep_approved"]:
            cost = hq["spent"] * data.HQ_UPKEEP_BPS // BPS
            paid = prop._pay_builders(conn, hq["account_id"], cost, hq["city"], f"{hq['name']}: headquarters upkeep, {label}", period)
            if paid >= cost:
                wear = 1
        condition = max(hq["condition"] - wear, 0)
        warnings = hq["warnings"]
        for n, threshold in enumerate(data.HQ_WARN_AT, 1):
            if condition < threshold <= hq["condition"]:
                warnings = max(warnings, n)
                empires._log(conn, hq["empire_id"], f"Warning: the headquarters' condition has fallen below {threshold}. "
                                                    f"Its upkeep needs the Risk Manager to ask and the head to approve.", now)
        conn.execute("UPDATE headquarters SET condition = %s, warnings = %s WHERE empire_id = %s", (condition, warnings, hq["empire_id"]))
        conn.execute("UPDATE properties SET condition = least(condition, %s) WHERE id = %s", (condition, hq["property_id"]))
        if condition < data.HQ_COLLAPSE_BELOW:
            chance = (data.HQ_COLLAPSE_BELOW - condition) / 10
            if condition == 0 or _uniform(seed, f"collapse:{hq['empire_id']}", period) < chance:
                _collapse(conn, hq, period, now, warnings)


def _collapse(conn: Connection, hq: dict, period: int, now: datetime, warnings: int) -> None:
    from simulation import empires, firm_tasks, news
    p = _one(conn, "SELECT * FROM properties WHERE id = %s", (hq["property_id"],))
    d = prop.districts(conn)[p["district_id"]]
    lost = prop.value(p, d, prop.policy_rate(conn)) - prop.value({**p, "status": "collapsed"}, d, prop.policy_rate(conn))
    conn.execute("UPDATE properties SET status = 'collapsed', condition = 0 WHERE id = %s", (p["id"],))
    conn.execute("UPDATE headquarters SET collapsed_period = %s, condition = 0 WHERE empire_id = %s", (period, hq["empire_id"]))
    empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (hq["empire_id"],))
    paid = firm_tasks._claim(conn, empire, "headquarters", max(lost, 0), period, now)
    sync_seats(conn, hq["empire_id"])
    blamed = []
    if warnings > 0 and not hq["upkeep_approved"]:
        # The warnings were ignored. The Risk Manager is to blame for not asking for the upkeep; the head for not
        # approving it once asked (or, with nobody at the Risk Manager's desk, for not seeing to it at all).
        risk = [s["player_id"] for s in _rows(conn, "SELECT player_id FROM empire_seats WHERE empire_id = %s AND build = 'risk_manager'"
                                                    " AND player_id IS NOT NULL", (empire["id"],))]
        at_fault = ([empire["head_player_id"]] if hq["upkeep_asked"] or not risk else []) + ([] if hq["upkeep_asked"] else risk)
        for player in at_fault:
            if player is not None:
                conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s", (data.HQ_COLLAPSE_REPUTATION, player))
                blamed.append(player)
    empires._log(conn, hq["empire_id"], f"The headquarters, {p['name']}, has fallen down. " +
                 (f"Insurance paid {money(paid)}. " if paid else "It was not insured. ") +
                 "Its benefits stop and its extra seats are frozen until it is rebuilt. Members keep their seats and their money." +
                 (" Those who ignored the warnings lose reputation." if blamed else ""), now)
    news.publish(conn, period=period + 1, day=4, kind="hq_collapse", story=f"hq:{hq['empire_id']}:{period}",
                 facts={"empire": empire["name"], "building": p["name"], "city": d["city"]}, locations=[d["city"]])


def view(conn: Connection, empire: dict, now: datetime) -> dict:
    hq = of(conn, empire["id"])
    owned = []
    ds = prop.districts(conn)
    for p in _rows(conn, "SELECT p.* FROM properties p JOIN property_holdings h ON h.property_id = p.id WHERE h.account_id = %s"
                         " AND h.share_bps = 10000 ORDER BY p.id", (empire["account_id"],)):
        owned.append({"id": p["id"], "name": p["name"], "city": ds[p["district_id"]]["city"], "kind": p["kind"], "status": p["status"]})
    base = {"owned": owned, "cities": [{"city": c, "words": w, "cost_bps": data.CITY_COST_BPS[c], "industries": list(data.HQ_CITY_INDUSTRIES[c])}
                                       for c, w in data.HQ_CITY_WORDS.items()]}
    if hq is None:
        return {**base, "headquarters": None}
    level = hq["level"]
    seats = _rows(conn, "SELECT build, slot, player_id IS NOT NULL AS held, hq_frozen AS frozen FROM empire_seats WHERE empire_id = %s AND slot >= 3"
                        " ORDER BY slot, build", (empire["id"],))
    return {**base, "headquarters": {
        "building": hq["building"], "property_id": hq["property_id"], "city": hq["city"], "district": hq["district"],
        "level": level, "spent": hq["spent"], "condition": hq["condition"], "warnings": hq["warnings"],
        "standing": standing(hq), "collapsed": hq["collapsed_period"] is not None, "homeless": hq["homeless"],
        "upkeep_asked": hq["upkeep_asked"], "upkeep_approved": hq["upkeep_approved"], "upkeep": hq["spent"] * data.HQ_UPKEEP_BPS // BPS,
        "bonus_bps": bonus_bps(conn, empire["id"]), "city_bonus_bps": 2 * bonus_bps(conn, empire["id"]),
        "city_words": data.HQ_CITY_WORDS[hq["city"]], "industries": list(data.HQ_CITY_INDUSTRIES[hq["city"]]),
        "extra_seats": extra_seats(level), "seats": [{"build": s["build"], "slot": s["slot"], "held": s["held"], "frozen": s["frozen"]} for s in seats],
        "next_cost": level_cost(level + 1, hq["city"]) if level < data.HQ_MOST_LEVEL else None,
        "next_seat_at": (level // data.HQ_SEAT_EVERY + 1) * data.HQ_SEAT_EVERY if level < data.HQ_MOST_LEVEL else None,
        "rebuild_cost": prop.build_cost({"size_m2": _one(conn, "SELECT size_m2 FROM properties WHERE id = %s", (hq["property_id"],))["size_m2"],
                                         "city": hq["city"]}),
        "lobbying": level if hq["city"] == data.ABUJA else 0,
    }}
