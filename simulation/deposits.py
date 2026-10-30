"""The crises stage, Part 1: money kept at real, named banks (owner's suggestion 2).

Until now a bank's savers were one fixed figure in its accounts. Now every naira kept at a bank is a claim on that
bank, written in the ledger as the bank's own deposit asset (DEP-<ticker>), one kobo a unit, issued by the bank:
what the bank owes its savers is exactly what it has put out.

  * Households keep the savings the banks already held for them, city by city. They do not touch them in calm
    times; when trust in a bank falls they draw them out (a run), put most of it the same day into the banks they
    trust most, and keep the rest at home until calm returns.
  * Players and empires can put money into savings at any of the six banks a player may use, and take it out again.
    Savings pay more than cash left in a current account, once a quarter, on the least kept through the whole
    quarter. But savings are a claim on the bank: if it fails, only the first ₦5 million at each bank is
    guaranteed.
  * Every saver's money at each bank is guaranteed up to ₦5 million by the Deposit Guarantee Fund, which the banks
    pay into every quarter. In a crisis the Government may promise that every saving is safe, whatever its size.

Paying in brings a claim into existence; paying out takes it away. Nothing else may create one. Every naira moves
through the ledger.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

GUARANTEE_FUND = "deposit_guarantee"


class SavingsError(Exception):
    """A saving the rules do not allow, with the reason in plain words."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('bank_deposits') IS NOT NULL AS ok")["ok"])


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def guarantee() -> int:
    return naira(data.DEPOSIT_GUARANTEE_NAIRA)


# ---------------------------------------------------------------------------
# Setting up: each bank's deposit asset, and the savers it already had
# ---------------------------------------------------------------------------

