"""Stage 10, Part 1: the newsroom on the website.

A journalist writes from confirmed facts only, so nothing a player sends here can put a figure in print. Nobody is
ever sent another player's draft, their empire's holdings, or a fact that is not yet public. Searching the archive and
"Why?" return only what is dated up to today.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, Query, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import wire
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import articles, careers, chronicle, clock, newsroom, newsroom_facts, ripple
from simulation import news as wire_news


def _act(conn: Connection, player: dict, action, bucket: str = "newsroom", attempts: int = 40) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (newsroom.NewsroomError, chronicle.ChronicleError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    return {"result": wire(result) if isinstance(result, (dict, list)) else result}


def _today(conn: Connection) -> tuple[int, int]:
    w = careers.world_now(conn, _exchange_time(conn))
    return w["period"], w["day"]


def _card(c: dict) -> dict:
    return {k: c[k] for k in ("id", "kind", "title", "line", "tickers", "tone", "record", "importance")}


class FactRequest(Request):
    fact_id: str = Field(min_length=3, max_length=80)


class WordsRequest(Request):
    angle: Literal["straight", "what_it_means", "who_wins"] = "straight"
    comment: str = Field(default="", max_length=400)
    declared: bool = False


class AskRequest(Request):
    ticker: str | None = Field(default=None, pattern=r"^[A-Z]{2,5}$")
    empire: str | None = Field(default=None, min_length=3, max_length=40)
    question: str = Field(min_length=10, max_length=300)


class AnswerRequest(Request):
    words: str | None = Field(default=None, max_length=300)


class AccountRequest(Request):
    words: str = Field(min_length=40, max_length=1200)
    evidence: list[int] = Field(default_factory=list, max_length=5)


@app.get("/api/newsroom")
def newsroom_desk(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if player.get("build") != "investment_banker":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The newsroom is for Financial Journalists.")
    now = _exchange_time(conn)
    return {"desk": wire(newsroom.view(conn, player["id"], now))}


@app.get("/api/newsroom/facts")
def newsroom_facts_list(ticker: str | None = Query(default=None, pattern=r"^[A-Z]{2,5}$"),
                        player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("newsroom-facts", str(player["id"]), attempts=60, per_seconds=60)
    cards = newsroom_facts.facts(conn, _exchange_time(conn))
    if ticker:
        cards = [c for c in cards if ticker in c["tickers"]]
    return {"facts": [_card(c) for c in cards[:120]]}


@app.post("/api/newsroom/story", status_code=201)
def newsroom_start(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.start(conn, player["id"], now))


@app.post("/api/newsroom/facts")
def newsroom_add(body: FactRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.add_fact(conn, player["id"], body.fact_id, now))


@app.post("/api/newsroom/facts/remove")
def newsroom_remove(body: FactRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.remove_fact(conn, player["id"], body.fact_id, now))


@app.post("/api/newsroom/check")
def newsroom_check(body: FactRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.check_fact(conn, player["id"], body.fact_id, now))


@app.put("/api/newsroom/words")
def newsroom_words(body: WordsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.set_words(conn, player["id"], body.angle, body.comment, body.declared, now))


@app.post("/api/newsroom/ask")
def newsroom_ask(body: AskRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if bool(body.ticker) == bool(body.empire):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ask a company or an empire.")
    return _act(conn, player, lambda now: newsroom.ask(conn, player["id"], ticker=body.ticker, empire_name=body.empire,
                                                        question=body.question, now=now), bucket="newsroom-ask", attempts=10)


@app.post("/api/newsroom/publish")
def newsroom_publish(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    # (Never the news item's number: it would show how many items are still to come this quarter.)
    return _act(conn, player, lambda now: _no_number(newsroom.publish(conn, player["id"], now)), bucket="newsroom-publish", attempts=6)


def _no_number(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "news_item_id"}


@app.post("/api/newsroom/drop")
def newsroom_drop(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.drop(conn, player["id"], now))


@app.post("/api/newsroom/stories/{story_id}/correct")
def newsroom_correct(story_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: _no_number(newsroom.correct(conn, player["id"], story_id, now)))


@app.post("/api/stories/{story_id}/expose")
def story_expose(story_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.expose(conn, player["id"], story_id, now), bucket="newsroom-expose", attempts=10)


@app.get("/api/interviews")
def interviews_waiting(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return {"questions": wire(newsroom.to_answer(conn, player["id"], _exchange_time(conn)))}


@app.post("/api/interviews/{interview_id}/answer")
def interview_answer(interview_id: int, body: AnswerRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.answer(conn, player["id"], interview_id, body.words, now))


@app.get("/api/stories")
def stories_list(author: str | None = Query(default=None, min_length=3, max_length=40),
                 player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    period, day = _today(conn)
    author_id = None
    if author:
        row = conn.execute("SELECT id FROM players WHERE lower(display_name) = lower(%s)", (author,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no player of that name.")
        author_id = row["id"]
    found = newsroom.public_stories(conn, period, day, author_id=author_id)
    for s in found:
        s["label"] = clock.period_label(s["period"])
    out = {"stories": wire(found)}
    if author_id:
        out["profile"] = newsroom.profile(conn, author_id)
    return out


@app.get("/api/news/archive")
def news_archive(q: str | None = Query(default=None, min_length=2, max_length=60), ticker: str | None = Query(default=None, pattern=r"^[A-Z]{2,5}$"),
                 before_period: int | None = Query(default=None, ge=1), player: dict = Depends(current_player),
                 conn: Connection = Depends(get_connection)):
    """Every story ever published, searchable. Only what is dated up to today."""
    limits.allow("news-archive", str(player["id"]), attempts=60, per_seconds=60)
    period, day = _today(conn)
    cond = ["(period < %s OR (period = %s AND day <= %s))"]
    params: list = [period, period, day]
    if q:
        cond.append("(headline ILIKE %s OR body ILIKE %s)")
        like = "%" + q.replace("%", "").replace("_", "") + "%"
        params += [like, like]
    if ticker:
        cond.append("%s = ANY(tickers)")
        params.append(ticker)
    if before_period:
        cond.append("period < %s")
        params.append(before_period)
    rows = conn.execute(f"SELECT id, period, day, outlet, kind, story, headline, body, tickers, follows, facts->>'author' AS author FROM news_items"
                        f" WHERE {' AND '.join(cond)} ORDER BY period DESC, day DESC, id DESC LIMIT 50", params).fetchall()
    from simulation import news_kinds
    from server.main import news_ref
    return {"items": [{"ref": news_ref(r), "period": r["period"], "day": r["day"], "outlet": news_kinds.outlet_name(r["outlet"]), "kind": r["kind"],
                       "headline": r["headline"], "body": r["body"], "tickers": r["tickers"], "follows_up": r["follows"] is not None,
                       "author": r["author"], "label": clock.period_label(r["period"])} for r in rows]}


def _visible_item(conn: Connection, ref: str) -> dict:
    from server.main import news_by_ref
    period, day = _today(conn)
    row = news_by_ref(conn, ref)
    if row is None or (row["period"], row["day"]) > (period, day):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such story.")
    return row


@app.get("/api/news/article")
def news_article(ref: str = Query(min_length=8, max_length=400, pattern=r"^[A-Za-z0-9_\-]+$"), player: dict = Depends(current_player),
                 conn: Connection = Depends(get_connection)):
    limits.allow("news-article", str(player["id"]), attempts=60, per_seconds=60)
    item = _visible_item(conn, ref)
    period, day = _today(conn)
    found = articles.article(conn, item["id"], period, day, _exchange_time(conn))
    # The items of the same affair around this one (the five before it and the five after it that are already out).
    before = conn.execute("SELECT id, period, day, headline FROM news_items WHERE story = %s AND (period, day, id) < (%s, %s, %s)"
                          " ORDER BY period DESC, day DESC, id DESC LIMIT 5", (item["story"], item["period"], item["day"], item["id"])).fetchall()
    after = conn.execute("SELECT id, period, day, headline FROM news_items WHERE story = %s AND (period, day, id) >= (%s, %s, %s)"
                         " AND (period < %s OR (period = %s AND day <= %s)) ORDER BY period, day, id LIMIT 6",
                         (item["story"], item["period"], item["day"], item["id"], period, period, day)).fetchall()
    thread = list(reversed(before)) + list(after)
    return {"article": found, "thread": [{"label": clock.period_label(t["period"]), "day": t["day"], "headline": t["headline"],
                                          "this": t["id"] == item["id"]} for t in thread],
            "why": why_key(conn, item)}


def why_key(conn: Connection, item: dict) -> str | None:
    """The Ripple's key for what a news item reports."""
    kind, tickers, period = item["kind"], item["tickers"] or [], item["period"]
    from simulation import articles as a
    family = a.FAMILY.get(kind)
    if family == "results" and tickers:
        return f"results:{tickers[0]}:{period - 1}"
    if family == "rating" and tickers:
        return f"rating:{tickers[0]}:{period - 1}"
    if family == "rate":
        return f"rate:{period - 1}"
    if kind in ("player_story", "correction") and (item.get("facts") or {}).get("story_id"):
        return f"story:{item['facts']['story_id']}"
    from simulation import events
    if kind in events.BY_NAME:
        found = conn.execute("SELECT * FROM events WHERE kind = %s AND period = %s AND day = %s ORDER BY id", (kind, period, item["day"])).fetchall()
        from simulation import ripple as r
        companies = {c["id"]: c for c in conn.execute("SELECT id, ticker, sector, headquarters FROM companies").fetchall()}
        for e in found:
            # The event this item reports: the one that touches the companies it names (or the only one of its kind that day).
            if len(found) == 1 or any(events.touches(e, c) for c in companies.values() if c["ticker"] in tickers):
                return r.event_key(conn, e)
    return None


@app.get("/api/why")
def why_chain(key: str = Query(min_length=3, max_length=80, pattern=r"^[a-z]+:[A-Za-z0-9 :\-]+$"),
              player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """What led to something, at three depths. Only links recorded up to the last closed quarter, or today's stories."""
    limits.allow("why", str(player["id"]), attempts=60, per_seconds=60)
    period, _ = _today(conn)
    found = ripple.chain(conn, key, visible_period=period)
    return wire(found)


@app.get("/api/chronicle")
def chronicle_read(layer: Literal["personal", "company", "world"] = "world", ticker: str | None = Query(default=None, pattern=r"^[A-Z]{2,5}$"),
                   player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    period, day = _today(conn)
    found = chronicle.entries(conn, layer, player_id=player["id"], company_ticker=ticker, period_now=period, day_now=day)
    return {"entries": wire(found)}


@app.post("/api/chronicle/{entry_id}/accounts", status_code=201)
def chronicle_account(entry_id: int, body: AccountRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    period, _ = _today(conn)
    return _act(conn, player, lambda now: chronicle.add_account(conn, player["id"], entry_id, body.words, body.evidence, period, now),
                bucket="chronicle", attempts=10)


_ = wire_news
