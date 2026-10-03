"""Players as professionals (design document, sections 7 and 10).

A player chooses a build (their profession), is hired by a company, and is paid a salary each
quarter by that company, out of the company's own cash. About 40% of the salary is taken
automatically: income tax to the Government, living costs to the households of the city they
work in, and their own saving for retirement. They choose one of the six banks, which pays
interest on the cash they leave with it. Their level comes from the work they finish.

Nothing here makes money. A player's salary is carved out of the wage bill their employer
already pays: the player takes the place of one computer-run member of staff.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

BUILDS = {
    "asset_manager": {
        "name": "Asset Manager", "accent": "violet", "track": "Investment management",
        "work": "Build and rebalance portfolios, analyse shares and bonds, and trade.",
        "earns": "Salary, and performance pay on portfolio results.",
        "cannot": "Replace a Risk Manager's assessment where an objective requires one.",
        "employers": ("banking", "insurance"),
        "employer_words": "the banks and the insurers, which run investment desks",
    },
    "accountant": {
        "name": "Accountant", "accent": "green", "track": "Accountancy",
        "work": "Statements, budgets, tax, audit, controls and investigation.",
        "earns": "Salary, and fees for audit and investigation work.",
        "cannot": "Decide legal guilt or publish an accusation.",
        "employers": None,                                   # every company keeps accounts
        "employer_words": "every company: each one keeps accounts",
    },
    "investment_banker": {
        "name": "Investment Banker", "accent": "purple", "track": "Investment banking",
        "work": "Takeovers, share and bond issues, valuation, restructuring and negotiation.",
        "earns": "Salary, deal fees and financing bonuses.",
        "cannot": "Verify the accounts or sign off the risk.",
        "employers": ("banking",),
        "employer_words": "the banks, which arrange deals and raise money for companies",
    },
    "risk_manager": {
        "name": "Risk Manager", "accent": "orange", "track": "Risk management",
        "work": "Market, credit, liquidity and operational risk; stress tests; exposure limits.",
        "earns": "Salary, and bonuses for risk performance and crisis work.",
        "cannot": "Carry out the legal or financial action that fixes a risk.",
        "employers": ("banking", "insurance"),
        "employer_words": "the banks and the insurers, whose business is carrying risk",
    },
    "lawyer": {
        "name": "Lawyer", "accent": "red", "track": "Law",
        "work": "Contracts, due diligence, title checks, litigation and regulatory filings.",
        "earns": "Salary, legal fees, and case and transaction bonuses.",
        "cannot": "Change the financial terms of a deal.",
        "employers": None,
        "employer_words": "every company: each one keeps lawyers",
    },
    "journalist": {
        "name": "Journalist", "accent": "blue", "track": "Journalism and research",
        "work": "Reporting, investigation, source work, and economic and company research.",
        "earns": "Salary from a media house, and bonuses for publication and investigation.",
        "cannot": "Declare someone guilty or change market data.",
        "employers": ("media",),
        "employer_words": "the media houses",
        "staff_per_opening": 100,
    },
}
# A new player cannot choose CEO: it is earned by rising through one of the six.
LATER_BUILDS: tuple = ()


class CareerError(Exception):
    """A request about a career that the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _event(conn: Connection, player_id, build, kind: str, words: str, now: datetime) -> None:
    conn.execute("INSERT INTO career_events (player_id, build, kind, words, at) VALUES (%s, %s, %s, %s, %s)",
                 (player_id, build, kind, words, now))


# ---------------------------------------------------------------------------
# Levels and pay
# ---------------------------------------------------------------------------

def experience_for(level: int) -> int:
    """The experience needed to reach a level."""
    return data.LEVEL_EXPERIENCE * level * (level - 1)


def level_for(experience: int) -> int:
    level = 1
    while level < data.LEVEL_CAP and experience >= experience_for(level + 1):
        level += 1
    return level


def level_words(level: int) -> str:
    for top, words in ((20, "Foundational competence"), (40, "Standard professional work and basic specialisation"),
                       (60, "Advanced competence and meaningful independence"), (70, "Advanced capabilities and stronger execution"),
                       (80, "Elite capabilities"), (90, "Master-level work"), (100, "Legendary mastery")):
        if level <= top:
            return words
    return "Legendary mastery"


def salary_per_quarter(level: int, wage_index_bps: int = BPS) -> int:
    """A quarter's salary before anything is taken, in kobo. Three game months make a quarter."""
    points = data.SALARY_PER_MONTH_NAIRA
    level = min(max(level, points[0][0]), points[-1][0])
    monthly = points[-1][1]
    for (low, pay_low), (high, pay_high) in zip(points, points[1:]):
        if level <= high:
            # Pay rises by the same proportion with each level between two points of the scale.
            monthly = round(pay_low * (pay_high / pay_low) ** ((level - low) / (high - low)) / 1000) * 1000
            break
    return apply_bps(naira(monthly * 3), wage_index_bps)


