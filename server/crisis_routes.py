"""The crises stage, Part 1, on the website: savings at the banks, trust in each bank, the Crisis Watch and the record of
every crisis. (Bids for a closed bank use the Auction House's own routes.)

Never sent: anybody else's savings, a crisis's hidden weakness while it is open, the lowest price the Deposit Guarantee
Fund will take when it sells a bank again, or anyone's bid limit but the viewer's own. (For a closed bank the lowest bid is
public: it is the new money the bank needs.)
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path as FastPath, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import wire
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import auctions, crisis, crisiswatch, deposits, ledger
from simulation.money import naira

KOBO = {"mine", "mine_guaranteed", "empire", "empire_guaranteed", "cash", "guarantee", "least", "lowest", "amount", "start_price",
        "price", "minimum", "your_limit", "drawn_out", "central_bank", "new_money"}


def _money(value, key: str | None = None):
    """Money as text (a kobo figure can be larger than a browser counts exactly), for the keys these pages use."""
    if isinstance(value, dict):
        return {k: (str(v) if k in KOBO and isinstance(v, int) and not isinstance(v, bool) else _money(v, k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_money(v) for v in value]
    return value


class SavingsRequest(Request):
    amount_naira: int = Field(ge=0, le=100_000_000_000, strict=True)
    for_empire: bool = False
    everything: bool = False             # take it all out, to the last kobo


def _act(conn: Connection, player: dict, action) -> dict:
    limits.allow("savings", str(player["id"]), attempts=20, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except deposits.SavingsError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    return wire(_money({"result": result}))


@app.get("/api/savings")
def savings(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return wire(_money(deposits.view(conn, player["id"], _exchange_time(conn))))


@app.post("/api/savings/{ticker}/in")
def savings_in(body: SavingsRequest, ticker: str = FastPath(pattern="^[A-Z]{3}$"), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: deposits.put_in(conn, player["id"], ticker, naira(body.amount_naira), now, for_empire=body.for_empire))


@app.post("/api/savings/{ticker}/out")
def savings_out(body: SavingsRequest, ticker: str = FastPath(pattern="^[A-Z]{3}$"), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: deposits.take_out(conn, player["id"], ticker, naira(body.amount_naira), now, for_empire=body.for_empire,
                                                         everything=body.everything))


@app.get("/api/crisis")
def crisis_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    now = _exchange_time(conn)
    viewer = ledger.player_account_id(conn, player["id"])
    from simulation import empires
    seat = empires.seat_of(conn, player["id"])
    empire = conn.execute("SELECT account_id FROM empires WHERE id = %s AND status = 'active'", (seat["empire_id"],)).fetchone() if seat else None
    own = auctions.bank_view(conn, now, viewer=viewer)
    ours = auctions.bank_view(conn, now, viewer=empire[0] if empire else None) if empire else []
    by_id = {b["id"]: b for b in ours}
    for a in own:
        b = by_id.get(a["id"])
        if b:
            a["empire_limit"] = b["your_limit"]
            a["empire_leads"] = b["you_lead"]
    return wire(_money({"watch": crisiswatch.view(conn, now), "banks": crisis.bank_view(conn, now), "crises": crisis.crises_view(conn, now),
                        "auctions": own, "blanket": deposits.blanket(conn), "national": crisis.national(conn),
                        "guarantee": deposits.guarantee()}))
