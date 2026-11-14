"""Stage 7: rank cases, the CEO rank, the league tables, and reports of marking.

Every request acts as the logged-in player and nobody else. A player sees only their own cases,
and never an answer before a case has been judged.
"""

from __future__ import annotations

import math
from typing import Literal

from fastapi import Depends, HTTPException, status
from fastapi import Path as FastPath
from psycopg import Connection
from pydantic import Field, field_validator, model_validator

from server import limits
from server.db import get_connection
from server.empire_routes import Words
from server.main import _exchange_time, _terms_as_text, app, current_player
from server.schemas import Request
from simulation import careers, leagues, ranks

TRACK = Literal["asset_manager", "investment_banker", "risk_manager", "ceo"]


def _case(case: dict | None) -> dict | None:
    if case is None:
        return None
    out = {k: v for k, v in case.items() if k not in ("fee", "parts")}
    out["fee_kobo"] = str(case["fee"])
    out["parts"] = [{**part, "terms": _terms_as_text(part["terms"])} for part in case["parts"]]
    return out


def _standing(conn: Connection, player: dict) -> dict:
    seen = ranks.standing(conn, player["id"], _exchange_time(conn))
    tracks = []
    for track in seen["tracks"]:
        row = {k: v for k, v in track.items() if k != "fee"}
        row["fee_kobo"] = None if track["fee"] is None else str(track["fee"])
        tracks.append(row)
    return {**seen, "tracks": tracks, "active": _case(seen["active"]), "past": [_case(c) for c in seen["past"]]}


def _step(conn: Connection, player: dict, action, bucket: str = "rank", attempts: int = 12) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        action(_exchange_time(conn))
    except (ranks.RankError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return _standing(conn, player)


class BeginRequest(Request):
    track: TRACK


class CaseAnswers(Request):
    # One small set of answers for each part of the case, by the part's code.
    answers: dict[str, dict[str, float | str | dict[str, str]]] = Field(max_length=6)

    @field_validator("answers")
    @classmethod
    def small(cls, value: dict) -> dict:
        for part, answers in value.items():
            if len(part) > 30 or len(answers) > 12:
                raise ValueError("That is too much to hand in.")
            for key, answer in answers.items():
                if len(key) > 30 or (isinstance(answer, str) and len(answer) > 30):
                    raise ValueError("That answer is too long.")
                texts = [part, key, answer] if isinstance(answer, str) else [part, key, *answer, *answer.values()] if isinstance(answer, dict) else [part, key]
                if any(ord(ch) < 32 or ord(ch) == 127 for text in texts for ch in text):
                    raise ValueError("That answer has characters in it that cannot be kept.")
                if isinstance(answer, float) and not math.isfinite(answer):
                    raise ValueError("Give an ordinary number.")
                if isinstance(answer, dict) and (len(answer) > 20 or any(len(k) > 30 or len(v) > 30 for k, v in answer.items())):
                    raise ValueError("That answer is too long.")
        return value


class ReportRequest(Request):
    objective_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000)
    case_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000)
    words: Words = Field(min_length=10, max_length=600)

    @model_validator(mode="after")
    def one_thing(self):
        if (self.objective_id is None) == (self.case_id is None):
            raise ValueError("Report one piece of work, or one rank case.")
        return self


@app.get("/api/ranks")
def my_ranks(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The gate ahead, what it needs, the case in hand, and past cases."""
    limits.allow("rank-read", str(player["id"]), attempts=90, per_seconds=60)
    return _standing(conn, player)


@app.post("/api/ranks/cases", status_code=status.HTTP_201_CREATED)
def begin_a_rank_case(body: BeginRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _step(conn, player, lambda now: ranks.begin(conn, player["id"], body.track, now), "rank-begin", 4)


@app.post("/api/ranks/cases/{case_id}/hand-in")
def hand_a_rank_case_in(body: CaseAnswers, case_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
                        player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _step(conn, player, lambda now: ranks.hand_in(conn, player["id"], case_id, body.answers, now))


@app.post("/api/reports", status_code=status.HTTP_201_CREATED)
def report_marking(body: ReportRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """A player reports a piece of work, or a rank case, whose marking they believe is wrong."""
    limits.allow("work-report", str(player["id"]), attempts=5, per_seconds=3600)
    try:
        ranks.report(conn, player["id"], body.words, _exchange_time(conn), objective_id=body.objective_id, case_id=body.case_id)
    except ranks.RankError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return {"words": "Thank you. Your report has been kept for the people who run the game to look at."}


@app.get("/api/league/builds/{build}")
def players_of_a_build(build: Literal["asset_manager", "asset_manager", "investment_banker", "risk_manager", "investment_banker", "investment_banker"],
                       player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Every player ranked within one build. The table is public."""
    limits.allow("league-read", str(player["id"]), attempts=60, per_seconds=60)
    return leagues.build_table(conn, build, player["id"])