def split_salary(gross: int) -> dict:
    """What is taken from a salary, and what is left."""
    pension = apply_bps(gross, data.PENSION_EMPLOYEE_BPS)
    tax = apply_bps(gross, data.SALARY_TAX_BPS)
    living = apply_bps(gross, data.SALARY_LIVING_BPS)
    return {"gross": gross, "pension_yours": pension, "tax": tax, "living_costs": living,
            "take_home": gross - pension - tax - living, "pension_employer": apply_bps(gross, data.PENSION_EMPLOYER_BPS)}


def world_now(conn: Connection, now: datetime) -> dict:
    """The running quarter, the game day in it, and what a worker is paid against the start of the game.

    The quarter is the one the clock says is running. In the moments after a quarter has ended and
    before it has been closed, that is already the next one: nobody can join, move bank or hand
    work in "for" a quarter that is over.
    """
    world = _one(conn, "SELECT world_start, weeks_ahead, last_closed_period FROM world_state")
    if world is None:
        raise CareerError("The world has not been created yet.")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    date = clock.game_date(now, start)
    economy = _one(conn, "SELECT wage_index_bps, next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return {
        "period": max(world["last_closed_period"], clock.periods_completed(now, start)) + 1,
        "day": date.day_of_quarter if date else 1,
        "started": date is not None,
        "wage_index_bps": economy["wage_index_bps"] if economy else BPS,
        "policy_rate_bps": economy["next_policy_rate_bps"] if economy else data.OPENING_RATE_BPS,
    }


def books_open(conn: Connection, now: datetime) -> None:
    """Refuse a change in the moments after a quarter has ended and before its books are closed.
    Otherwise somebody could act knowing how the quarter ended, or lose pay they had earned."""
    world = _one(conn, "SELECT world_start, weeks_ahead, last_closed_period FROM world_state FOR SHARE")
    if world and clock.periods_completed(now, clock.effective_start(world["world_start"], world["weeks_ahead"])) > world["last_closed_period"]:
        raise CareerError("The quarter has just ended and its books are being closed. Try again in a minute.")


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def career(conn: Connection, player_id, build: str | None = None, *, lock: bool = False) -> dict | None:
    """A player's career in their present build (or the one named)."""
    if build is None:
        player = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
        build = player and player["build"]
    if build is None:
        return None
    row = _one(conn, "SELECT * FROM careers WHERE player_id = %s AND build = %s" + (" FOR UPDATE" if lock else ""),
               (player_id, build))
    if row:
        row["level"] = level_for(row["experience"])
    return row


