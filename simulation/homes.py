"""The gap stage, Part 2: households buying homes with loans from the banks.

Each quarter, in each city, households borrow to buy homes: about 1.5% of their income at the neutral rate, less as
the mortgage rate rises above it and as fewer people have jobs, more when it falls. The banks lend (each in proportion
to what it already lends to that city's households, and never past what its own funds allow), and the money goes to the
city's property companies, which build the homes (buying from the cement and steel companies). Home loans are part of
what households owe the banks, and are repaid with the rest of it.

Some households cannot pay: a little of the book defaults every quarter, more when the rate has risen over the last
year, when jobs are lost, and when repayments take too much of income. The bank repossesses the homes and sells them,
getting back about 60% of the loan (other households buy them cheaply); it loses the rest. The forced sales push the
city's home prices down. So a sharp rate rise brings defaults and falling prices, as the design asks.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('home_loans') IS NOT NULL AS ok")["ok"] is True


def demand_bps(rate_bps: int, jobs_change_bps: int) -> int:
    """How keen households are to borrow for homes, against the neutral rate and steady jobs."""
    mortgage = rate_bps + data.HOME_LOAN_SPREAD_BPS
    neutral = data.NEUTRAL_RATE_BPS + data.HOME_LOAN_SPREAD_BPS
    keen = BPS - (mortgage - neutral) * data.HOME_LOAN_RATE_SENSITIVITY_BPS // 100 + jobs_change_bps * 2
    return min(max(keen, 0), 2 * BPS)


def default_bps(rate_bps: int, rate_year_ago_bps: int, jobs_change_bps: int, burden_bps: int) -> int:
    """The share of the home-loan book that defaults this quarter."""
    rise_points = max(rate_bps - rate_year_ago_bps, 0) / 100
    jobs_fall = max(-jobs_change_bps, 0) / 100
    out = data.HOME_DEFAULT_BASE_BPS + rise_points * data.HOME_DEFAULT_PER_RATE_POINT_BPS + jobs_fall * data.HOME_DEFAULT_PER_JOBS_FALL_BPS
    if burden_bps > data.HOME_DEFAULT_BURDEN_BPS:
        out += (burden_bps - data.HOME_DEFAULT_BURDEN_BPS) // 10
    return int(min(out, 2000))


def _rate(conn: Connection, period: int) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps AS r FROM economy_results WHERE period = %s", (period,))
    if row:
        return row["r"]
    row = _one(conn, "SELECT next_policy_rate_bps AS r FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["r"] if row else data.NEUTRAL_RATE_BPS


def close(conn: Connection, world, period: int, now: datetime, *, rate_bps: int | None = None, year_ago_bps: int | None = None) -> dict:
    """One quarter of home buying, defaults and repossessions in every city."""
    if not ready(conn):
        return {}
    if _one(conn, "SELECT 1 FROM home_loans LIMIT 1") is None:
        # A new world: a fifth of what households owe the banks at the start is home loans.
        conn.execute("INSERT INTO home_loans (bank_company_id, location, principal) SELECT bank_company_id, location, principal * %s / 10000"
                     " FROM household_debts WHERE principal > 0", (data.HOME_SEED_SHARE_BPS,))
    from simulation import banking, infrastructure, news
    from simulation import property as prop
    label = clock.period_label(period)
    rate = _rate(conn, period) if rate_bps is None else rate_bps
    year_ago = _rate(conn, period - 4) if year_ago_bps is None else year_ago_bps
    banks = {b["id"]: b for b in banking.banks(conn, period)}
    ds = prop.districts(conn)
    totals = {"lent": 0, "defaulted": 0}
    for location, household in sorted(world.households.items()):
        hh = household["account_id"]
        now_row = _one(conn, "SELECT income, jobs FROM household_results WHERE location = %s AND period = %s", (location, period))
        before = _one(conn, "SELECT jobs FROM household_results WHERE location = %s AND period = %s", (location, period - 1))
        if now_row is None:
            continue
        jobs_change = (now_row["jobs"] - before["jobs"]) * BPS // max(before["jobs"], 1) if before else 0
        income = now_row["income"]
        # 1. Repayments: home loans shrink with the rest of what households owe (the banks' own servicing collects them).
        conn.execute("UPDATE home_loans SET principal = principal - principal * %s / 10000 WHERE location = %s", (data.HOUSEHOLD_REPAY_BPS, location))
        book_rows = _rows(conn, "SELECT * FROM home_loans WHERE location = %s AND principal > 0 ORDER BY bank_company_id", (location,))
        book = sum(r["principal"] for r in book_rows)
        repaid = book * data.HOUSEHOLD_REPAY_BPS // max(BPS - data.HOUSEHOLD_REPAY_BPS, 1)
        # 2. Defaults and repossessions.
        service = book * (rate + data.HOME_LOAN_SPREAD_BPS) // BPS // 4 + book // data.HOME_LOAN_TERM_QUARTERS
        burden = service * BPS // max(income, 1)            # repayments against the households' income
        share = default_bps(rate, year_ago, jobs_change, burden)
        defaulted = recovered = repossessed = 0
        homes = [d for d in ds.values() if d["city"] == location and d["kind"] == "homes"]
        for r in book_rows:
            gone = r["principal"] * share // BPS
            if gone <= 0:
                continue
            bank = banks.get(r["bank_company_id"]) or _one(conn, "SELECT id, account_id, name FROM companies WHERE id = %s", (r["bank_company_id"],))
            back = ledger.pay_up_to(conn, payer=hh, receiver=bank["account_id"], wanted=gone * data.HOME_RECOVERY_BPS // BPS,
                                    kind="household_loan_repayment", memo=f"Repossessed homes in {location} sold for {bank['name']}, {label}",
                                    period=period)
            conn.execute("UPDATE home_loans SET principal = principal - %s WHERE bank_company_id = %s AND location = %s",
                         (gone, r["bank_company_id"], location))
            conn.execute("UPDATE household_debts SET principal = greatest(principal - %s, 0) WHERE bank_company_id = %s AND location = %s",
                         (gone, r["bank_company_id"], location))
            conn.execute("INSERT INTO bank_home_losses (bank_company_id, period, amount) VALUES (%s, %s, %s)", (r["bank_company_id"], period, gone - back))
            defaulted += gone
            recovered += back
        if homes and defaulted:
            avg_home = max(sum(prop.value(p, d, rate) for d in homes for p in _rows(conn, "SELECT * FROM properties WHERE district_id = %s AND kind = 'home'",
                                                                                   (d["id"],))) // max(len(homes) * 10, 1), 1)
            repossessed = max(defaulted // max(avg_home // 50, 1), 1)
        # 3. New home loans, bank by bank.
        keen = demand_bps(rate, jobs_change)
        wanted = income * data.HOME_LOAN_SHARE_BPS // BPS * keen // BPS
        shares = {r["bank_company_id"]: r["principal"] for r in _rows(conn, "SELECT bank_company_id, principal FROM household_debts WHERE location = %s"
                                                                            " AND principal > 0", (location,))}
        lent = 0
        total_share = sum(shares.values())
        for bank_id, owed in sorted(shares.items(), key=lambda kv: str(kv[0])):
            bank = banks.get(bank_id)
            if bank is None or total_share <= 0:
                continue
            amount = min(wanted * owed // total_share, banking.lending_room(bank))
            if amount <= 0 or ledger.balance(conn, bank["account_id"]) < amount:
                continue
            ledger.transfer(conn, payer=bank["account_id"], receiver=hh, amount=amount, kind="household_loan",
                            memo=f"{bank['name']}: home loans to households in {location}, {label}", period=period)
            bank["household_loans"] += amount
            conn.execute("UPDATE household_debts SET principal = principal + %s WHERE bank_company_id = %s AND location = %s", (amount, bank_id, location))
            conn.execute("INSERT INTO home_loans (bank_company_id, location, principal) VALUES (%s, %s, %s)"
                         " ON CONFLICT (bank_company_id, location) DO UPDATE SET principal = home_loans.principal + EXCLUDED.principal",
                         (bank_id, location, amount))
            lent += amount
        # The households pay the city's property companies for the new homes, which buy the materials.
        if lent:
            builders = _rows(conn, "SELECT account_id FROM companies WHERE sector = 'real_estate' AND status = 'trading' AND headquarters = %s"
                                   " ORDER BY ticker", (location,)) or \
                _rows(conn, "SELECT account_id FROM companies WHERE sector = 'real_estate' AND status = 'trading' ORDER BY ticker")
            each = lent // max(len(builders), 1)
            for n, b in enumerate(builders):
                part = each if n < len(builders) - 1 else lent - each * (len(builders) - 1)
                paid = ledger.pay_up_to(conn, payer=hh, receiver=b["account_id"], wanted=part, kind="customer_revenue",
                                        memo=f"Households in {location} buy new homes, {label}", period=period)
                infrastructure.buy_from(conn, b["account_id"], paid * data.HOME_BUILD_COST_BPS // BPS, ("cement", data.STEEL_SECTOR), location,
                                        f"Materials for new homes in {location}, {label}", period, kind="business_purchase")
        # 4. Home prices: buying lifts them; forced sales push them down.
        homes_worth = sum(prop.value(p, d, rate) for d in homes for p in _rows(conn, "SELECT * FROM properties WHERE district_id = %s", (d["id"],)))
        if homes and homes_worth > 0:
            move = (lent * data.HOME_PRICE_FROM_BUYING_BPS // BPS - defaulted * data.HOME_REPOSSESSION_PRICE_HIT) * BPS // homes_worth
            move = max(min(move, 1500), -2500)
            for d in homes:
                premium = min(max(d["premium_bps"] + move, data.PREMIUM_LIMITS_BPS[0]), data.PREMIUM_LIMITS_BPS[1])
                conn.execute("UPDATE districts SET premium_bps = %s WHERE id = %s", (premium, d["id"]))
        book_after = _one(conn, "SELECT coalesce(sum(principal), 0)::bigint AS b FROM home_loans WHERE location = %s", (location,))["b"]
        conn.execute("INSERT INTO home_loan_results (period, location, lent, repaid, defaulted, recovered, repossessed, book, rate_bps)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (period, location) DO NOTHING",
                     (period, location, lent, repaid, defaulted, recovered, repossessed, book_after, rate + data.HOME_LOAN_SPREAD_BPS))
        if repossessed and share >= data.HOME_DEFAULT_BASE_BPS * 3:
            news.publish(conn, period=period + 1, day=4, kind="home_repossessions", story=f"homes:{location}:{period}",
                         facts={"city": location, "homes": f"about {repossessed:,}", "rate": f"{(rate + data.HOME_LOAN_SPREAD_BPS) / 100:.1f}%"},
                         locations=[location], sectors=["banking", "real_estate"])
        totals["lent"] += lent
        totals["defaulted"] += defaulted
    return totals


def losses_to_count(conn: Connection, bank_company_id, period: int) -> int:
    """For a bank's accounts: what it lost on home loans since its last accounts (counted once)."""
    if not ready(conn):
        return 0
    row = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM bank_home_losses WHERE bank_company_id = %s AND counted_in IS NULL",
               (bank_company_id,))
    conn.execute("UPDATE bank_home_losses SET counted_in = %s WHERE bank_company_id = %s AND counted_in IS NULL", (period, bank_company_id))
    return row["n"]


def summary(conn: Connection) -> list[dict]:
    if not ready(conn):
        return []
    return [{"period": r["period"], "label": clock.period_label(r["period"]), "location": r["location"], "lent": r["lent"],
             "defaulted": r["defaulted"], "repossessed": r["repossessed"], "book": r["book"], "rate_bps": r["rate_bps"]}
            for r in _rows(conn, "SELECT * FROM home_loan_results WHERE period >= (SELECT max(period) - 7 FROM home_loan_results)"
                                 " ORDER BY period, location")]
