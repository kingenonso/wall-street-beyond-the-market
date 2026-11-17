-- Floor extras, slice 1 (owner, 17 November 2026: "build"): flash storms and the risk engine.
--
-- A flash storm: without warning, for ten minutes, clients flood the open desks with calls, mostly in one share, bigger
-- and with shorter countdowns. Its best desks and clients are named and earn their empires league points.
--
-- The risk engine: every banker's desk has three limits, set by the Risk Manager (or the head) of the banker's empire, or
-- the Floor's own if the banker has no empire: the largest single deal, the most held in one share from the Floor today,
-- and the most the desk may lose in a day. A price that would break a limit is refused; a day's loss past the limit freezes
-- the desk until the next trading day.

CREATE TABLE floor_storms (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slot       bigint NOT NULL UNIQUE,                       -- the ten-minute slot it was drawn for
    starts_at  timestamptz NOT NULL,
    ends_at    timestamptz NOT NULL,
    company_id uuid NOT NULL REFERENCES companies (id),      -- the share most of its calls are in
    reason     text NOT NULL,
    scored     boolean NOT NULL DEFAULT false
);

CREATE TABLE floor_limits (
    player_id     uuid PRIMARY KEY REFERENCES players (id),  -- the banker
    deal_most     bigint NOT NULL CHECK (deal_most > 0),
    name_most     bigint NOT NULL CHECK (name_most > 0),
    day_loss_most bigint NOT NULL CHECK (day_loss_most > 0),
    set_by        uuid NOT NULL REFERENCES players (id),
    set_at        timestamptz NOT NULL
);

CREATE TABLE floor_freezes (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id  uuid NOT NULL REFERENCES players (id),
    day        date NOT NULL,                                -- the trading day it was frozen for
    loss       bigint NOT NULL,
    limit_was  bigint NOT NULL,
    at         timestamptz NOT NULL,
    UNIQUE (player_id, day)
);

ALTER TABLE floor_notes DROP CONSTRAINT floor_notes_kind_check;
ALTER TABLE floor_notes ADD CONSTRAINT floor_notes_kind_check CHECK (kind IN ('nudge', 'drop', 'hour', 'storm', 'risk'));
