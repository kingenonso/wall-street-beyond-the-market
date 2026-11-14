"""Server insurance routes (Stage 12).

Every request acts as the logged-in player, for their own account.
The four actions are: Buy a policy, Cancel a policy, Review cover, Claim.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import Connection
from pydantic import Field, field_validator

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import insurance as sim_insurance
from simulation import ledger
from simulation import world_data as data


router = APIRouter(prefix="/insurance", tags=["insurance"])

Money = Annotated[int, Field(gt=0, le=1_000_000_000_000_000, strict=True)]


# --- Schemas ---

PolicyKind = Literal["property", "directors", "income", "umbrella"]


class BuyPolicyRequest(Request):
    kind: PolicyKind
    limit_kobo: Money
    excess_kobo: Money = Field(gt=0, default=0)

    @classmethod
    @field_validator("kind")
    def kind_must_be_valid(cls, v):
        if v not in ("property", "directors", "income", "umbrella"):
            raise ValueError("Kind must be one of: property, directors, income, umbrella")
        return v


class CancelPolicyRequest(Request):
    kind: PolicyKind

    @classmethod
    @field_validator("kind")
    def kind_must_be_valid(cls, v):
        if v not in ("property", "directors", "income", "umbrella"):
            raise ValueError("Kind must be one of: property, directors, income, umbrella")
        return v


class ReviewCoverRequest(Request):
    kind: PolicyKind

    @classmethod
    @field_validator("kind")
    def kind_must_be_valid(cls, v):
        if v not in ("property", "directors", "income", "umbrella"):
            raise ValueError("Kind must be one of: property, directors, income, umbrella")
        return v


class ClaimRequest(Request):
    kind: PolicyKind
    loss_kind: str  # e.g. "property", "directors", "income", "umbrella"
    loss_amount_kobo: Money
    evidence: str = ""  # description of the loss event

    @classmethod
    @field_validator("kind")
    def kind_must_be_valid(cls, v):
        if v not in ("property", "directors", "income", "umbrella"):
            raise ValueError("Kind must be one of: property, directors, income, umbrella")
        return v


# --- Route helpers ---

def _player_policy_account(conn: Connection, player_id: str) -> str:
    """The player's personal account for insurance premiums/claims."""
    return ledger.player_account_id(conn, player_id)


def _pool_account(conn: Connection) -> str:
    return ledger.account_id(conn, "insurance:pool")


# --- Routes ---

@router.post("/buy", summary="Buy an insurance policy")
def buy_policy(req: BuyPolicyRequest, conn: Connection = Depends(get_connection),
               player: dict = Depends(current_player)) -> dict:
    """Buy a new insurance policy.

    Premium = expected loss + loading (20% bps). Charged from the player's account
    to the insurance pool. The policy starts at once; no-claims record begins at 0.
    """
    player_account = _player_policy_account(conn, player["id"])
    pool_account = _pool_account(conn)

    # Compute the quarterly premium
    period = sim_insurance.clock.world_now(conn, _exchange_time(conn))["period"]
    premium = sim_insurance._compute_premium(
        conn, player["id"], req.kind, period, req.limit_kobo, req.excess_kobo)

    if premium <= 0:
        raise HTTPException(status.HTTP_400,
                            detail="Premium is zero or negative; cannot buy a policy with no expected loss.")

    # Check the player has enough in their account
    balance = ledger.balance(conn, player_account)
    if balance < premium:
        raise HTTPException(status.HTTP_400,
                            detail=f"Insufficient funds: your account has {balance} but the premium is {premium}.")

    # Transfer premium to the pool
    ledger.transfer(conn, payer=player_account, receiver=pool_account,
                    amount=premium, kind="insurance_premium",
                    period=period, now=_exchange_time(conn))

    # Write the policy row
    conn.execute("""
        INSERT INTO insurance_policies (player_id, kind, limit, excess, premium_bps,
            started, ends, state, no_claims_years)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', 0)
    """, (player["id"], req.kind, req.limit_kobo, req.excess_kobo,
          premium, period, None))

    # Log the event
    _ = period  # silence

    return {"kind": req.kind, "limit_kobo": req.limit_kobo,
            "excess_kobo": req.excess_kobo, "premium_kobo": premium,
            "state": "active", "period": period}