def setup(conn: Connection, period: int, now: datetime) -> None:
    """Write each bank's savers into the ledger, once. Safe to call at any time."""
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM world_state"):
        return
    if _one(conn, "SELECT 1 AS x FROM ledger_accounts WHERE code = %s", (GUARANTEE_FUND,)) is None:
        ledger.create_account(conn, kind="government", name="Deposit Guarantee Fund", code=GUARANTEE_FUND)
    conn.execute("INSERT INTO household_cash_held (location) SELECT name FROM locations ON CONFLICT DO NOTHING")
    waiting = _rows(conn, """
        SELECT c.id, c.ticker, c.name, c.account_id,
               (SELECT r.customer_funds FROM company_results r WHERE r.company_id = c.id ORDER BY r.period DESC LIMIT 1) AS funds
        FROM companies c WHERE c.sector = 'banking' AND NOT EXISTS (SELECT 1 FROM bank_deposits d WHERE d.company_id = c.id)
        ORDER BY c.ticker""")
    if not waiting:
        return
    homes = {r["location"]: r["account_id"] for r in _rows(conn, "SELECT location, account_id FROM households ORDER BY location")}
    population = {r["name"]: r["population_bps"] for r in _rows(conn, "SELECT name, population_bps FROM locations")}
    for bank in waiting:
        if not bank["funds"] or bank["funds"] <= 0:
            continue
        code = f"DEP-{bank['ticker']}"
        ledger.create_asset(conn, code=code, kind="deposit", name=f"Savings at {bank['name']}", unit="kobo",
                            issuer_account_id=bank["account_id"])
        # Each city's share follows where the bank lends to households; a bank that lends to none follows population.
        lent = {r["location"]: r["principal"] for r in _rows(conn, "SELECT location, principal FROM household_debts"
                                                                   " WHERE bank_company_id = %s AND principal > 0", (bank["id"],))}
        weights = {loc: lent.get(loc, 0) for loc in homes} if sum(lent.values()) > 0 else {loc: population.get(loc, 0) for loc in homes}
        total_weight = sum(weights.values()) or 1
        shares = {loc: bank["funds"] * w // total_weight for loc, w in weights.items()}
        biggest = max(shares, key=lambda k: shares[k])
        shares[biggest] += bank["funds"] - sum(shares.values())
        legs = [ledger.Leg(bank["account_id"], -bank["funds"], code)]
        legs += [ledger.Leg(homes[loc], amount, code) for loc, amount in shares.items() if amount > 0]
        ledger.post(conn, kind="deposit_record", legs=legs, period=period,
                    memo=f"{bank['name']}: the savings households already kept with it, written into the ledger")
        conn.execute("INSERT INTO bank_deposits (company_id, asset, recorded_period, at) VALUES (%s, %s, %s, %s)",
                     (bank["id"], code, period, now))
        for loc, amount in shares.items():
            if amount <= 0:
                continue
            conn.execute("INSERT INTO household_deposits_covered (company_id, location, covered) VALUES (%s, %s, %s)"
                         " ON CONFLICT (company_id, location) DO UPDATE SET covered = EXCLUDED.covered",
                         (bank["id"], loc, apply_bps(amount, data.HOUSEHOLD_COVERED_BPS)))
            _flow(conn, bank["id"], homes[loc], "households", loc, "recorded", amount, period, 0, now)


def _flow(conn: Connection, company_id, account, holder: str, location, kind: str, amount: int, period: int, day: int,
          now: datetime | None) -> None:
    if amount > 0:
        conn.execute("INSERT INTO deposit_flows (company_id, account_id, holder, location, kind, amount, period, day, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()))",
                     (company_id, account, holder, location, kind, amount, period, day, now))


# ---------------------------------------------------------------------------
# Banks and what they owe their savers
# ---------------------------------------------------------------------------

def banks(conn: Connection) -> list[dict]:
    """Every bank that keeps savers' money, with its deposit asset."""
    if not ready(conn):
        return []
    return _rows(conn, "SELECT c.id, c.ticker, c.name, c.account_id, c.headquarters, d.asset FROM bank_deposits d"
                       " JOIN companies c ON c.id = d.company_id ORDER BY c.ticker")


def bank(conn: Connection, ticker: str) -> dict | None:
    return next((b for b in banks(conn) if b["ticker"] == ticker), None)


def asset_of(conn: Connection, company_id) -> str | None:
    row = _one(conn, "SELECT asset FROM bank_deposits WHERE company_id = %s", (company_id,)) if ready(conn) else None
    return row["asset"] if row else None


def owed(conn: Connection, company_id) -> int | None:
    """What a bank owes its savers now, or None for a company that keeps no savers' money."""
    asset = asset_of(conn, company_id)
    return ledger.amount_in_existence(conn, asset) if asset else None


def saved(conn: Connection, account, asset: str) -> int:
    return max(ledger.balance(conn, account, asset), 0)


def savings_of(conn: Connection, account) -> int:
    """Everything an account keeps in savings at every bank (counted with its cash in what it is worth)."""
    if not ready(conn):
        return 0
    row = _one(conn, "SELECT coalesce(sum(b.balance), 0)::bigint AS total FROM ledger_balances b JOIN bank_deposits d ON d.asset = b.asset"
                     " WHERE b.account_id = %s AND b.balance > 0", (account,))
    return row["total"] if row else 0


def blanket(conn: Connection) -> bool:
    """Whether the Government has promised that every saving is safe, whatever its size."""
    if not _one(conn, "SELECT to_regclass('blanket_guarantees') IS NOT NULL AS ok")["ok"]:
        return False
    return _one(conn, "SELECT 1 AS x FROM blanket_guarantees WHERE until_period IS NULL") is not None


def guaranteed_part(conn: Connection, amount: int) -> int:
    """How much of one saver's money at one bank is guaranteed."""
    return amount if blanket(conn) else min(amount, guarantee())


def closed(conn: Connection, company_id) -> bool:
    """Whether the Central Bank has closed this bank (savings frozen until it is resolved)."""
    if not _one(conn, "SELECT to_regclass('bank_resolutions') IS NOT NULL AS ok")["ok"]:
        return False
    return _one(conn, "SELECT 1 AS x FROM bank_resolutions WHERE company_id = %s AND status = 'open'", (company_id,)) is not None


# ---------------------------------------------------------------------------
# Paying in and drawing out
# ---------------------------------------------------------------------------

def _place(conn: Connection, payer, b: dict, amount: int, kind: str, memo: str, period: int) -> None:
    """Money paid into a bank: the payer's naira to the bank, and the bank's claim, newly made, to the payer."""
    ledger.post(conn, kind=kind, memo=memo, period=period, legs=[
        ledger.Leg(payer, -amount), ledger.Leg(b["account_id"], amount),
        ledger.Leg(b["account_id"], -amount, b["asset"]), ledger.Leg(payer, amount, b["asset"])])


def _repay(conn: Connection, holder, b: dict, amount: int, kind: str, memo: str, period: int) -> None:
    """Savings paid back: the claim returns to the bank (and is gone), the bank pays the naira."""
    ledger.post(conn, kind=kind, memo=memo, period=period, legs=[
        ledger.Leg(b["account_id"], -amount), ledger.Leg(holder, amount),
        ledger.Leg(holder, -amount, b["asset"]), ledger.Leg(b["account_id"], amount, b["asset"])])


def households_place(conn: Connection, location: str, account, b: dict, amount: int, kind: str, period: int, day: int,
                     now: datetime) -> int:
    """Households of a city put money into a bank they trust. Returns what they put in."""
    amount = min(amount, max(ledger.balance(conn, account), 0))
    if amount <= 0:
        return 0
    _place(conn, account, b, amount, "deposit_placed", f"Households of {location}: savings put into {b['name']}", period)
    conn.execute("INSERT INTO household_deposits_covered (company_id, location, covered) VALUES (%s, %s, %s)"
                 " ON CONFLICT (company_id, location) DO UPDATE SET covered = household_deposits_covered.covered + EXCLUDED.covered",
                 (b["id"], location, apply_bps(amount, data.HOUSEHOLD_COVERED_BPS)))
    _flow(conn, b["id"], account, "households", location, kind, amount, period, day, now)
    return amount


def households_draw(conn: Connection, location: str, account, b: dict, amount: int, period: int, day: int, now: datetime) -> int:
    """Households of a city draw savings out of a bank (the bank has already made sure it can pay). Savers above the
    guarantee line go first; what is left belongs more and more to those below it."""
    held = saved(conn, account, b["asset"])
    amount = min(amount, held, max(ledger.balance(conn, b["account_id"]), 0))
    if amount <= 0:
        return 0
    _repay(conn, account, b, amount, "deposit_withdrawn", f"Households of {location}: savings drawn out of {b['name']}", period)
    covered = _one(conn, "SELECT covered FROM household_deposits_covered WHERE company_id = %s AND location = %s FOR UPDATE",
                   (b["id"], location))
    if covered is not None:
        left = held - amount
        conn.execute("UPDATE household_deposits_covered SET covered = least(covered, %s) WHERE company_id = %s AND location = %s",
                     (left, b["id"], location))
    _flow(conn, b["id"], account, "households", location, "run", amount, period, day, now)
    return amount


def household_split(conn: Connection, b: dict, location: str, account) -> tuple[int, int]:
    """A city's savings at a bank: (above the guarantee line, below it)."""
    held = saved(conn, account, b["asset"])
    if blanket(conn):
        return 0, held
    covered = _one(conn, "SELECT covered FROM household_deposits_covered WHERE company_id = %s AND location = %s", (b["id"], location))
    under = min(covered["covered"] if covered else apply_bps(held, data.HOUSEHOLD_COVERED_BPS), held)
    return held - under, under


# ---------------------------------------------------------------------------
# Companies: their spare cash kept as savings at their bank
# ---------------------------------------------------------------------------

def company_place(conn: Connection, account, b: dict, amount: int, period: int, day: int, now: datetime) -> int:
    amount = min(amount, max(ledger.balance(conn, account), 0))
    if amount <= 0 or closed(conn, b["id"]):
        return 0
    _place(conn, account, b, amount, "company_savings", f"Spare cash kept as savings at {b['name']}", period)
    _flow(conn, b["id"], account, "company", None, "placed", amount, period, day, now)
    return amount


def company_draw(conn: Connection, account, b: dict, amount: int, period: int, day: int, now: datetime, *, kind: str = "run") -> int:
    held = saved(conn, account, b["asset"])
    amount = min(amount, held, max(ledger.balance(conn, b["account_id"]), 0))
    if amount <= 0:
        return 0
    _repay(conn, account, b, amount, "company_savings_back", f"Savings drawn back out of {b['name']}", period)
    _flow(conn, b["id"], account, "company", None, kind, amount, period, day, now)
    return amount


def _company_bank(conn: Connection, company: dict) -> dict | None:
    """Where a company keeps its savings: the bank it borrows from, if that bank is open and calm; otherwise the most
    trusted open bank."""
    from simulation import crisis
    trust = crisis.trust_now(conn)
    open_banks = [b for b in banks(conn) if not closed(conn, b["id"]) and b["id"] != company["id"]]
    if not open_banks:
        return None
    lender = _one(conn, "SELECT c.id FROM company_debts d JOIN companies c ON c.account_id = d.lender_account_id"
                        " WHERE d.company_id = %s AND d.principal_outstanding > 0 ORDER BY d.principal_outstanding DESC LIMIT 1",
                  (company["id"],))
    calm = lambda b: trust.get(b["id"], {}).get("state", "calm") == "calm"   # noqa: E731
    if lender:
        mine = next((b for b in open_banks if b["id"] == lender["id"]), None)
        if mine and calm(mine):
            return mine
    choice = [b for b in open_banks if calm(b) and trust.get(b["id"], {}).get("score", data.CONFIDENCE_START) >= data.CONFIDENCE_WARNING] \
        or [b for b in open_banks if calm(b)] or open_banks
    # Spread over the trusted banks, each company with its own (so the risk is not all at one bank), a bigger bank taking
    # more of them in proportion to the savings it already keeps (so a small bank is not handed a giant's spare cash it cannot
    # earn the interest on). The pick is fixed by the world's secret and the company, so a world always repeats.
    import hashlib
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    ranked = sorted(choice, key=lambda b: b["ticker"])
    sizes = [max(ledger.amount_in_existence(conn, b["asset"]), 1) for b in ranked]
    point = int(hashlib.sha256(f"{seed}:savings:{company.get('ticker') or company['id']}".encode()).hexdigest()[:12], 16) % sum(sizes)
    for b, size in zip(ranked, sizes):
        if point < size:
            return b
        point -= size
    return ranked[-1]


def company_savings(conn: Connection, account) -> int:
    return savings_of(conn, account)


def company_before_close(conn: Connection, company: dict, period: int, policy_rate_bps: int, ratings: dict) -> None:
    """As a company starts its close its bank pays the interest on its savings (on the least kept through the quarter),
    and it draws them back into cash, to pay what it must. A closed bank's are frozen."""
    if not ready(conn) or company["sector"] == "banking":
        return
    from simulation import crisis
    now = _one(conn, "SELECT now() AS t")["t"]
    for b in banks(conn):
        held = saved(conn, company["account_id"], b["asset"])
        if held <= 0 or closed(conn, b["id"]):
            continue
        _interest_one(conn, b, company["account_id"], period, savings_rate_bps(policy_rate_bps, ratings.get(b["id"])))
        paid = crisis.secure_cash(conn, b, held, period, clock.GAME_DAYS_PER_QUARTER, now)
        if paid > 0:
            company_draw(conn, company["account_id"], b, paid, period, clock.GAME_DAYS_PER_QUARTER, now, kind="withdrawn")


def company_after_close(conn: Connection, company: dict, result: dict, period: int, now: datetime | None = None) -> int:
    """After its close, a company keeps half its cash above what it likes to hold as savings at its bank."""
    if not ready(conn) or company["sector"] in ("banking",) or company.get("status") == "wound_up":
        return 0
    comfortable = data.CASH_TARGET_QUARTERS * (result["operating_expenses"] + result["interest_expense"])
    spare = max(ledger.balance(conn, company["account_id"]) - comfortable, 0)
    amount = apply_bps(spare, data.COMPANY_SAVINGS_BPS)
    if amount < naira(data.SAVINGS_LEAST_NAIRA):
        return 0
    b = _company_bank(conn, company)
    return company_place(conn, company["account_id"], b, amount, period, clock.GAME_DAYS_PER_QUARTER, now) if b else 0


def bailed_in(conn: Connection, company_id, period: int) -> int:
    """What a closed bank's savers above the guarantee bore of its hole this quarter."""
    if not ready(conn):
        return 0
    return _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE company_id = %s AND kind = 'bail_in'"
                      " AND period = %s", (company_id, period))["t"]