def choose_build(conn: Connection, player_id, build: str, now: datetime) -> None:
    """Choose a build, or change to another. A player may change once in a real month and hold
    up to three builds; each keeps its own level. Changing build means leaving the present job."""
    if build not in BUILDS:
        raise CareerError("That build does not open until a later stage of the game.")
    with conn.transaction():
        books_open(conn, now)
        player = _one(conn, "SELECT id, build, build_changed_at FROM players WHERE id = %s FOR UPDATE", (player_id,))
        if player["build"] == build:
            return
        held = [r["build"] for r in _rows(conn, "SELECT build FROM careers WHERE player_id = %s", (player_id,))]
        if player["build"] is not None:
            wait = player["build_changed_at"] + timedelta(days=data.BUILD_CHANGE_DAYS)
            if now < wait:
                raise CareerError(f"A build can be changed once in a real month. You can change again on "
                                  f"{clock.to_lagos(wait):%d %B %Y}.")
            if build not in held and len(held) >= data.MAX_BUILDS:
                raise CareerError(f"A player may hold up to {data.MAX_BUILDS} builds.")
            if _one(conn, "SELECT 1 FROM objectives WHERE player_id = %s AND state = 'active'", (player_id,)):
                raise CareerError("Finish or give up the work you have taken on before changing build.")
            _leave(conn, player_id, now, "changed build")
        conn.execute("INSERT INTO careers (player_id, build, started_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (player_id, build, now))
        conn.execute("UPDATE players SET build = %s, build_changed_at = %s WHERE id = %s", (build, now, player_id))
        conn.execute("INSERT INTO retirement_accounts (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player_id,))
        _event(conn, player_id, build, "build_chosen", f"Chose the {BUILDS[build]['name']} build.", now)


def add_experience(conn: Connection, player_id, build: str, amount: int, now: datetime) -> dict:
    """Add experience from finished work. Returns the level before and after."""
    row = career(conn, player_id, build, lock=True)
    before = row["level"]
    after = level_for(row["experience"] + amount)
    conn.execute("UPDATE careers SET experience = experience + %s WHERE player_id = %s AND build = %s", (amount, player_id, build))
    for level in range(before + 1, after + 1):
        _event(conn, player_id, build, "level_up", f"Reached Level {level} as {_a(BUILDS[build]['name'])}.", now)
    return {"before": before, "after": after}


def _a(name: str) -> str:
    return ("an " if name[0] in "AEIOU" else "a ") + name


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def _employers(conn: Connection, build: str) -> list[dict]:
    """The companies that hire a build, as their latest filed accounts show them. (Only what is
    filed is used: what a player sees of an employer is what anybody can see.)"""
    sectors = BUILDS[build]["employers"]
    return _rows(
        conn,
        "SELECT c.id, c.ticker, c.name, c.headquarters, c.account_id, s.name AS sector, r.credit_rating AS rating,"
        "   coalesce((r.figures->'notes'->>'staff')::bigint, 0) AS staff,"
        "   (r.figures->'balance_sheet'->>'payables')::bigint AS payables,"
        "   coalesce((r.figures->'notes'->>'principal_overdue')::bigint, 0) AS principal_overdue,"
        "   (r.figures->'balance_sheet'->>'cash')::bigint AS cash,"
        "   (SELECT count(*) FROM employments e WHERE e.company_id = c.id AND e.ended_at IS NULL) AS players"
        " FROM companies c JOIN sectors s ON s.code = c.sector"
        " JOIN LATERAL (SELECT figures, credit_rating FROM company_reports p WHERE p.company_id = c.id"
        "               ORDER BY p.period DESC, p.version DESC LIMIT 1) r ON true"
        " WHERE (%s::text[] IS NULL OR c.sector = ANY(%s)) ORDER BY c.name",
        (list(sectors) if sectors else None, list(sectors) if sectors else None))


def _places(employer: dict, build: str) -> int:
    """How many players a company will take. The media houses are small, so they take one for every 100 staff."""
    return max(employer["staff"] // BUILDS[build].get("staff_per_opening", data.STAFF_PER_OPENING), 1)


def openings(conn: Connection, player_id, now: datetime) -> list[dict]:
    """Every employer that hires the player's build, and whether it has a place."""
    mine = career(conn, player_id)
    if mine is None:
        return []
    state = world_now(conn, now)
    pay = split_salary(salary_per_quarter(mine["level"], state["wage_index_bps"]))
    job = current_job(conn, player_id)
    out = []
    for employer in _employers(conn, mine["build"]):
        places = _places(employer, mine["build"])
        out.append({
            "ticker": employer["ticker"], "name": employer["name"], "sector": employer["sector"],
            "headquarters": employer["headquarters"], "rating": employer["rating"],
            "places_left": max(places - employer["players"], 0),
            "behind_on_bills": employer["payables"] > 0 or employer["principal_overdue"] > 0 or employer["cash"] <= 0,
            "gross": pay["gross"], "take_home": pay["take_home"],
            "yours": bool(job and job["company_id"] == employer["id"]),
        })
    return out


def current_job(conn: Connection, player_id) -> dict | None:
    return _one(conn, "SELECT e.*, c.name, c.ticker, c.headquarters, c.account_id FROM employments e"
                      " JOIN companies c ON c.id = e.company_id WHERE e.player_id = %s AND e.ended_at IS NULL", (player_id,))


def take_job(conn: Connection, player_id, ticker: str, now: datetime) -> dict:
    """Be hired by a company. A computer-run employer takes anybody of the right build while it
    has a place. The player must have chosen a bank first: the employer needs to know where to pay."""
    with conn.transaction():
        books_open(conn, now)
        player = _one(conn, "SELECT id, build FROM players WHERE id = %s FOR UPDATE", (player_id,))
        if player["build"] is None:
            raise CareerError("Choose a build first.")
        if current_bank(conn, player_id) is None:
            raise CareerError("Choose your bank first: your employer needs to know where to pay you.")
        state = world_now(conn, now)
        # Lock the employer, so that two people cannot take its last place at the same moment.
        company = _one(conn, "SELECT id, name, ticker, sector FROM companies WHERE ticker = %s FOR UPDATE", (ticker,))
        employer = next((e for e in _employers(conn, player["build"]) if e["ticker"] == ticker), None)
        if company is None or employer is None:
            raise CareerError(f"That company does not hire {BUILDS[player['build']]['name']}s.")
        job = current_job(conn, player_id)
        if job and job["company_id"] == company["id"]:
            return job
        if employer["players"] >= _places(employer, player["build"]):
            raise CareerError(f"{company['name']} has no place open at the moment.")
        if job:
            if job["started_period"] == state["period"]:
                raise CareerError("You started your present job this quarter. You can move after the quarter ends.")
            if _one(conn, "SELECT 1 FROM objectives WHERE player_id = %s AND state = 'active'", (player_id,)):
                raise CareerError("Finish or give up the work you have taken on before moving to another employer.")
            _leave(conn, player_id, now, "moved to another employer")
        elif _one(conn, "SELECT 1 FROM employments WHERE player_id = %s AND ended_period = %s", (player_id, state["period"])):
            raise CareerError("You left a job this quarter. You can start another after the quarter ends.")
        conn.execute(
            "INSERT INTO employments (player_id, company_id, build, started_at, started_period, started_day)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (player_id, company["id"], player["build"], now, state["period"], state["day"]))
        _event(conn, player_id, player["build"], "hired",
               f"Hired by {company['name']} as {_a(BUILDS[player['build']]['name'])}.", now)
        return current_job(conn, player_id)


def _leave(conn: Connection, player_id, now: datetime, reason: str) -> None:
    job = current_job(conn, player_id)
    if job is None:
        return
    state = world_now(conn, now)
    conn.execute("UPDATE employments SET ended_at = %s, ended_period = %s, ended_reason = %s WHERE id = %s",
                 (now, state["period"], reason, job["id"]))
    _event(conn, player_id, job["build"], "left_job", f"Left {job['name']}: {reason}.", now)


def leave_job(conn: Connection, player_id, now: datetime) -> None:
    """Resign. Pay for the quarter in hand is lost: an employer pays whoever is on its staff on pay day."""
    with conn.transaction():
        books_open(conn, now)
        _one(conn, "SELECT id FROM players WHERE id = %s FOR UPDATE", (player_id,))
        if _one(conn, "SELECT 1 FROM objectives WHERE player_id = %s AND state = 'active'", (player_id,)):
            raise CareerError("Finish or give up the work you have taken on before leaving your job.")
        _leave(conn, player_id, now, "resigned")


# ---------------------------------------------------------------------------
# Pay day. Called by the company engine while a company closes its quarter.
# ---------------------------------------------------------------------------

def has_worked(conn: Connection, player_id, period: int) -> bool:
    """Did the player finish a real piece of work that counts in this quarter? Work passed counts.
    So does work that was not passed but earned at least one of its milestones: an honest attempt.
    A blank sheet, work given up and work never done do not."""
    return _one(conn, "SELECT 1 FROM objectives WHERE player_id = %s AND judged_period = %s AND (state = 'passed'"
                      " OR (state = 'failed' AND coalesce((result->>'score')::int, 0) > 0)) LIMIT 1", (player_id, period)) is not None


def salaries_due(conn: Connection, company: dict, period: int, wage_index_bps: int, budget: int) -> list[dict]:
    """What a company owes the players on its staff for the quarter being closed.

    No work, no pay: a player who finished no real piece of work since the last pay day is paid
    nothing for the quarter (see has_worked). A player who started part-way through is paid for
    the days worked. Players' pay can never be more than `budget`, a part of the company's wage bill: if it
    would be, everybody's is cut by the same proportion. (The number of places a company has
    keeps it far below that; this is the backstop.)
    """
    packets = []
    grosses = []
    for job in _rows(conn, "SELECT e.*, a.id AS player_account FROM employments e"
                           " JOIN ledger_accounts a ON a.player_id = e.player_id"
                           " WHERE e.company_id = %s AND e.ended_at IS NULL AND e.started_period <= %s"
                           " AND NOT EXISTS (SELECT 1 FROM payslips p WHERE p.player_id = e.player_id AND p.period = %s)"
                           " ORDER BY e.id", (company["id"], period, period)):
        mine = career(conn, job["player_id"], job["build"])
        days = clock.GAME_DAYS_PER_QUARTER - job["started_day"] + 1 if job["started_period"] == period else clock.GAME_DAYS_PER_QUARTER
        worked = has_worked(conn, job["player_id"], period)
        gross = salary_per_quarter(mine["level"], wage_index_bps) * days // clock.GAME_DAYS_PER_QUARTER if worked else 0
        grosses.append(gross)
        packets.append({"player_id": job["player_id"], "account": job["player_account"],
                        "employment_id": job["id"], "build": job["build"], "level": mine["level"],
                        "days_worked": days, "worked": worked})
    total = sum(grosses)
    if total > budget > 0:
        grosses = [gross * budget // total for gross in grosses]
    elif total > budget:
        grosses = [0 for _ in grosses]
    return [{**split_salary(gross), **packet} for gross, packet in zip(grosses, packets)]


def pay_salaries(conn: Connection, company: dict, households, treasury, packets: list[dict], period: int, owe) -> int:
    """Pay the players on a company's staff, and write their payslips. Returns what was due in cash
    (everything but the retirement saving, which goes to the pension funds with everybody else's).

    The company pays three ways at once: take-home pay to the player, income tax to the
    Government, and the player's living costs to the households of the city they work in.
    If it cannot pay in full, each is paid the same proportion and the rest stays owed.
    """
    total = 0
    for packet in packets:
        amounts = {packet["account"]: packet["take_home"], treasury: packet["tax"], households: packet["living_costs"]}
        got: dict = {}
        ledger.pay_split_up_to(
            conn, payer=company["account_id"], amounts=amounts, kind="salary", period=period, paid_to=got,
            memo=f"{company['name']}: salary, {clock.period_label(period)}", reference=f"salary:{packet['player_id']}:{period}")
        for receiver, due in amounts.items():
            unpaid = due - got.get(UUID(str(receiver)), 0)
            if unpaid > 0:
                owe(conn, company, receiver, "salary", unpaid, period)
        paid = got.get(UUID(str(packet["account"])), 0)
        note = ""
        if not packet["worked"]:
            note = "No pay this quarter: you finished no piece of work since the last pay day."
        elif paid < packet["take_home"]:
            note = f"{company['name']} could not pay all of it. The rest is still owed to you and is paid when it has the cash."
        elif packet["days_worked"] < clock.GAME_DAYS_PER_QUARTER:
            note = f"You started part-way through the quarter: paid for {packet['days_worked']} of 90 days."
        conn.execute(
            "INSERT INTO payslips (player_id, period, employment_id, company_id, build, level, days_worked, worked, gross,"
            " pension_yours, pension_employer, tax, living_costs, take_home, paid, owed, note)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (packet["player_id"], period, packet["employment_id"], company["id"], packet["build"], packet["level"],
             packet["days_worked"], packet["worked"], packet["gross"], packet["pension_yours"], packet["pension_employer"],
             packet["tax"], packet["living_costs"], packet["take_home"], paid, packet["take_home"] - paid, note))
        total += sum(amounts.values())
    return total


# ---------------------------------------------------------------------------
# The player's bank
# ---------------------------------------------------------------------------

def savings_rate_bps(policy_rate_bps: int, rating: str | None) -> int:
    """What a bank pays in a year on cash left with it."""
    return apply_bps(policy_rate_bps, data.SAVINGS_RATE_SHARE_BPS.get(rating or "BBB", 3300))


def banks(conn: Connection, player_id, now: datetime) -> list[dict]:
    state = world_now(conn, now)
    mine = current_bank(conn, player_id)
    out = []
    for bank in _rows(
            conn,
            "SELECT c.id, c.ticker, c.name, c.headquarters,"
            "   (SELECT p.credit_rating FROM company_reports p WHERE p.company_id = c.id ORDER BY p.period DESC, p.version DESC LIMIT 1) AS rating,"
            "   (SELECT count(*) FROM bank_customers b WHERE b.company_id = c.id AND b.ended_at IS NULL) AS customers"
            " FROM companies c WHERE c.ticker = ANY(%s) ORDER BY c.name", (list(data.PLAYER_BANKS),)):
        out.append({"ticker": bank["ticker"], "name": bank["name"], "headquarters": bank["headquarters"], "rating": bank["rating"],
                    "savings_rate_bps": savings_rate_bps(state["policy_rate_bps"], bank["rating"]),
                    "yours": bool(mine and mine["company_id"] == bank["id"])})
    return out


def current_bank(conn: Connection, player_id) -> dict | None:
    return _one(conn, "SELECT b.*, c.name, c.ticker, c.account_id FROM bank_customers b JOIN companies c ON c.id = b.company_id"
                      " WHERE b.player_id = %s AND b.ended_at IS NULL", (player_id,))


def choose_bank(conn: Connection, player_id, ticker: str, now: datetime) -> dict:
    """Choose a bank, or move to another. A player may move once in a game quarter."""
    if ticker not in data.PLAYER_BANKS:
        raise CareerError("Choose one of the six banks.")
    with conn.transaction():
        books_open(conn, now)
        _one(conn, "SELECT id FROM players WHERE id = %s FOR UPDATE", (player_id,))
        state = world_now(conn, now)
        bank = _one(conn, "SELECT id, name FROM companies WHERE ticker = %s", (ticker,))
        mine = current_bank(conn, player_id)
        if mine and mine["company_id"] == bank["id"]:
            return mine
        if mine:
            if mine["since_period"] == state["period"]:
                raise CareerError("You joined your present bank this quarter. You can move after the quarter ends.")
            conn.execute("UPDATE bank_customers SET ended_at = %s WHERE id = %s", (now, mine["id"]))
        conn.execute("INSERT INTO bank_customers (player_id, company_id, since, since_period) VALUES (%s, %s, %s, %s)",
                     (player_id, bank["id"], now, state["period"]))
        build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
        _event(conn, player_id, build, "bank_chosen",
               f"Moved to {bank['name']}." if mine else f"Opened an account at {bank['name']}.", now)
        return current_bank(conn, player_id)


def lowest_balance(conn: Connection, account, since: datetime | None) -> int:
    """The least cash an account has held at any moment since `since` (or ever)."""
    opening = 0
    if since is not None:
        opening = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e"
                             " JOIN ledger_transactions t ON t.id = e.transaction_id"
                             " WHERE e.account_id = %s AND e.asset = 'NGN' AND t.created_at <= %s", (account, since))["total"]
    lowest = running = opening
    for move in _rows(conn, "SELECT e.amount FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                            " WHERE e.account_id = %s AND e.asset = 'NGN' AND (%s::timestamptz IS NULL OR t.created_at > %s)"
                            " ORDER BY t.created_at, e.id", (account, since, since)):
        running += move["amount"]
        lowest = min(lowest, running)
    return max(lowest, 0)


def pay_deposit_interest(conn: Connection, bank: dict, period: int, policy_rate_bps: int, rating: str | None) -> int:
    """A bank pays interest to the players who bank with it, out of its own cash, as it closes its
    quarter. It pays on the least cash the player kept at any moment of the quarter, so money put in
    for a moment before pay day earns nothing. Returns what the bank paid."""
    rate = savings_rate_bps(policy_rate_bps, rating)
    last_close = _one(conn, "SELECT closed_at FROM money_watch_results WHERE period = %s", (period - 1,))
    paid_total = 0
    # Only a customer who was with the bank for the whole quarter is paid: one who joined or moved
    # during it starts earning from the next. So nothing is gained by moving bank on the last day.
    for customer in _rows(conn, "SELECT b.player_id, a.id AS account FROM bank_customers b"
                                " JOIN ledger_accounts a ON a.player_id = b.player_id"
                                " WHERE b.company_id = %s AND b.ended_at IS NULL AND b.since_period < %s"
                                " AND NOT EXISTS (SELECT 1 FROM deposit_interest d WHERE d.player_id = b.player_id AND d.period = %s)"
                                " ORDER BY b.id", (bank["id"], period, period)):
        since = last_close["closed_at"] if last_close else None
        lowest = lowest_balance(conn, customer["account"], since)
        amount = (lowest * rate + 2 * BPS) // (4 * BPS)
        paid = ledger.pay_up_to(
            conn, payer=bank["account_id"], receiver=customer["account"], wanted=amount, kind="deposit_interest", period=period,
            memo=f"{bank['name']}: interest on the cash you kept with it, {clock.period_label(period)}",
            reference=f"deposit:{customer['player_id']}:{period}") if amount > 0 else 0
        conn.execute("INSERT INTO deposit_interest (player_id, period, company_id, lowest_balance, rate_bps, amount)"
                     " VALUES (%s, %s, %s, %s, %s, %s)", (customer["player_id"], period, bank["id"], lowest, rate, paid))
        paid_total += paid
    return paid_total


# ---------------------------------------------------------------------------
# Retirement savings
# ---------------------------------------------------------------------------

def choose_fund(conn: Connection, player_id, fund: str, now: datetime) -> None:
    """Choose which kind of fund looks after the retirement savings. Once in a game year."""
    if fund not in data.PENSION_FUNDS:
        raise CareerError("Choose one of the four funds.")
    with conn.transaction():
        books_open(conn, now)
        state = world_now(conn, now)
        conn.execute("INSERT INTO retirement_accounts (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player_id,))
        account = _one(conn, "SELECT * FROM retirement_accounts WHERE player_id = %s FOR UPDATE", (player_id,))
        if account["fund"] == fund:
            return
        chosen = account["fund_chosen_period"]
        if chosen is not None and state["period"] - chosen < clock.QUARTERS_PER_YEAR:
            raise CareerError(f"A fund can be changed once in a game year. You can change again in "
                              f"{clock.period_label(chosen + clock.QUARTERS_PER_YEAR)}.")
        # The savings stay with the old fund until the quarter ends: nobody can pick a fund
        # for the quarter after seeing how the quarter went.
        conn.execute("UPDATE retirement_accounts SET fund = %s, fund_chosen_period = %s, previous_fund = %s WHERE player_id = %s",
                     (fund, state["period"], account["fund"], player_id))
        build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
        _event(conn, player_id, build, "fund_chosen", f"Moved retirement savings to the {data.PENSION_FUNDS[fund]['name']} fund.", now)


def close_retirement(conn: Connection, period: int, index_level: int, policy_rate_bps: int) -> None:
    """As a quarter closes: work out what each kind of fund earned, grow every player's savings by
    it, and add what they and their employer paid in this quarter.

    Shares earn what the BSX 50 did over the quarter; bonds earn a quarter of the Government's
    five-year rate; cash earns a quarter of its three-month rate. The manager's fee comes off.
    """
    from simulation import bonds
    before = _one(conn, "SELECT index_level FROM pension_fund_results WHERE period = %s LIMIT 1", (period - 1,))
    shares_bps = (index_level - before["index_level"]) * BPS // before["index_level"] if before and before["index_level"] else 0
    bonds_bps = bonds.government_yield_bps(policy_rate_bps, 20) // 4
    cash_bps = bonds.government_yield_bps(policy_rate_bps, 1) // 4
    returns = {}
    for fund, mix in data.PENSION_FUNDS.items():
        earned = (mix["shares"] * shares_bps + mix["bonds"] * bonds_bps + mix["cash"] * cash_bps) // BPS - data.PENSION_MANAGER_FEE_BPS
        returns[fund] = earned
        conn.execute("INSERT INTO pension_fund_results (period, fund, return_bps, index_level) VALUES (%s, %s, %s, %s)",
                     (period, fund, earned, index_level))
    for account in _rows(conn, "SELECT * FROM retirement_accounts ORDER BY player_id FOR UPDATE"):
        slip = _one(conn, "SELECT pension_yours, pension_employer, take_home, paid FROM payslips WHERE player_id = %s AND period = %s",
                    (account["player_id"], period))
        # The saving is credited in full for the quarter it was earned in. If the employer was short
        # of cash, what it could not pay to the pension funds stays owed to them, like any other bill.
        yours = slip["pension_yours"] if slip else 0
        employer = slip["pension_employer"] if slip else 0
        fund = account["previous_fund"] if account["fund_chosen_period"] == period and account["previous_fund"] else account["fund"]
        growth = max(apply_bps(account["value"], returns[fund]), -account["value"])
        closing = account["value"] + growth + yours + employer
        if closing == account["value"] and not slip:
            continue
        conn.execute("INSERT INTO retirement_entries (player_id, period, fund, opening, growth, paid_in_by_you, paid_in_by_employer, closing)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                     (account["player_id"], period, fund, account["value"], growth, yours, employer, closing))
        conn.execute("UPDATE retirement_accounts SET value = %s WHERE player_id = %s", (closing, account["player_id"]))


# ---------------------------------------------------------------------------
# What the player sees
# ---------------------------------------------------------------------------

def profile(conn: Connection, player_id, now: datetime) -> dict:
    """Everything about a player's working life, for their own eyes."""
    player = _one(conn, "SELECT id, display_name, reputation, build, build_changed_at FROM players WHERE id = %s", (player_id,))
    state = world_now(conn, now)
    mine = career(conn, player_id)
    out = {
        "build": None, "builds": [{"code": code, **{k: b[k] for k in ("name", "accent", "track", "work", "earns", "cannot", "employer_words")}}
                                  for code, b in BUILDS.items()],
        "later_builds": list(LATER_BUILDS), "reputation": player["reputation"],
        "can_change_build_at": None, "career": None, "job": None, "bank": None, "pay": None, "payslips": [],
        "retirement": None, "events": [], "next_pay_day": None, "interest": [],
    }
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    if now >= start:
        out["next_pay_day"] = clock.next_quarter_end(now, start)
    bank = current_bank(conn, player_id)
    if bank:
        rating = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1",
                      (bank["company_id"],))
        out["bank"] = {"ticker": bank["ticker"], "name": bank["name"], "since": bank["since"],
                       "savings_rate_bps": savings_rate_bps(state["policy_rate_bps"], rating and rating["credit_rating"]),
                       "can_move": bank["since_period"] < state["period"]}
    out["interest"] = _rows(conn, "SELECT d.period, c.name AS bank, d.lowest_balance, d.rate_bps, d.amount FROM deposit_interest d"
                                  " JOIN companies c ON c.id = d.company_id WHERE d.player_id = %s ORDER BY d.period DESC LIMIT 8", (player_id,))
    savings = _one(conn, "SELECT * FROM retirement_accounts WHERE player_id = %s", (player_id,))
    if savings:
        chosen = savings["fund_chosen_period"]
        out["retirement"] = {
            "fund": savings["fund"], "value": savings["value"],
            "can_change": chosen is None or state["period"] - chosen >= clock.QUARTERS_PER_YEAR,
            "funds": [{"code": code, "name": f["name"], "for": f["for"], "shares_bps": f["shares"], "bonds_bps": f["bonds"],
                       "cash_bps": f["cash"],
                       "last_return_bps": (_one(conn, "SELECT return_bps FROM pension_fund_results WHERE fund = %s ORDER BY period DESC LIMIT 1",
                                                (code,)) or {}).get("return_bps")}
                      for code, f in data.PENSION_FUNDS.items()],
            "entries": _rows(conn, "SELECT period, fund, opening, growth, paid_in_by_you, paid_in_by_employer, closing"
                                   " FROM retirement_entries WHERE player_id = %s ORDER BY period DESC LIMIT 8", (player_id,)),
        }
    if mine is None:
        return out
    build = BUILDS[mine["build"]]
    level = mine["level"]
    out["build"] = mine["build"]
    out["can_change_build_at"] = player["build_changed_at"] + timedelta(days=data.BUILD_CHANGE_DAYS)
    floor, ceiling = experience_for(level), experience_for(level + 1)
    out["career"] = {
        "build": mine["build"], "build_name": build["name"], "accent": build["accent"], "track": build["track"],
        "level": level, "level_words": level_words(level), "experience": mine["experience"],
        "level_floor": floor, "next_level_at": None if level >= data.LEVEL_CAP else ceiling,
        "at_cap": level >= data.LEVEL_CAP, "review_open": mine["review_open"], "review": review_standing(conn, player_id, mine),
        "other_builds": [{"build": r["build"], "name": BUILDS[r["build"]]["name"], "level": level_for(r["experience"])}
                         for r in _rows(conn, "SELECT build, experience FROM careers WHERE player_id = %s AND build <> %s",
                                        (player_id, mine["build"]))],
    }
    pay = split_salary(salary_per_quarter(level, state["wage_index_bps"]))
    next_pay = split_salary(salary_per_quarter(min(level + 1, data.LEVEL_CAP), state["wage_index_bps"]))
    job = current_job(conn, player_id)
    worked = has_worked(conn, player_id, state["period"])
    out["pay"] = {**pay, "at_next_level": next_pay["gross"], "worked_this_quarter": worked}
    if job:
        out["job"] = {"ticker": job["ticker"], "name": job["name"], "headquarters": job["headquarters"],
                      "since": job["started_at"], "can_move": job["started_period"] < state["period"],
                      "owed": _one(conn, "SELECT coalesce(sum(p.amount_outstanding), 0)::bigint AS owed FROM company_payables p"
                                         " JOIN ledger_accounts a ON a.id = p.payee_account_id WHERE a.player_id = %s AND p.kind = 'salary'",
                                   (player_id,))["owed"]}
    out["payslips"] = _rows(
        conn, "SELECT p.period, c.name AS employer, p.level, p.days_worked, p.worked, p.gross, p.pension_yours, p.pension_employer,"
              " p.tax, p.living_costs, p.take_home, p.paid, p.owed, p.note FROM payslips p JOIN companies c ON c.id = p.company_id"
              " WHERE p.player_id = %s ORDER BY p.period DESC LIMIT 8", (player_id,))
    out["events"] = _rows(conn, "SELECT kind, words, at FROM career_events WHERE player_id = %s ORDER BY id DESC LIMIT 20", (player_id,))
    return out


def review_standing(conn: Connection, player_id, mine: dict) -> dict | None:
    """Where a performance review stands, in words the player can act on."""
    if not mine["review_open"]:
        return None
    since = _rows(conn, "SELECT state FROM objectives WHERE player_id = %s AND build = %s AND judged_seq > %s",
                  (player_id, mine["build"], mine["review_from"] or 0))
    passes = sum(1 for o in since if o["state"] == "passed")
    return {
        "opened_at": mine["review_opened_at"], "finished": len(since), "passes": passes,
        "why": f"{data.REVIEW_FAILURES} of {data.REVIEW_WINDOW} pieces of work in a row were not passed.",
        "how_to_recover": f"Pass {data.REVIEW_PASSES_NEEDED} of your next {data.REVIEW_LENGTH} pieces of work and the review is closed. "
                          f"If you do not, you step down one level and start again from there.",
    }
