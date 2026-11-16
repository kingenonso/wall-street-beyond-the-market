-- The Floor, slice 4 (owner, 16 November 2026, "go on"): the Floor inside live events, the daily floor hour, and the
-- wrongs a banker can do to a client, which the tribunal tries.

-- What the game says on the Floor: the bell, the halfway mark, the last minutes, a move in the featured share, the floor
-- hour. Each said once.
CREATE TABLE floor_notes (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key       text NOT NULL UNIQUE,
    at        timestamptz NOT NULL,
    kind      text NOT NULL CHECK (kind IN ('nudge', 'drop', 'hour')),
    words     text NOT NULL,
    ticker    text
);
CREATE INDEX floor_notes_by_time ON floor_notes (at DESC);

-- How the players did on the Floor during a live event, or a floor hour: the best banks (what they earned from the gap
-- in their prices) and the best clients (what they saved against the exchange). Places only are shown, never amounts.
CREATE TABLE floor_scores (
    window_key  text NOT NULL,                       -- 'live:<event id>' or 'hour:<date>'
    player_id   uuid NOT NULL REFERENCES players (id),
    role        text NOT NULL CHECK (role IN ('bank', 'client')),
    amount      bigint NOT NULL,
    place       integer NOT NULL CHECK (place BETWEEN 1 AND 3),
    points      integer NOT NULL DEFAULT 0,
    at          timestamptz NOT NULL,
    PRIMARY KEY (window_key, role, place)
);
CREATE INDEX floor_scores_by_player ON floor_scores (player_id);

-- The tribunal hears the Floor's wrongs: trading ahead of a client's request, passing one client's order to somebody else,
-- and banks agreeing their prices together.
ALTER TABLE court_cases DROP CONSTRAINT court_cases_kind_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_kind_check
    CHECK (kind IN ('insider', 'manipulation', 'undisclosed_stake', 'naked_short', 'insurance_fraud', 'front_running', 'order_leak', 'collusion'));
