"""The crises stage, Part 1, on the website: savings at the banks, trust in each bank, the Crisis Watch and the record of
every crisis. (Bids for a closed bank use the Auction House's own routes.)

Never sent: anybody else's savings, a crisis's hidden weakness while it is open, the lowest price the Deposit Guarantee
Fund will take when it sells a bank again, or anyone's bid limit but the viewer's own. (For a closed bank the lowest bid is
public: it is the new money the bank needs.)
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from fastapi import Path as FastPath
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
    ours = auctions.bank_view(conn, now, viewer=empire["account_id"] if empire else None) if empire else []
    by_id = {b["id"]: b for b in ours}
    for a in own:
        b = by_id.get(a["id"])
        if b:
            a["empire_limit"] = b["your_limit"]
            a["empire_leads"] = b["you_lead"]
    return wire(_money({"watch": crisiswatch.view(conn, now), "banks": crisis.bank_view(conn, now), "crises": crisis.crises_view(conn, now),
                        "auctions": own, "blanket": deposits.blanket(conn), "national": crisis.national(conn),
                        "guarantee": deposits.guarantee()}))


# A bank in trouble pops up on every player's screen; these are the kinds of news that do.
ALERT_KINDS = ("bank_run", "bank_panic", "bank_closed", "bank_rescued", "bank_public", "savings_guarantee", "guarantee_lifted", "banks_calm")


@app.get("/api/crisis/alerts")
def crisis_alerts(after: int | None = Query(default=None, ge=0), player: dict = Depends(current_player),
                  conn: Connection = Depends(get_connection)):
    """What has happened at the banks since the player last looked (one item for each affair, in the paper that gave it most
    weight), and whether the player's own savings, or their empire's, are at that bank. Only what is dated today or before."""
    from simulation import careers
    w = careers.world_now(conn, _exchange_time(conn))
    seen = "(period < %s OR (period = %s AND day <= %s))"
    top = conn.execute(f"SELECT coalesce(max(id), 0) AS m FROM news_items WHERE kind = ANY(%s) AND {seen}",
                       (list(ALERT_KINDS), w["period"], w["period"], w["day"])).fetchone()["m"]
    if after is None:
        # Opening the game: what happened in the last five game days, so nobody misses a crisis in progress.
        rows = conn.execute(f"SELECT DISTINCT ON (story) * FROM news_items WHERE kind = ANY(%s) AND {seen} AND (period * 100 + day) >= %s"
                            " ORDER BY story, importance DESC, id", (list(ALERT_KINDS), w["period"], w["period"], w["day"],
                                                                     w["period"] * 100 + w["day"] - 5)).fetchall()
        if not rows and conn.execute("SELECT 1 FROM economic_crises WHERE status = 'open' AND step >= 3").fetchone():
            # A crisis still going on: its latest news, however many days ago it was printed.
            rows = conn.execute(f"SELECT * FROM news_items WHERE kind = ANY(%s) AND {seen} ORDER BY id DESC LIMIT 1",
                                (list(ALERT_KINDS), w["period"], w["period"], w["day"])).fetchall()
    else:
        rows = conn.execute(f"SELECT DISTINCT ON (story) * FROM news_items WHERE kind = ANY(%s) AND {seen} AND id > %s"
                            " ORDER BY story, importance DESC, id", (list(ALERT_KINDS), w["period"], w["period"], w["day"], after)).fetchall()
    rows = sorted(rows, key=lambda r: r["id"])[-5:]
    mine = ledger.player_account_id(conn, player["id"])
    empire = conn.execute("SELECT e.account_id FROM empires e JOIN empire_seats s ON s.empire_id = e.id WHERE s.player_id = %s"
                          " AND e.status = 'active'", (player["id"],)).fetchone()
    items = []
    for r in rows:
        ticker = (r["tickers"] or [None])[0]
        yours = None
        if ticker:
            b = deposits.bank(conn, ticker)
            if b and mine and deposits.saved(conn, mine, b["asset"]) > 0:
                yours = "you"
            elif b and empire and deposits.saved(conn, empire["account_id"], b["asset"]) > 0:
                yours = "empire"
        company = conn.execute("SELECT name FROM companies WHERE ticker = %s", (ticker,)).fetchone() if ticker else None
        items.append({"id": r["id"], "kind": r["kind"], "headline": r["headline"], "body": r["body"], "ticker": ticker,
                      "company": company["name"] if company else None, "yours": yours})
    return wire({"mark": top, "items": items})