def lost_in_failures(conn: Connection, account, period: int) -> int:
    """Savings an account lost this quarter when a bank was closed and savers above the guarantee bore its hole."""
    if not ready(conn):
        return 0
    return _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE account_id = %s AND kind = 'bail_in'"
                      " AND period = %s", (account, period))["t"]


# ---------------------------------------------------------------------------
# Players and empires: savings
# ---------------------------------------------------------------------------

def _state(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


def _saver(conn: Connection, player_id, for_empire: bool, now: datetime) -> tuple[object, str, dict | None]:
    """Whose savings: the player's own, or (for its head) the empire's."""
    if not for_empire:
        account = ledger.player_account_id(conn, player_id)
        if account is None:
            raise SavingsError("You have no account yet.")
        return account, "player", None
    from simulation import empires
    seat = empires.seat_of(conn, player_id)
    empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (seat["empire_id"],)) if seat else None
    if empire is None or empire["status"] != "active":
        raise SavingsError("You hold no seat in an active empire.")
    if empire["head_player_id"] != player_id:
        raise SavingsError("Only the empire's head moves its money into or out of savings.")
    return empire["account_id"], "empire", empire


def _amount(amount) -> int:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < naira(data.SAVINGS_LEAST_NAIRA):
        raise SavingsError(f"Put in or take out at least {money(naira(data.SAVINGS_LEAST_NAIRA))}.")
    return amount


