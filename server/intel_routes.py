"""Stage 10, Part 2: the Intelligence Market, the Sealed Tip, sources and the record of rumours, on the website.

Nothing sent from here says whether a piece of information is true, what it was drawn from, who planted it, or when it
will be settled. A piece's words go only to those who hold it. Nobody is told who else holds a piece, only how many do.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import wire
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import careers, clock, intel, newsroom
from simulation.money import naira

REF = r"^[A-Za-z0-9_-]{8,20}$"


def _act(conn: Connection, player: dict, action, bucket: str = "intel", attempts: int = 30) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (intel.IntelError, newsroom.NewsroomError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    return {"result": wire(result) if isinstance(result, (dict, list)) else result}


class RefRequest(Request):
    ref: str = Field(pattern=REF)


class GiveRequest(Request):
    ref: str = Field(pattern=REF)
    to: str = Field(min_length=2, max_length=40)


class OfferRequest(Request):
    ref: str = Field(pattern=REF)
    price_naira: int = Field(ge=10_000, le=50_000_000, strict=True)


class SourceRequest(Request):
    kind: Literal["company", "ministry"]
    ticker: str | None = Field(default=None, pattern=r"^[A-Z]{2,5}$")


@app.get("/api/intel")
def intel_desk(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if not player.get("build"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a build first: information is matched to the work you do.")
    now = _exchange_time(conn)
    out = {"tip": intel.sealed_tip(conn, player["id"], now), "mine": intel.mine(conn, player["id"], now),
           "market": intel.market(conn, player["id"], now), "feed": intel.desk_feed(conn, player["id"], now)}
    if player["build"] == "journalist":
        level = careers.career(conn, player["id"], "journalist")
        out["sources"] = intel.sources(conn, player["id"], now)
        out["sources_allowed"] = intel.sources_allowed(level["level"] if level else 1)
    return wire(out)


@app.post("/api/intel/tip/open")
def intel_open_tip(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.open_tip(conn, player["id"], now))


@app.post("/api/intel/check")
def intel_check(body: RefRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.check(conn, player["id"], body.ref, now), bucket="intel-check", attempts=10)


@app.post("/api/intel/give")
def intel_give(body: GiveRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.give(conn, player["id"], body.ref, body.to, now), bucket="intel-give", attempts=10)


@app.post("/api/intel/offer", status_code=201)
def intel_offer(body: OfferRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.offer(conn, player["id"], body.ref, naira(body.price_naira), now))


@app.post("/api/intel/listings/{listing_id}/withdraw")
def intel_withdraw(listing_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.withdraw(conn, player["id"], listing_id))


@app.post("/api/intel/listings/{listing_id}/buy")
def intel_buy(listing_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.buy(conn, player["id"], listing_id, now), bucket="intel-buy", attempts=10)


@app.post("/api/intel/sources", status_code=201)
def intel_cultivate(body: SourceRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if body.kind == "company" and not body.ticker:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name the company by its ticker.")
    return _act(conn, player, lambda now: intel.cultivate(conn, player["id"], body.kind, body.ticker, now))


@app.post("/api/intel/sources/{source_id}/ask")
def intel_ask(source_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.ask_source(conn, player["id"], source_id, now))


@app.post("/api/intel/sources/{source_id}/drop")
def intel_drop(source_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: intel.drop_source(conn, player["id"], source_id))


@app.post("/api/newsroom/lead")
def newsroom_lead(body: RefRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.add_lead(conn, player["id"], body.ref, now), bucket="newsroom")


@app.post("/api/newsroom/lead/remove")
def newsroom_lead_remove(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.remove_lead(conn, player["id"], now), bucket="newsroom")


@app.get("/api/rumours")
def rumours(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The record of unconfirmed reports: what readers believed, and what turned out to be true (M32)."""
    now = _exchange_time(conn)
    w = careers.world_now(conn, now)
    rows = conn.execute("""
        SELECT s.id, s.headline, s.readers, s.period, s.day, s.lead_outcome, p.display_name AS author,
               coalesce((SELECT sum(b.bps) FROM rumour_beliefs b WHERE b.story_id = s.id), 0)::int AS marked
        FROM stories s JOIN players p ON p.id = s.author_id
        WHERE s.status = 'published' AND s.lead IS NOT NULL AND (s.period < %s OR (s.period = %s AND s.day <= %s))
        ORDER BY s.period DESC, s.day DESC, s.id DESC LIMIT 40""", (w["period"], w["period"], w["day"])).fetchall()
    out = []
    for r in rows:
        r = dict(zip(("id", "headline", "readers", "period", "day", "outcome", "author", "marked"), r)) if not isinstance(r, dict) else r
        out.append({"story_id": r["id"], "headline": r["headline"], "readers": r["readers"], "author": r["author"],
                    "when": clock.period_label(r["period"]) + f", day {r['day']}", "marked_bps": r["marked"],
                    "outcome": {"confirmed": "borne out", "disproved": "proved wrong", None: "not yet settled"}[r["lead_outcome"]]})
    return {"rumours": out}