@router.post("/cancel", summary="Cancel an insurance policy")
def cancel_policy(req: CancelPolicyRequest, conn: Connection = Depends(get_connection),
                  player: dict = Depends(current_player)) -> dict:
    """Cancel an active insurance policy.

    A policy can be cancelled at any time. Premiums already charged are not refunded.
    The policy state is set to 'expired'. No second claim can be opened on an
    expired policy.
    """
    period = sim_insurance.clock.world_now(conn, _exchange_time(conn))["period"]

    # Set the policy to expired
    conn.execute("""
        UPDATE insurance_policies
        SET state = 'expired', ends = %s
        WHERE player_id = %s AND kind = %s AND state = 'active'
    """, (period, player["id"], req.kind))

    return {"kind": req.kind, "state": "expired", "period": period}


@router.post("/review", summary="Review your cover")
def review_cover(req: ReviewCoverRequest, conn: Connection = Depends(get_connection),
                 player: dict = Depends(current_player)) -> dict:
    """Review your active insurance policy.

    Shows the current limit, excess, premium, no-claims years, and the adjusted
    personal loan spread.
    """
    period = sim_insurance.clock.world_now(conn, _exchange_time(conn))["period"]

    policy = sim_insurance._one(conn, """
        SELECT kind, limit, excess, premium_bps, started, no_claims_years, state
        FROM insurance_policies
        WHERE player_id = %s AND kind = %s AND state = 'active'
    """, (player["id"], req.kind))

    if policy is None:
        raise HTTPException(status.HTTP_404,
                            detail=f"No active {req.kind} policy found for player {player['id']}.")

    # Compute the narrowed personal loan spread
    from server.lending import UNINSURED_PERSONAL_LOAN_SPREAD_BPS
    from server.lending import INSURED_PERSONAL_LOAN_STEP1_BPS, INSURED_PERSONAL_LOAN_STEP2_BPS

    borrower_policies = sim_insurance._rows(conn, """
        SELECT kind, limit FROM insurance_policies
        WHERE player_id = %s AND state = 'active'
    """, (player["id"],))

    total_cover_kobo = sum(p["limit"] for p in borrower_policies)

    narrowing = UNINSURED_PERSONAL_LOAN_SPREAD_BPS
    if total_cover_kobo > 0:
        narrowing -= INSURED_PERSONAL_LOAN_STEP1_BPS
        borrower_loan = sim_insurance._one(conn, """
            SELECT principal FROM player_loans
            WHERE borrower = %s AND kind = 'personal' AND status = 'open'
            ORDER BY taken_period DESC LIMIT 1
        """, (player["id"],))
        if borrower_loan and borrower_loan["principal"] > 0:
            if total_cover_kobo > borrower_loan["principal"] // 2:
                narrowing -= INSURED_PERSONAL_LOAN_STEP2_BPS

    loan_rate_bps = data.NEUTRAL_RATE_BPS + narrowing  # simplified; real impl reads the player's loan

    return {
        "kind": policy["kind"],
        "limit_kobo": policy["limit"],
        "excess_kobo": policy["excess"],
        "premium_bps": policy["premium_bps"],
        "started": policy["started"],
        "no_claims_years": policy["no_claims_years"],
        "state": policy["state"],
        "personal_loan_spread_bps": narrowing,
        "loan_rate_bps": loan_rate_bps,
    }


@router.post("/claim", summary="Open a claim against your policy")
def open_claim(req: ClaimRequest, conn: Connection = Depends(get_connection),
               player: dict = Depends(current_player)) -> dict:
    """Open a new claim against your active policy.

    The claim is written to the claims table and investigated. If the loss was
    caused by the claimant, the claim is refused and a court case for insurance
    fraud is opened. Otherwise, the claim is approved for payment from the pool.
    """
    period = sim_insurance.clock.world_now(conn, _exchange_time(conn))["period"]

    # Open the claim via the simulation module, using the policy's excess.
    policy = sim_insurance._one(conn, """
        SELECT excess FROM insurance_policies
        WHERE player_id = %s AND kind = %s AND state = 'active'
    """, (player["id"], req.kind))
    if policy is None:
        raise HTTPException(status.HTTP_404,
                            detail=f"No active {req.kind} policy found for player {player['id']}.")
    claim_id = sim_insurance.open_claim(conn, player["id"], req.kind,
                                        req.loss_kind, req.loss_amount_kobo,
                                        req.evidence, policy["excess"], _exchange_time(conn))

    # Investigate before payment
    investigation = sim_insurance.investigate_claim(conn, claim_id, _exchange_time(conn))

    return {
        "claim_id": claim_id,
        "kind": req.kind,
        "loss_kind": req.loss_kind,
        "loss_amount_kobo": req.loss_amount_kobo,
        "investigation": investigation,
        "period": period,
    }