def _player_bank(conn: Connection, ticker: str) -> dict:
    b = bank(conn, ticker)
    if b is None or ticker not in data.PLAYER_BANKS:
        raise SavingsError("Choose one of the six banks.")
    return b


def put_in(conn: Connection, player_id, ticker: str, amount, now: datetime, *, for_empire: bool = False) -> dict:
    """Move cash into savings at a bank."""
    amount = _amount(amount)
    with conn.transaction():
        _books_open(conn, now)
        setup(conn, _state(conn, now)["period"] - 1, now)
        b = _player_bank(conn, ticker)
        account, holder, empire = _saver(conn, player_id, for_empire, now)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('savings:' || %s::text))", (str(account),))
        if closed(conn, b["id"]):
            raise SavingsError(f"{b['name']} has been closed by the Central Bank. It takes no money until it is resolved.")
        w = _state(conn, now)
        if empire is not None:
            # Moving the empire's cash into savings puts it at the bank's risk: the head may move, in a quarter, no more than
            # what they may sign for (less what they have signed for already). Taking it out is never limited.
            from simulation import empires
            seat = empires.seat_of(conn, player_id)
            moved = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE account_id = %s AND holder = 'empire'"
                               " AND kind = 'placed' AND period = %s", (account, w["period"]))["t"]
            room = empires.signing_limit(conn, seat) - empires._spent(conn, empire["id"], player_id, w["period"]) - moved
            if amount > room:
                raise SavingsError(f"That is more of the empire's money than you may sign for this quarter ({money(max(room, 0))} left).")
        if ledger.balance(conn, account) < amount:
            raise SavingsError(f"You have {money(max(ledger.balance(conn, account), 0))} in cash.")
        _place(conn, account, b, amount, "savings_placed",
               f"{'The empire' if empire else 'Savings'}: {money(amount)} put into savings at {b['name']}", w["period"])
        _flow(conn, b["id"], account, holder, None, "placed", amount, w["period"], w["day"], now)
        if empire is not None:
            from simulation.empires import _log
            _log(conn, empire["id"], f"The head put {money(amount)} of the empire's cash into savings at {b['name']}.", now)
        return {"bank": b["name"], "saved": saved(conn, account, b["asset"])}


