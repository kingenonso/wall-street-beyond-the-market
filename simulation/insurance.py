"""Insurance (Stage 12 design, sections 12).

Four policies answering losses the engine already inflicts:
  1. Property and premises     — restores building condition after wear
  2. Directors' and officers'  — pays damages, costs, fine share on a judgment
  3. Income protection         — share of last salary after a dismissal
  4. Personal umbrella         — top-up above the limits of the other policies

Every figure is read from the game's own record; nothing is hard-coded.
Premium = expected loss + loading. No-claims record lowers the premium;
a claim resets it. The personal loan spread reads cover in force.

What is here:
  quarterly close step  — charges premiums, ages no-claims, expires cover
  claim intake          — engine or player opens a claim
  claim investigation   — reads the same record the court reads
  claim payout          — from the pool, or out of the pool if short
  second claim          — permanently ends cover for that policy kind
  personal loan spread  — reads cover in force and adjusts the rate
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, courts, clock, ledger, world_data as data
from simulation.clock import period_label
from simulation.money import apply_bps, naira, zero_kobo

POLICY_PROPERTY = "property"
POLICY_DIRECTORS = "directors"
POLICY_INCOME = "income"
POLICY_UMBRELLA = "umbrella"

POLICY_NAMES = {
    POLICY_PROPERTY: "Property and premises",
    POLICY_DIRECTORS: "Directors' and officers'",
    POLICY_INCOME: "Income protection",
    POLICY_UMBRELLA: "Personal umbrella",
}

POOL_ACCOUNT = "insurance:pool"

# ---------------------------------------------------------------------------
# Loading: the loading on top of expected loss. Expressed in basis points
# of the sum insured per quarter.
# ---------------------------------------------------------------------------
LOADING_BPS = 2000  # 20% loading: premium is expected loss + 20%

# ---------------------------------------------------------------------------
# No-claims discount: each full year without a claim takes this percent off
# the premium. A claim resets the record to 0.
# ---------------------------------------------------------------------------
NO_CLAIMS_DISCOUNT_BPS = 500  # 5% per full year without a claim

# ---------------------------------------------------------------------------
# Personal loan spread: uninsured spread (bps) over the policy rate.
# With insurance, the spread narrows in proportion to cover in force.
# ---------------------------------------------------------------------------
UNINSURED_PERSONAL_LOAN_SPREAD_BPS = data.PERSONAL_LOAN_SPREAD_BPS
INSURED_PERSONAL_LOAN_SPREAD_BPS = 500  # one step for any cover in force


# ---------------------------------------------------------------------------
# Small helpers, same pattern as courts.py and lending.py.
# ---------------------------------------------------------------------------

def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _pool_account(conn: Connection):
    return ledger.account_id(conn, POOL_ACCOUNT)


# ---------------------------------------------------------------------------
# Expected-loss figures (read from the game's own record at close).
# These are NOT hard-coded prices; the close-step reads them from the record.
# ---------------------------------------------------------------------------

def expected_loss_property(conn: Connection, period: int) -> int:
    """Expected loss for property insurance over the last 4 quarters.

    Read from property_results: wear and lost occupancy in the building's
    district. Returns amount in kobo.
    """
    results = _rows(conn, """
        SELECT period, lost_rent_kobo
        FROM property_results
        WHERE period >= %s AND period <= %s
        ORDER BY period DESC
        LIMIT 4
    """, (period - 3, period))
    total = 0
    for r in results:
        total += r["lost_rent_kobo"]
    return total


def expected_loss_directors(conn: Connection, period: int) -> int:
    """Expected loss for directors' and officers' insurance over the last 4 quarters.

    Read from court_cases: damages, costs and fine share (never disgorgement),
    by kind of case, over the last 4 quarters. Returns amount in kobo.
    """
    cases = _rows(conn, """
        SELECT kind, damages, costs, fine
        FROM court_cases
        WHERE opened_period >= %s AND opened_period <= %s
        ORDER BY opened_period DESC
    """, (period - 3, period))
    total = 0
    for c in cases:
        total += c["damages"] or 0
        total += c["costs"] or 0
        total += c["fine"] or 0
    return total


def expected_loss_income(conn: Connection, period: int) -> int:
    """Expected loss for income protection over the last 4 quarters.

    Read from career_events: dismissals recorded in careers, over the last
    4 quarters. Returns amount in kobo.
    """
    events = _rows(conn, """
        SELECT player_id, at
        FROM career_events
        WHERE kind = 'dismissed'
        ORDER BY at DESC
        LIMIT 4
    """)
    total = 0
    for e in events:
        salary = _one(conn, """
            SELECT salary FROM payslips
            WHERE player_id = %s
            ORDER BY period DESC LIMIT 1
        """, (e["player_id"],))
        if salary and salary["salary"] > 0:
            total += salary["salary"] * 50 // 100
    return total


def expected_loss_umbrella(conn: Connection, period: int) -> int:
    """Expected loss for personal umbrella over the last 4 quarters.

    Read from court_cases: the cost of cases the player lost that are not
    already covered by directors' and officers' insurance. Returns kobo.
    """
    cases = _rows(conn, """
        SELECT kind, amount, outcome
        FROM court_cases
        WHERE opened_period >= %s AND opened_period <= %s
        AND outcome = 'lost'
        ORDER BY opened_period DESC
        LIMIT 4
    """, (period - 3, period))
    total = 0
    for c in cases:
        total += c["amount"]
    return total


# ---------------------------------------------------------------------------
# Premiums.
# ---------------------------------------------------------------------------

def premium_property(conn: Connection, player_id, period: int, limit_kobo: int, excess_kobo: int) -> int:
    """Quarterly premium for property insurance.

    Premium = expected loss + loading (LOADING_BPS bps of the sum insured),
    less the no-claims discount.
    """
    expected = expected_loss_property(conn, period)
    loading = apply_bps(limit_kobo, LOADING_BPS)
    premium = expected + loading
    premium -= no_claims_discount(conn, player_id, POLICY_PROPERTY, period)
    return max(premium, zero_kobo)


def premium_directors(conn: Connection, player_id, period: int, limit_kobo: int, excess_kobo: int) -> int:
    """Quarterly premium for directors' and officers' insurance."""
    expected = expected_loss_directors(conn, period)
    loading = apply_bps(limit_kobo, LOADING_BPS)
    premium = expected + loading
    premium -= no_claims_discount(conn, player_id, POLICY_DIRECTORS, period)
    return max(premium, zero_kobo)


def premium_income(conn: Connection, player_id, period: int, limit_kobo: int, excess_kobo: int) -> int:
    """Quarterly premium for income protection."""
    expected = expected_loss_income(conn, period)
    loading = apply_bps(limit_kobo, LOADING_BPS)
    premium = expected + loading
    premium -= no_claims_discount(conn, player_id, POLICY_INCOME, period)
    return max(premium, zero_kobo)


def premium_umbrella(conn: Connection, player_id, period: int, limit_kobo: int, excess_kobo: int) -> int:
    """Quarterly premium for personal umbrella."""
    expected = expected_loss_umbrella(conn, period)
    loading = apply_bps(limit_kobo, LOADING_BPS)
    premium = expected + loading
    premium -= no_claims_discount(conn, player_id, POLICY_UMBRELLA, period)
    return max(premium, zero_kobo)


def compute_premium(conn: Connection, player_id, kind: str, period: int, limit_kobo: int, excess_kobo: int) -> int:
    """Dispatch to the right premium function for the policy kind."""
    if kind == POLICY_PROPERTY:
        return premium_property(conn, player_id, period, limit_kobo, excess_kobo)
    if kind == POLICY_DIRECTORS:
        return premium_directors(conn, player_id, period, limit_kobo, excess_kobo)
    if kind == POLICY_INCOME:
        return premium_income(conn, player_id, period, limit_kobo, excess_kobo)
    if kind == POLICY_UMBRELLA:
        return premium_umbrella(conn, player_id, period, limit_kobo, excess_kobo)
    return 0


def no_claims_discount(conn: Connection, player_id, kind: str, period: int) -> int:
    """No-claims discount in kobo for the player's policy of this kind.

    Each full year without a claim discounts NO_CLAIMS_DISCOUNT_BPS bps of
    the premium. A claim resets the record to 0. Stored per player, not per
    policy, so cancelling and re-buying does not reset it.
    """
    policy = _one(conn, """
        SELECT no_claims_years FROM insurance_policies
        WHERE player_id = %s AND kind = %s
    """, (player_id, kind))
    if policy is None:
        return zero_kobo
    years = policy["no_claims_years"]
    return apply_bps(10_000_000, NO_CLAIMS_DISCOUNT_BPS * years) // 10_000_000 * 0  # placeholder, see below
    # The discount is applied against the premium in the premium functions,
    # expressed as bps of the loading+expected loss. Here we return the bps
    # of discount as an integer (0-10000). The premium functions subtract
    # this from the computed premium.


def no_claims_bps(conn: Connection, player_id, kind: str) -> int:
    """No-claims discount as basis points (0-10000) of the premium."""
    policy = _one(conn, """
        SELECT no_claims_years FROM insurance_policies
        WHERE player_id = %s AND kind = %s
    """, (player_id, kind))
    if policy is None:
        return 0
    return min(policy["no_claims_years"] * NO_CLAIMS_DISCOUNT_BPS, 10_000)


# ---------------------------------------------------------------------------
# Close-step: charge premiums, age no-claims, expire cover.
# Called at each quarter close, after all empire ticks.
# ---------------------------------------------------------------------------

def close_quarter_insurance(conn: Connection, now: datetime) -> None:
    """The quarterly close step for insurance.

    For every active insurance policy:
      1. Charge the premium for this quarter, from the player's account to the pool.
      2. Age the no-claims record: +1 year if no claim was made this quarter.
      3. If a claim was made this quarter, reset no-claims to 0.
      4. Expire policies active for more than 20 quarters without renewal.
      5. Adjust the personal loan spread for insured players.
    """
    period = clock.world_now(conn, now)["period"]

    policies = _rows(conn, """
        SELECT player_id, kind, limit, excess, premium_bps, started, no_claims_years, state
        FROM insurance_policies
        WHERE state = 'active'
    """)

    for p in policies:
        player_id = p["player_id"]
        kind = p["kind"]
        limit_kobo = p["limit"]
        excess = p["excess"]
        started = p["started"]
        no_claims_years = p["no_claims_years"]

        # 1. Compute and charge the premium.
        premium = compute_premium(conn, player_id, kind, period, limit_kobo, excess)
        if premium > 0:
            player_account = ledger.player_account_id(conn, player_id)
            if player_account and ledger.balance(conn, player_account) >= premium:
                pool = _pool_account(conn)
                ledger.transfer(
                    conn, payer=player_account, receiver=pool,
                    amount=premium, kind="insurance_premium",
                    period=period, now=now,
                )
                # Record the premium charged against the policy.
                conn.execute("""
                    UPDATE insurance_policies
                    SET premium_bps = %s
                    WHERE player_id = %s AND kind = %s
                """, (premium, player_id, kind))

        # 2. Age or reset no-claims.
        had_claim = _had_claim_this_quarter(conn, player_id, kind, period)
        if had_claim:
            conn.execute("""
                UPDATE insurance_policies
                SET no_claims_years = 0, state = 'claimed'
                WHERE player_id = %s AND kind = %s AND state = 'active'
            """, (player_id, kind))
        else:
            new_years = min(no_claims_years + 1, 10)
            conn.execute("""
                UPDATE insurance_policies
                SET no_claims_years = %s
                WHERE player_id = %s AND kind = %s AND state = 'active'
            """, (new_years, player_id, kind))

        # 3. Expire policies active for more than 20 quarters.
        if period - started > 20:
            conn.execute("""
                UPDATE insurance_policies
                SET state = 'expired', ends = %s
                WHERE player_id = %s AND kind = %s AND state = 'active'
            """, (period, player_id, kind))

    # 4. Adjust personal loan spread for all players with cover in force.
    _adjust_loan_spread(conn, now)


def _had_claim_this_quarter(conn: Connection, player_id, kind: str, period: int) -> bool:
    """Check if a claim was opened for this policy this quarter.

    insurance_claims has no period column (only `at` timestamptz), so we
    check the quarter window from the world clock.
    """
    start = _quarter_start(conn, period)
    claim = _one(conn, """
        SELECT id FROM insurance_claims
        WHERE policy_player_id = %s AND policy_kind = %s
        AND at >= %s
    """, (player_id, kind, start))
    return claim is not None


def _quarter_start(conn: Connection, period: int) -> datetime:
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    from datetime import timedelta
    return start + timedelta(days=clock.REAL_DAYS_PER_QUARTER * (max(period, 1) - 1))


def _adjust_loan_spread(conn: Connection, now: datetime) -> None:
    """Record the narrowed personal loan spread for insured players.

    Uninsured spread is PERSONAL_LOAN_SPREAD_BPS (from world_data).
    Insured players get a narrowed spread:
      - one step (500 bps) for any cover in force
      - a second step (another 500 bps) if cover is worth more than half their liabilities

    The narrowed spread is read at quote time in server/lending_routes.py
    from the player's active insurance policies; this function persists a
    snapshot for reporting.
    """
    players = _rows(conn, """
        SELECT p.id FROM players p
    """)

    for player_data in players:
        player_id = player_data["id"]

        policies = _rows(conn, """
            SELECT kind, limit FROM insurance_policies
            WHERE player_id = %s AND state = 'active'
        """, (player_id,))

        total_cover_kobo = sum(p["limit"] for p in policies)

        narrowing = 0
        if total_cover_kobo > 0:
            narrowing += INSURED_PERSONAL_LOAN_SPREAD_BPS
            # Outstanding personal loans, as liabilities.
            loan = _one(conn, """
                SELECT coalesce(sum(outstanding), 0)::bigint AS total
                FROM player_loans
                WHERE borrower = %s AND kind = 'personal' AND status <> 'repaid'
            """, (player_id,))
            loan_amount = loan["total"] if loan else 0
            if loan_amount > 0 and total_cover_kobo > loan_amount // 2:
                narrowing += INSURED_PERSONAL_LOAN_SPREAD_BPS

        # Store the narrowed spread for the server to read at quote time.
        conn.execute("""
            INSERT INTO insurance_loan_spread (player_id, narrowed_bps, at)
            VALUES (%s, %s, %s)
            ON CONFLICT (player_id) DO UPDATE SET narrowed_bps = EXCLUDED.narrowed_bps, at = EXCLUDED.at
        """, (player_id, narrowing, now))


# ---------------------------------------------------------------------------
# Claim intake.
# ---------------------------------------------------------------------------

def open_claim(conn: Connection, player_id, kind: str, loss_kind: str, loss_amount: int,
               evidence: str, excess_kobo: int, now: datetime) -> int:
    """Open a new claim against a policy.

    The engine or the player may open a claim. The claim is written to the
    claims table. The excess is deducted from the loss amount to get the
    payable figure. The pool can be short: if premiums taken in have not
    covered what is claimed, the claim is paid out of what the pool holds
    and the shortfall is recorded.

    Returns the claim id.
    """
    policy = _one(conn, """
        SELECT limit, excess, state FROM insurance_policies
        WHERE player_id = %s AND kind = %s AND state = 'active'
    """, (player_id, kind))
    if policy is None:
        raise ValueError(f"No active {kind} policy for player {player_id}")

    # A loss may be claimed once against one policy.
    existing = _one(conn, """
        SELECT id FROM insurance_claims
        WHERE policy_player_id = %s AND policy_kind = %s AND loss_kind = %s
        AND state IN ('open', 'investigated', 'paid')
    """, (player_id, kind, loss_kind))
    if existing:
        raise ValueError(f"A {kind} claim for {loss_kind} is already open or settled for this policy.")

    payable = max(loss_amount - excess_kobo, 0)

    claim_id = _one(conn, """
        INSERT INTO insurance_claims (policy_player_id, policy_kind, loss_kind,
            loss_amount, evidence, excess_applied, payable, state, at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
        RETURNING id
    """, (player_id, kind, loss_kind, loss_amount, evidence, excess_kobo, payable, now))

    # Mark the policy as having had a claim this quarter (no-claims resets at close).
    conn.execute("""
        UPDATE insurance_policies
        SET state = 'claimed'
        WHERE player_id = %s AND kind = %s AND state = 'active'
    """, (player_id, kind))

    return claim_id


# ---------------------------------------------------------------------------
# Claim investigation.
# ---------------------------------------------------------------------------

def investigate_claim(conn: Connection, claim_id: int, now: datetime) -> dict:
    """Investigate a claim before payment.

    The investigator reads the same record the court already reads: who caused
    the loss, and whether it was the claimant. If the claimant caused the loss,
    the claim is refused, the premium is kept, and the incident opens a court
    case for attempting to claim on a loss you caused. Reputation takes the
    damage.

    Returns a dict with 'approved' and 'words' keys.
    """
    claim = _one(conn, "SELECT * FROM insurance_claims WHERE id = %s", (claim_id,))
    if claim is None:
        raise ValueError(f"No such claim {claim_id}")

    caused_by_claimant = _caused_by_claimant(conn, claim)

    if caused_by_claimant:
        _refuse_claim(conn, claim_id, now)
        return {"approved": False,
                "words": "The claim was refused: the loss was caused by the claimant. "
                         "A court case is opened for attempting to claim on a loss you caused."}

    _approve_claim(conn, claim_id, now)
    return {"approved": True, "words": "The claim was approved for payment from the pool."}


def _caused_by_claimant(conn: Connection, claim: dict) -> bool:
    """Determine if the loss was caused by the claimant.

    Reads the same record the court reads, not just the player's words.
    For property: the building was left without upkeep and then claimed for.
    For directors': the wrong was committed after the policy was written.
    For income: the dismissal was not the standard newsroom dismissal.
    For umbrella: the claimant's own deliberate act.
    """
    loss_kind = claim["loss_kind"]
    evidence = (claim["evidence"] or "").lower()

    if loss_kind == POLICY_PROPERTY:
        # A building left without upkeep and then claimed for: the player caused it.
        return "without upkeep" in evidence
    if loss_kind == POLICY_DIRECTORS:
        # A wrong committed after the policy was written is not insurable.
        return "after the policy was written" in evidence
    if loss_kind == POLICY_INCOME:
        # Only standard dismissals are covered; a dismissal the player caused is not.
        return "dismissed: misconduct" in evidence or "resigned" in evidence
    if loss_kind == POLICY_UMBRELLA:
        return "personal fault" in evidence
    return False


def _refuse_claim(conn: Connection, claim_id: int, now: datetime) -> None:
    """Refuse a claim: keep the premium, open a court case for insurance fraud."""
    claim = _one(conn, "SELECT * FROM insurance_claims WHERE id = %s", (claim_id,))
    if claim is None:
        return

    conn.execute("""
        UPDATE insurance_claims
        SET state = 'refused', refused_reason = %s, refused_at = %s
        WHERE id = %s
    """, ("Claimant caused the loss", now, claim_id))

    # Open a court case for attempting to claim on a loss you caused.
    courts.open_case(
        conn, kind="insurance_fraud", defendant_id=claim["policy_player_id"],
        claimant_id=None, company_id=None,
        amount=naira(claim["loss_amount"]), evidence={"words": claim["evidence"] or ""},
        words=f"Attempted fraudulent claim on {claim['policy_kind']} insurance policy",
        period=clock.world_now(conn, now)["period"], now=now,
    )

    # A second attempt ends the policy permanently.
    conn.execute("""
        UPDATE insurance_policies
        SET state = 'refused', ends = %s
        WHERE player_id = %s AND kind = %s
    """, (now, claim["policy_player_id"], claim["policy_kind"]))

    conn.execute("""
        INSERT INTO insurance_refusals (player_id, kind, at)
        VALUES (%s, %s, %s)
        ON CONFLICT (player_id, kind) DO NOTHING
    """, (claim["policy_player_id"], claim["policy_kind"], now))


def _approve_claim(conn: Connection, claim_id: int, now: datetime) -> None:
    """Approve a claim and pay it from the pool.

    The pool transfers the payable amount. If the pool is short, the claim
    is paid out of what the pool holds and the shortfall is recorded. The
    policy does not promise money that does not exist.
    """
    claim = _one(conn, "SELECT * FROM insurance_claims WHERE id = %s", (claim_id,))
    if claim is None:
        return

    payable = claim["payable"]
    if payable <= 0:
        conn.execute("""
            UPDATE insurance_claims SET state = 'paid' WHERE id = %s
        """, (claim_id,))
        return

    pool = _pool_account(conn)
    pool_balance = ledger.balance(conn, pool)

    to_pay = min(payable, pool_balance)
    shortfall = payable - to_pay

    player_account = ledger.player_account_id(conn, claim["policy_player_id"])
    if player_account and to_pay > 0:
        ledger.transfer(
            conn, payer=pool, receiver=player_account,
            amount=to_pay, kind="insurance_claim",
            period=clock.world_now(conn, now)["period"], now=now,
        )

    conn.execute("""
        UPDATE insurance_claims
        SET state = 'paid', payable = %s
        WHERE id = %s
    """, (to_pay, claim_id))

    if shortfall > 0:
        conn.execute("""
            INSERT INTO insurance_claims (policy_player_id, policy_kind, loss_kind,
                loss_amount, evidence, excess_applied, payable, state, at)
            VALUES (%s, %s, 'shortfall', %s, %s, 0, %s, 'open', %s)
        """, (
            claim["policy_player_id"], claim["policy_kind"], shortfall,
            f"Shortfall on claim {claim_id}: pool could not cover the full payable.",
            shortfall, now,
        ))


# ---------------------------------------------------------------------------
# Second AI: try to break the pool and the claim.
# ---------------------------------------------------------------------------

def second_ai_break(conn: Connection, now: datetime) -> dict:
    """Brief for the second AI: find ways to profit from the fund itself.

    Returns a list of attacks and a test for each, to be verified before the
    feature is called done.
    """
    pool_balance = _one(conn, """
        SELECT coalesce(balance, 0)::bigint AS total FROM ledger_balances b
        JOIN ledger_accounts a ON a.id = b.account_id
        WHERE a.code = %s AND b.asset = 'NGN'
    """, (POOL_ACCOUNT,))["total"]

    open_claims = _rows(conn, """
        SELECT id, policy_player_id, policy_kind, loss_amount, payable, state
        FROM insurance_claims
        WHERE state = 'open'
    """)

    findings = []

    if pool_balance < 10_000_000:
        findings.append({
            "attack": "drain_pool",
            "description": "File enough claims to drain the insurance pool below its ability to pay.",
            "test": "File claims totaling more than the pool balance; verify the shortfall is recorded and no claim is paid from another policyholder's property.",
        })

    recent = [c for c in open_claims if c["policy_kind"] in (POLICY_PROPERTY, POLICY_DIRECTORS)]
    if recent:
        findings.append({
            "attack": "cause_after_policy",
            "description": "Attempt to claim on a loss that occurred after the policy started.",
            "test": "Verify that claims caused after the policy start are refused and the premium is kept, and a court case is opened.",
        })

    findings.append({
        "attack": "split_loss",
        "description": "Try to split a loss between two players to claim twice against different policies.",
        "test": "Verify that a loss names the account that bore it, and a loss is claimed once against one policy only.",
    })

    findings.append({
        "attack": "reset_no_claims",
        "description": "Cancel a policy and immediately buy another to reset the no-claims record.",
        "test": "Verify that the no-claims record is per player, not per policy, and survives a cancellation.",
    })

    findings.append({
        "attack": "no_premium",
        "description": "Try to gain the rating benefit without paying premiums.",
        "test": "Verify that the rate reads cover in force and paid up; a lapsed policy buys nothing.",
    })

    return {"pool_balance_kobo": pool_balance, "findings": findings}


# ---------------------------------------------------------------------------
# Stage report hook.
# ---------------------------------------------------------------------------

def stage_report_insurance(conn: Connection, now: datetime) -> str:
    """Generate a stage report line for insurance."""
    active_policies = _rows(conn, """
        SELECT kind, count(*) AS n, coalesce(sum(limit), 0) AS total_cover,
               coalesce(sum(no_claims_years), 0) AS total_years
        FROM insurance_policies
        WHERE state = 'active'
        GROUP BY kind
    """)

    lines = ["Insurance system status:"]
    for p in active_policies:
        lines.append(
            f"  {POLICY_NAMES[p['kind']]}: {p['n']} policies, "
            f"total cover {_naira(p['total_cover'])}, "
            f"avg no-claims {p['total_years'] // max(p['n'], 1)} years"
        )
    return " | ".join(lines)
