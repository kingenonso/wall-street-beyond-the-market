"""The 1,000 consumer groups (economy upgrade, owner, 12 October 2026).

Before this, each location's households acted as one block: a mix of the ten
mindsets, all earning and spending together. Now each location is made of
consumer groups, 1,000 in all, shared out by population (Lagos 350, Kano 200,
and 150 each in Abuja, Port Harcourt and Aba). Each group:

  * lives in one location, and may move to another;
  * earns at one of five income levels;
  * thinks in one of the ten mindsets;
  * has its own savings and debts;
  * has its own taste for each kind of good.

Every quarter, each group decides for itself how much to spend, out of what it
earned and what it has saved, and how keen it is to borrow. Its mindset decides
how it reacts to the news; its income level decides how much of what it earns it
spends, and on what. The groups of a location are then added up, and their
spending goes through the same ledger account as before, so every naira is still
counted exactly once.

The money stays in each location's household account. A group's savings and debts
are its share of that account and of the location's loans: after every quarter
they are put back in line with the ledger to the kobo. When a group moves, its
savings are paid from one location's account to the other, and its debts go with it.

Groups are private to the simulation. Players see them only added up: by income
level, by mindset, and how many moved.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger, mindsets
from simulation import world_data as data
from simulation.fortune import fortune_bps
from simulation.money import BPS, apply_bps


def _uniform(seed: str, subject: str, period: int) -> float:
    """A draw between 0 and 1, every value equally likely, fixed by the world's secret."""
    digest = hashlib.sha256(f"{seed}:{subject}:{period}:uniform".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Making the groups when a world is created
# ---------------------------------------------------------------------------

def _counts(total: int, shares: list[int]) -> list[int]:
    """Share out a whole number in proportion to `shares`, the remainder to the largest parts first."""
    whole = sum(shares)
    counts = [total * s // whole for s in shares]
    order = sorted(range(len(shares)), key=lambda i: -(total * shares[i] % whole))
    for i in order[: total - sum(counts)]:
        counts[i] += 1
    return counts


def _band_tastes() -> dict[str, list[int]]:
    """Each level's taste for each kind of good, scaled so that, across all groups weighted by what they
    earn, the average taste is exactly 10000: on day one the groups spend just as the old blocks did."""
    weights = [g * e for g, e in zip(data.INCOME_BAND_GROUPS_PERCENT, data.INCOME_BAND_EARNS_BPS)]
    out = {}
    for sector, tastes in data.INCOME_BAND_TASTES.items():
        average = sum(t * w for t, w in zip(tastes, weights)) / sum(weights)
        out[sector] = [round(t * BPS / average) for t in tastes]
    return out


def create(conn: Connection, seed: str, savings: dict[str, int], debts: dict[str, int]) -> None:
    """Make the 1,000 groups. `savings` and `debts` are each location's opening totals, which the
    groups share between them: richer groups hold more of the savings, and owe in line with what they earn."""
    locations = _rows(conn, "SELECT name, population_bps FROM locations ORDER BY sort_order")
    per_location = _counts(data.CONSUMER_GROUPS, [loc["population_bps"] for loc in locations])
    tastes = _band_tastes()
    sectors = [r["code"] for r in _rows(conn, "SELECT code FROM sectors ORDER BY sort_order")]
    group_id = 0
    for loc, count in zip(locations, per_location):
        name = loc["name"]
        bands = _counts(count, list(data.INCOME_BAND_GROUPS_PERCENT))
        # Mindsets are dealt so that the location's mix holds for what its groups earn (and so spend), not
        # only for their number: the richest groups are dealt first, each to the mindset furthest below its share.
        total_earned = sum(n * data.INCOME_BAND_EARNS_BPS[b] for b, n in enumerate(bands))
        target = {m: p * total_earned / 100 for m, p in zip(data.MINDSETS, data.MINDSET_MIX[name])}
        given = {m: 0 for m in data.MINDSETS}
        dealt: dict[int, list[str]] = {}
        for band_index in sorted(range(len(bands)), key=lambda b: -data.INCOME_BAND_EARNS_BPS[b]):
            dealt[band_index] = []
            for _ in range(bands[band_index]):
                pick = max(data.MINDSETS, key=lambda m: target[m] - given[m])
                given[pick] += data.INCOME_BAND_EARNS_BPS[band_index]
                dealt[band_index].append(pick)
        rows = []
        for band_index, n in enumerate(bands):
            for position in range(n):
                group_id += 1
                band = data.INCOME_BANDS[band_index]
                mindset = dealt[band_index][position]
                own = {}
                for sector in sectors:
                    base = tastes.get(sector, [BPS] * 5)[band_index]
                    spread = fortune_bps(seed, f"group-taste:{group_id}:{sector}", 0, "taste", data.GROUP_TASTE_SPREAD_BPS)
                    own[sector] = max(apply_bps(base, BPS + spread), 100)
                rows.append([group_id, name, band, mindset, data.INCOME_BAND_EARNS_BPS[band_index], own])
        # Savings follow earnings more than evenly (the rich hold more of them); debts and the
        # opening quarter's income follow earnings.
        earns = [r[4] for r in rows]
        save_weights = [round(e ** (data.GROUP_SAVINGS_TILT / BPS)) for e in earns]
        cash = _counts(savings.get(name, 0), save_weights)
        owed = _counts(debts.get(name, 0), earns)
        opening = _rows(conn, "SELECT income, spending FROM household_results WHERE location = %s AND period = 0", (name,))
        income = _counts(opening[0]["income"] if opening else 0, earns)
        spending = _counts(opening[0]["spending"] if opening else 0, earns)
        for r, c, d, i, sp in zip(rows, cash, owed, income, spending):
            conn.execute(
                "INSERT INTO consumer_groups (id, location, band, mindset, earns_bps, tastes, cash, debt, income, spending)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (r[0], r[1], r[2], r[3], r[4], json.dumps(r[5]), c, d, i, sp))
    record(conn, 0)


# ---------------------------------------------------------------------------
# One quarter
# ---------------------------------------------------------------------------

def load(conn: Connection) -> list[dict]:
    groups = _rows(conn, "SELECT * FROM consumer_groups ORDER BY id")
    if not groups:
        from simulation import economy
        raise economy.WorldTooOld("This world was created before the consumer groups existed. Start a new world to run this version.")
    return groups


def _habit_scales(groups: list[dict], household: dict) -> tuple[dict[str, int], dict[str, int]]:
    """How much of what they live on, and of their savings, each level spends, scaled so that a
    location's groups together keep the households' usual habit."""
    by_band = defaultdict(int)
    for g in groups:
        by_band[g["band"]] += g["earns_bps"]
    total = sum(by_band.values()) or 1
    spends = dict(zip(data.INCOME_BANDS, data.INCOME_BAND_SPENDS_BPS))
    dips = dict(zip(data.INCOME_BANDS, data.INCOME_BAND_DIPS_BPS))
    avg_spend = sum(by_band[b] * spends[b] for b in by_band) / total
    avg_dip = sum(by_band[b] * dips[b] for b in by_band) / total
    return ({b: round(household["spend_from_income_bps"] * spends[b] / avg_spend) for b in data.INCOME_BANDS},
            {b: round(household["spend_from_savings_bps"] * dips[b] / avg_dip) for b in data.INCOME_BANDS})


def respond(groups: list[dict], signals: dict[str, mindsets.Signals]) -> dict[str, dict]:
    """How each location's groups react to the news, added up by what each earns.

    Returns, for each location, the same figures a whole location gave before (spending and
    borrowing as multipliers, how strongly they favour local companies, which mindset moved
    them most), and each group's own reaction, kept on the group for the spending step.
    """
    out: dict[str, dict] = {}
    reactions = {location: mindsets.reactions(s) for location, s in signals.items()}
    weight: dict[str, int] = defaultdict(int)
    spend: dict[str, int] = defaultdict(int)
    borrow: dict[str, int] = defaultdict(int)
    loyal: dict[str, int] = defaultdict(int)
    moved: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in groups:
        location = g["location"]
        if location not in reactions:
            continue
        s, b = reactions[location][g["mindset"]]
        g["spend_bps"], g["borrow_bps"] = BPS + s, max(BPS + b, 1000)
        w = g["earns_bps"]
        weight[location] += w
        spend[location] += w * s
        borrow[location] += w * b
        moved[location][g["mindset"]] += w * s
        if g["mindset"] == "loyal":
            loyal[location] += w
    for location in reactions:
        total = weight[location] or 1
        strongest = max(moved[location], key=lambda m: abs(moved[location][m]), default=None)
        out[location] = {
            "spend_bps": BPS + spend[location] // total,
            "borrow_bps": max(BPS + borrow[location] // total, 1000),
            # The loyal shop close to home: the more of them, the stronger the local preference.
            "loyalty_bps": data.LOCAL_PREFERENCE_BPS + loyal[location] * BPS // total * 2,
            "moved_most_by": strongest if strongest and moved[location][strongest] != 0 else None,
        }
    return out


def mindset_mix(groups: list[dict]) -> dict[str, dict[str, int]]:
    """Each location's mix of mindsets, weighted by what its groups earn (they are who spends)."""
    weight: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in groups:
        weight[g["location"]][g["mindset"]] += g["earns_bps"]
    mix = {}
    for location, by_mind in weight.items():
        total = sum(by_mind.values()) or 1
        mix[location] = {m: by_mind.get(m, 0) * BPS // total for m in data.MINDSETS}
    return mix


def share_out(groups: list[dict], location: str, amount: int, weights: dict[int, int]) -> dict[int, int]:
    """Share an amount between a location's groups in proportion to `weights` (by group id)."""
    total = sum(weights.values())
    if amount <= 0 or total <= 0:
        return {}
    return {gid: amount * w // total for gid, w in weights.items() if w > 0}


def budgets(conn: Connection, groups: list[dict], world, period: int, *, borrowed: dict[str, int],
            debt_service: dict[str, int], moods: dict[str, int], seed: str,
            base_weights: dict[str, int]) -> dict[str, dict]:
    """What each location's groups mean to spend this quarter, and on which kinds of goods.

    Each group: (what it earned last quarter, less its share of what the banks took) times
    how much of that its income level spends, plus a little of its savings; moved by how its
    mindset reacts to the news and by the location's mood; plus whatever it has just borrowed.
    Returns for each location: the total budget, the spending weights by sector, and each group's budget.
    """
    by_location: dict[str, list[dict]] = defaultdict(list)
    for g in groups:
        by_location[g["location"]].append(g)
    out = {}
    for location, household in world.households.items():
        mine = by_location.get(location, [])
        if not mine:
            out[location] = {"budget": 0, "weights": dict(base_weights), "groups": {}}
            continue
        # Money that reached the households after the last close (players' living costs, empire pay, and so on)
        # is shared out first, so the groups' savings are exactly the location's account when they decide.
        _line_up(mine, "cash", ledger.balance(conn, household["account_id"]))
        spends, dips = _habit_scales(mine, household)
        # Last quarter's income is shared by what each group earns; the banks' takings by what each owes.
        income = {g["id"]: g["income"] for g in mine}
        service = share_out(mine, location, debt_service.get(location, 0), {g["id"]: g["debt"] for g in mine})
        loans = share_out(mine, location, borrowed.get(location, 0),
                          {g["id"]: g["earns_bps"] * g.get("borrow_bps", BPS) // BPS for g in mine})
        mood = fortune_bps(seed, f"households:{location}", period, "mood", data.HOUSEHOLD_MOOD_BPS) + moods.get(location, 0)
        each: dict[int, int] = {}
        weights: dict[str, int] = defaultdict(int)
        for g in mine:
            disposable = max(income[g["id"]] - service.get(g["id"], 0), 0)
            new = loans.get(g["id"], 0)
            # (What it has just borrowed is already in its savings: it dips into the rest, and spends the loan below.)
            habit = apply_bps(disposable, spends[g["band"]]) + apply_bps(max(g["cash"] - new, 0), dips[g["band"]])
            budget = max(apply_bps(apply_bps(habit, g.get("spend_bps", BPS)), BPS + mood), 0) + new
            each[g["id"]] = budget
            g["_service"], g["_loan"] = service.get(g["id"], 0), new
            for sector, base in base_weights.items():
                weights[sector] += budget * g["tastes"].get(sector, BPS) // BPS * base // max(sum(base_weights.values()), 1)
        out[location] = {"budget": sum(each.values()), "weights": dict(weights), "groups": each}
    return out


def settle(conn: Connection, groups: list[dict], world, period: int, plans: dict[str, dict],
           spent: dict[str, int]) -> None:
    """After the quarter: each group's income, spending, savings and debts, put back in line with the
    ledger and the banks' records to the kobo. Then a few groups may move, and the record is written."""
    income_now = {r["location"]: r["income"] for r in _rows(
        conn, "SELECT location, income FROM household_results WHERE period = %s", (period,))}
    debt_now = {r["location"]: int(r["total"]) for r in _rows(
        conn, "SELECT location, coalesce(sum(principal), 0) AS total FROM household_debts GROUP BY location")}
    by_location: dict[str, list[dict]] = defaultdict(list)
    for g in groups:
        by_location[g["location"]].append(g)
    for location, household in world.households.items():
        mine = by_location.get(location, [])
        if not mine:
            continue
        plan = plans.get(location, {"budget": 0, "groups": {}})
        # What was actually spent, shared in proportion to what each meant to spend.
        paid = share_out(mine, location, spent.get(location, 0), plan["groups"])
        earned = share_out(mine, location, income_now.get(location, 0), {g["id"]: g["earns_bps"] for g in mine})
        for g in mine:
            g["spending"] = paid.get(g["id"], 0)
            g["income"] = earned.get(g["id"], 0)
            # (Its savings when it decided already held this quarter's loan and had paid the banks.)
            g["cash"] = max(g["cash"] + g["income"] - g["spending"], 0)
            # Debts: what was owed, less its share of what was repaid, plus what it borrowed. Put in line below.
            g["debt"] = max(g["debt"] - g.get("_service", 0) // 2 + g.get("_loan", 0), 0)
        _line_up(mine, "cash", ledger.balance(conn, household["account_id"]))
        _line_up(mine, "debt", debt_now.get(location, 0))
    _save(conn, groups)


def _line_up(groups: list[dict], key: str, total: int) -> None:
    """Scale the groups' figures so that they add up exactly to `total`, keeping their proportions."""
    current = sum(g[key] for g in groups)
    if current <= 0:
        weights = [g["earns_bps"] for g in groups]
    else:
        weights = [g[key] for g in groups]
    shares = _counts(max(total, 0), weights) if sum(weights) else [0] * len(groups)
    for g, value in zip(groups, shares):
        g[key] = value


def _save(conn: Connection, groups: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE consumer_groups SET location = %s, cash = %s, debt = %s, income = %s, spending = %s, moved_period = %s"
            " WHERE id = %s",
            [(g["location"], g["cash"], g["debt"], g["income"], g["spending"], g.get("moved_period"), g["id"]) for g in groups])


def move_weights(here: str, places: list[str], population: dict[str, int], growth: dict[str, int]) -> dict[str, int]:
    """Where a group thinking of moving goes: every place, its own included, by its share of the people,
    and more to places where jobs grow faster than at home."""
    return {p: population.get(p, 0) * max(BPS + (growth[p] - growth[here]) * data.GROUP_MOVE_TOWARD_JOBS_BPS // 100, 1000)
            for p in places}


def move(conn: Connection, groups: list[dict], world, period: int, seed: str) -> dict[tuple[str, str], int]:
    """A few groups move to another location: now and then by themselves, more often towards
    locations where jobs are growing faster. Their savings are paid across and their debts go with them.
    Returns how many moved, by (from, to)."""
    jobs = {}
    for r in _rows(conn, "SELECT location, period, jobs FROM household_results WHERE period IN (%s, %s)", (period, period - 1)):
        jobs.setdefault(r["location"], {})[r["period"]] = r["jobs"]
    growth = {}
    for location in world.households:
        now, before = jobs.get(location, {}).get(period), jobs.get(location, {}).get(period - 1)
        growth[location] = (now - before) * BPS // before if now and before and period > 1 else 0
    places = list(world.households)
    population = {r["name"]: r["population_bps"] for r in _rows(conn, "SELECT name, population_bps FROM locations")}
    national = sum(growth[p] * population.get(p, 0) for p in places) // BPS
    movers = []
    for g in groups:
        here = g["location"]
        # Groups where jobs grow slower than in the country as a whole move a little more often.
        chance = data.GROUP_MOVE_BPS + max(national - growth[here], 0) * data.GROUP_MOVE_PER_JOBS_BPS // 100
        draw = _uniform(seed, f"move:{g['id']}", period)
        if draw >= chance / BPS:
            continue
        # Where to: every place, its own included, in proportion to its people, and places where jobs grow faster
        # draw more. Drawing its own place means it stays. (So as many move from A to B as from B to A, on average,
        # and only differences in jobs tip the balance: the shares of the population do not drift by themselves.)
        weights = move_weights(here, places, population, growth)
        pick = _uniform(seed, f"move-to:{g['id']}", period) * sum(weights.values())
        chosen = here
        for p, w in weights.items():
            pick -= w
            if pick < 0:
                chosen = p
                break
        if chosen != here:
            movers.append((draw, g, chosen))
    movers.sort(key=lambda m: m[0])
    moved: dict[tuple[str, str], int] = defaultdict(int)
    label = clock.period_label(period)
    for _, g, to in movers[: data.GROUP_MOVES_MOST]:
        # (Read afresh for each move: an earlier move this quarter may have brought debts here.)
        debts = _rows(conn, "SELECT bank_company_id, location, principal FROM household_debts WHERE principal > 0")
        owed = defaultdict(int)
        for d in debts:
            owed[d["location"]] += d["principal"]
        here = g["location"]
        if g["cash"] > 0:
            g["cash"] = ledger.pay_up_to(
                conn, payer=world.households[here]["account_id"], receiver=world.households[to]["account_id"],
                wanted=g["cash"], kind="household_move",
                memo=f"Households moving from {here} to {to}, {label}", period=period)
        if g["debt"] > 0 and owed[here] > 0:
            # Its debts go with it: the same share of each bank's loans in the old location.
            share = min(g["debt"], owed[here])
            for d in [d for d in debts if d["location"] == here and d["principal"] > 0]:
                part = d["principal"] * share // owed[here]
                if part <= 0:
                    continue
                conn.execute("UPDATE household_debts SET principal = principal - %s WHERE bank_company_id = %s AND location = %s",
                             (part, d["bank_company_id"], here))
                conn.execute(
                    "INSERT INTO household_debts (bank_company_id, location, principal) VALUES (%s, %s, %s)"
                    " ON CONFLICT (bank_company_id, location) DO UPDATE SET principal = household_debts.principal + EXCLUDED.principal",
                    (d["bank_company_id"], to, part))
                d["principal"] -= part
        g["location"], g["moved_period"] = to, period
        moved[(here, to)] += 1
    for (here, to), n in moved.items():
        conn.execute("INSERT INTO consumer_moves (period, from_location, to_location, groups) VALUES (%s, %s, %s, %s)",
                     (period, here, to, n))
    if moved:
        # The people go with the groups: each location's share of the population follows its groups.
        counts = defaultdict(int)
        for g in groups:
            counts[g["location"]] += 1
        locations = [r["name"] for r in _rows(conn, "SELECT name FROM locations ORDER BY sort_order")]
        shares = _counts(BPS, [counts[name] for name in locations])
        for name, share in zip(locations, shares):
            conn.execute("UPDATE locations SET population_bps = %s WHERE name = %s", (share, name))
        # Each location's mix of mindsets follows its groups too.
        for location, mix in mindset_mix(groups).items():
            for mindset, share in mix.items():
                conn.execute("UPDATE household_mindsets SET share_bps = %s WHERE location = %s AND mindset = %s",
                             (share, location, mindset))
        # Savings and debts are lined up again with the ledger in their new homes.
        by_location: dict[str, list[dict]] = defaultdict(list)
        for g in groups:
            by_location[g["location"]].append(g)
        debt_now = {r["location"]: int(r["total"]) for r in _rows(
            conn, "SELECT location, coalesce(sum(principal), 0) AS total FROM household_debts GROUP BY location")}
        for location, mine in by_location.items():
            _line_up(mine, "cash", ledger.balance(conn, world.households[location]["account_id"]))
            _line_up(mine, "debt", debt_now.get(location, 0))
        _save(conn, groups)
    return dict(moved)


def record(conn: Connection, period: int) -> None:
    """Write down the groups, added up by location, income level and mindset."""
    conn.execute(
        "INSERT INTO consumer_results (period, location, band, mindset, groups, income, spending, cash, debt)"
        " SELECT %s, location, band, mindset, count(*), sum(income), sum(spending), sum(cash), sum(debt)"
        " FROM consumer_groups GROUP BY location, band, mindset", (period,))


def quarter(conn: Connection, world, period: int, seed: str, plans: dict[str, dict], spent: dict[str, int],
            groups: list[dict]) -> dict[tuple[str, str], int]:
    """Everything after the spending: settle each group, let a few move, and write the record."""
    settle(conn, groups, world, period, plans, spent)
    moved = move(conn, groups, world, period, seed)
    record(conn, period)
    return moved


# ---------------------------------------------------------------------------
# What players may see: only added up
# ---------------------------------------------------------------------------

def public_summary(conn: Connection, period: int) -> dict:
    """The groups added up for the Economy page: spending by income level and by mindset, and how
    many groups moved. Never one group's figures."""
    rows = _rows(conn, "SELECT band, mindset, location, groups, income, spending, cash, debt FROM consumer_results WHERE period = %s",
                 (period,))
    bands = {b: {"band": b, "name": data.INCOME_BAND_NAMES[b], "groups": 0, "income": 0, "spending": 0, "cash": 0, "debt": 0}
             for b in data.INCOME_BANDS}
    minds = {m: {"mindset": m, "groups": 0, "spending": 0} for m in data.MINDSETS}
    for r in rows:
        b = bands[r["band"]]
        for k in ("groups", "income", "spending", "cash", "debt"):
            b[k] += r[k]
        minds[r["mindset"]]["groups"] += r["groups"]
        minds[r["mindset"]]["spending"] += r["spending"]
    moves = _rows(conn, "SELECT from_location, to_location, groups FROM consumer_moves WHERE period = %s ORDER BY groups DESC, from_location",
                  (period,))
    history = _rows(conn, "SELECT period, sum(groups)::int AS groups FROM consumer_moves GROUP BY period ORDER BY period")
    return {"period": period, "bands": list(bands.values()), "mindsets": list(minds.values()),
            "moves": moves, "moved": sum(m["groups"] for m in moves),
            "moved_history": history}