def take_out(conn: Connection, player_id, ticker: str, amount, now: datetime, *, for_empire: bool = False, everything: bool = False) -> dict:
    """Draw savings out of a bank (`everything`: all of it, to the last kobo). The bank pays if it can: if it cannot,
    the Central Bank closes it, and that closing stands (it is not undone by the refusal)."""
    if not everything:
        amount = _amount(amount)
    from simulation import crisis
    shut = None
    with conn.transaction():
        _books_open(conn, now)
        setup(conn, _state(conn, now)["period"] - 1, now)
        b = _player_bank(conn, ticker)
        account, holder, empire = _saver(conn, player_id, for_empire, now)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('savings:' || %s::text))", (str(account),))
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('bank-cash:' || %s::text))", (str(b["id"]),))
        if closed(conn, b["id"]):
            raise SavingsError(f"{b['name']} has been closed by the Central Bank. Savings there are frozen until it is resolved.")
        held = saved(conn, account, b["asset"])
        if everything:
            amount = held
            if amount <= 0:
                raise SavingsError(f"You have no savings at {b['name']}.")
        if amount > held:
            raise SavingsError(f"You have {money(held)} in savings at {b['name']}.")
        w = _state(conn, now)
        paid = crisis.secure_cash(conn, b, amount, w["period"], w["day"], now)
        if paid < amount:
            # It cannot pay what it owes on demand: the Central Bank closes it, and the closing is kept. Nothing is paid out.
            crisis.cannot_pay(conn, b, w["period"], w["day"], now)
            shut = b
        else:
            _repay(conn, account, b, amount, "savings_withdrawn",
                   f"{'The empire' if empire else 'Savings'}: {money(amount)} taken out of savings at {b['name']}", w["period"])
            _flow(conn, b["id"], account, holder, None, "withdrawn", amount, w["period"], w["day"], now)
            if empire is not None:
                from simulation.empires import _log
                _log(conn, empire["id"], f"The head took {money(amount)} of the empire's savings out of {b['name']}.", now)
            done = {"bank": b["name"], "saved": saved(conn, account, b["asset"])}
    if shut is not None:
        raise SavingsError(f"{shut['name']} could not pay. The Central Bank has closed it: savings there are frozen until it is resolved.")
    return done


