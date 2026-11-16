-- Duels on the Floor (owner, 16 November 2026: "Duel on the Floor"): two empires run by players (or one against an
-- empire the computer runs) challenge each other for the next live event. Each is scored on what the event did to its
-- money plus what its bankers earned on the Floor during it, as a share of what it was worth at the bell. The higher
-- score wins league points. An empire may decline freely; three declines in a season are shown on its record.

CREATE TABLE floor_duels (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bell             timestamptz NOT NULL,                 -- the live event it is fought in
    challenger       bigint NOT NULL REFERENCES empires (id),
    challenged       bigint NOT NULL REFERENCES empires (id),
    season           integer NOT NULL,
    status           text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'accepted', 'declined', 'lapsed', 'withdrawn', 'scored', 'void')),
    created_at       timestamptz NOT NULL,
    answered_at      timestamptz,
    event_id         bigint REFERENCES live_events (id),
    challenger_bps   integer,
    challenged_bps   integer,
    winner           bigint REFERENCES empires (id),
    CHECK (challenger <> challenged)
);
-- One duel for an empire at each bell, as challenger or challenged, once accepted or still on offer.
CREATE INDEX floor_duels_by_bell ON floor_duels (bell, status);
CREATE INDEX floor_duels_by_season ON floor_duels (season, challenged, status);