def _books_open(conn: Connection, now: datetime) -> None:
    """No moving savings between a quarter's end and its close (closures at the close are decided on what stood then)."""
    from simulation import careers
    try:
        careers.books_open(conn, now)
    except careers.CareerError as e:
        raise SavingsError(str(e)) from None


def draw_for_debt(conn: Connection, account, wanted: int, period: int, now: datetime) -> int:
    """Savings are cash kept with a bank: when an account must raise cash by force (a margin call, a debt in default),
    its savings at open banks are drawn first, before anything is sold. Returns what was drawn."""
    if not ready(conn) or wanted <= 0:
        return 0
    from simulation import careers, crisis
    day = careers.world_now(conn, now)["day"]
    drawn = 0
    for b in banks(conn):
        if drawn >= wanted:
            break
        held = saved(conn, account, b["asset"])
        if held <= 0 or closed(conn, b["id"]):
            continue
        amount = crisis.secure_cash(conn, b, min(held, wanted - drawn), period, day, now)
        if amount <= 0:
            continue
        _repay(conn, account, b, amount, "savings_withdrawn", f"Savings drawn out of {b['name']} to pay what is owed", period)
        holder = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))["kind"]
        _flow(conn, b["id"], account, holder if holder in ("player", "empire", "company") else "player", None, "withdrawn", amount,
              period, day, now)
        drawn += amount
    return drawn


def savings_rate_bps(policy_rate_bps: int, rating: str | None) -> int:
    """What savings at a bank pay in a year: a share of the Central Bank's rate, more at a weaker bank."""
    return apply_bps(policy_rate_bps, data.TERM_SAVINGS_RATE_SHARE_BPS.get(rating or "BBB", 6_500))


def _lowest(conn: Connection, account, asset: str, since: datetime | None) -> int:
    """The least an account held of an asset at any moment since `since` (the last close)."""
    opening = 0
    if since is not None:
        opening = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e"
                             " JOIN ledger_transactions t ON t.id = e.transaction_id"
                             " WHERE e.account_id = %s AND e.asset = %s AND t.created_at <= %s", (account, asset, since))["total"]
    lowest = running = opening
    for move in _rows(conn, "SELECT e.amount FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                            " WHERE e.account_id = %s AND e.asset = %s AND (%s::timestamptz IS NULL OR t.created_at > %s)"
                            " ORDER BY t.created_at, e.id", (account, asset, since, since)):
        running += move["amount"]
        lowest = min(lowest, running)
    return max(lowest, 0)


def pay_interest(conn: Connection, company: dict, period: int, policy_rate_bps: int, rating: str | None) -> int:
    """At its close, a bank pays interest on players' and empires' savings: on the least kept through the whole quarter,
    so money put in for a moment before pay day earns nothing. Returns what it paid."""
    asset = asset_of(conn, company["id"])
    if asset is None or closed(conn, company["id"]):
        return 0
    rate = savings_rate_bps(policy_rate_bps, rating)
    total = 0
    for holder in _rows(conn, "SELECT b.account_id, a.kind FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                              " WHERE b.asset = %s AND b.balance > 0 AND a.kind IN ('player', 'empire') ORDER BY b.account_id", (asset,)):
        total += _interest_one(conn, {**company, "asset": asset}, holder["account_id"], period, rate)
    return total


def _interest_one(conn: Connection, b: dict, account, period: int, rate: int) -> int:
    """One saver's interest for the quarter, once, on the least it kept through the whole quarter."""
    asset = b.get("asset") or asset_of(conn, b["id"])
    if _one(conn, "SELECT 1 AS x FROM savings_interest WHERE account_id = %s AND company_id = %s AND period = %s", (account, b["id"], period)):
        return 0
    last = _one(conn, "SELECT closed_at FROM money_watch_results WHERE period = %s", (period - 1,))
    lowest = _lowest(conn, account, asset, last["closed_at"] if last else None)
    amount = (lowest * rate + 2 * BPS) // (4 * BPS)
    paid = ledger.pay_up_to(conn, payer=b["account_id"], receiver=account, wanted=amount, kind="savings_interest",
                            period=period, memo=f"{b['name']}: interest on savings, {clock.period_label(period)}") if amount > 0 else 0
    conn.execute("INSERT INTO savings_interest (account_id, company_id, period, lowest, rate_bps, amount) VALUES (%s, %s, %s, %s, %s, %s)",
                 (account, b["id"], period, lowest, rate, paid))
    return paid


def pay_premium(conn: Connection, company: dict, period: int) -> int:
    """At its close, a bank pays the Deposit Guarantee Fund its premium on what it owes its savers."""
    owes = owed(conn, company["id"])
    if not owes or closed(conn, company["id"]):
        return 0
    fund = ledger.account_id(conn, GUARANTEE_FUND)
    wanted = apply_bps(owes, data.GUARANTEE_PREMIUM_BPS)
    paid = ledger.pay_up_to(conn, payer=company["account_id"], receiver=fund, wanted=wanted, kind="guarantee_premium", period=period,
                            memo=f"{company['name']}: its premium to the Deposit Guarantee Fund, {clock.period_label(period)}")
    # The fund repays what it borrowed from the Treasury first.
    repay_fund_loans(conn, period)
    return paid


def repay_fund_loans(conn: Connection, period: int) -> None:
    fund = ledger.account_id(conn, GUARANTEE_FUND)
    treasury = ledger.account_id(conn, ledger.TREASURY)
    for loan in _rows(conn, "SELECT * FROM guarantee_fund_loans WHERE outstanding > 0 ORDER BY id FOR UPDATE"):
        paid = ledger.pay_up_to(conn, payer=fund, receiver=treasury, wanted=loan["outstanding"], kind="guarantee_fund_repayment",
                                period=period, memo="The Deposit Guarantee Fund repays the Treasury")
        if paid <= 0:
            return
        conn.execute("UPDATE guarantee_fund_loans SET outstanding = outstanding - %s WHERE id = %s", (paid, loan["id"]))


def fund_pays(conn: Connection, receiver, amount: int, period: int, now: datetime, memo: str, *, kind: str = "guarantee_cover") -> int:
    """The Deposit Guarantee Fund pays out; what it has not got, it borrows from the Treasury. Returns what was paid."""
    fund = ledger.account_id(conn, GUARANTEE_FUND)
    short = amount - max(ledger.balance(conn, fund), 0)
    if short > 0:
        treasury = ledger.account_id(conn, ledger.TREASURY)
        lent = ledger.pay_up_to(conn, payer=treasury, receiver=fund, wanted=short, kind="guarantee_fund_loan", period=period,
                                memo="The Treasury lends to the Deposit Guarantee Fund")
        if lent > 0:
            conn.execute("INSERT INTO guarantee_fund_loans (amount, outstanding, period, at) VALUES (%s, %s, %s, %s)", (lent, lent, period, now))
    return ledger.pay_up_to(conn, payer=fund, receiver=receiver, wanted=amount, kind=kind, period=period, memo=memo)


# ---------------------------------------------------------------------------
# What a player sees
# ---------------------------------------------------------------------------

def view(conn: Connection, player_id, now: datetime) -> dict:
    """The banks, how far each is trusted, what savings pay, and what the player (and, for a member, their empire) keeps
    in each. Another saver's money is never shown."""
    from simulation import crisis, empires
    w = _state(conn, now)
    setup(conn, w["period"] - 1, now)
    account = ledger.player_account_id(conn, player_id)
    seat = empires.seat_of(conn, player_id)
    empire = _one(conn, "SELECT * FROM empires WHERE id = %s AND status = 'active'", (seat["empire_id"],)) if seat else None
    rate = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    policy = rate["next_policy_rate_bps"] if rate else data.NEUTRAL_RATE_BPS
    trust = crisis.trust_now(conn)
    out = []
    for b in banks(conn):
        rating = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1", (b["id"],))
        mine = saved(conn, account, b["asset"]) if account else 0
        ours = saved(conn, empire["account_id"], b["asset"]) if empire else 0
        t = trust.get(b["id"], {})
        out.append({"ticker": b["ticker"], "name": b["name"], "headquarters": b["headquarters"],
                    "takes_savings": b["ticker"] in data.PLAYER_BANKS, "rating": rating["credit_rating"] if rating else None,
                    "savings_rate_bps": savings_rate_bps(policy, rating["credit_rating"] if rating else None),
                    "trust": t.get("score"), "state": t.get("state", "calm"), "trust_change": t.get("change"),
                    "closed": closed(conn, b["id"]),
                    "mine": mine, "mine_guaranteed": guaranteed_part(conn, mine),
                    "empire": ours if empire else None, "empire_guaranteed": guaranteed_part(conn, ours) if empire else None})
    return {"banks": out, "guarantee": guarantee(), "blanket": blanket(conn), "least": naira(data.SAVINGS_LEAST_NAIRA),
            "cash": max(ledger.balance(conn, account), 0) if account else 0,
            "empire": {"name": empire["name"], "head": empire["head_player_id"] == player_id,
                       "cash": max(ledger.balance(conn, empire["account_id"]), 0)} if empire else None,
            "interest": [{"period": r["period"], "bank": r["name"], "lowest": r["lowest"], "rate_bps": r["rate_bps"], "amount": r["amount"]}
                         for r in _rows(conn, "SELECT s.*, c.name FROM savings_interest s JOIN companies c ON c.id = s.company_id"
                                              " WHERE s.account_id = %s ORDER BY s.period DESC, c.name LIMIT 12", (account,))] if account else []}
