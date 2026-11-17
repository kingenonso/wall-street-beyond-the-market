-- Unions and strikes, part 4: strike waves and the general strike (owner, 17 November 2026: "go on").
--
-- When most of an industry's staff are angry at once, the union lodges one industry-wide demand (a wave) instead of
-- company by company. The employers the computer runs answer it together; a refusal is a strike across all of them.
-- Companies a player-run empire controls are still answered by their head, on the wave's terms.
--
-- Rarely, when prices have outrun pay hard and several industries are out at once, the National Labour Federation gives
-- notice of a general strike and asks the Government for a cost-of-living award to households. The Government Leader
-- (or the stand-in, by its rule) concedes, paying the award from the Treasury, or refuses: then the exchange closes for at
-- most two real days, orders waiting in the queue, and every industry with a union loses days of sales.

CREATE TABLE union_waves (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    union_id      integer NOT NULL REFERENCES unions (id),
    period        integer NOT NULL,
    opened_day    integer NOT NULL CHECK (opened_day BETWEEN 1 AND 90),
    deadline_day  integer NOT NULL CHECK (deadline_day BETWEEN 1 AND 90),
    companies     integer NOT NULL CHECK (companies >= 1),       -- the employers the computer runs, answered together
    anger_bps     integer NOT NULL,
    reasons       jsonb NOT NULL DEFAULT '[]',
    demand_bps    integer NOT NULL CHECK (demand_bps > 0),
    offer_bps     integer,
    settled_bps   integer,
    strike_days   integer,
    ends_day      integer,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'agreed', 'struck', 'ended')),
    decided_at    timestamptz,
    UNIQUE (union_id, period),
    CHECK (deadline_day > opened_day)
);

ALTER TABLE union_disputes ADD COLUMN wave_id integer REFERENCES union_waves (id);
-- A wave's members: the companies the computer runs that it speaks for.
CREATE TABLE union_wave_members (
    wave_id     integer NOT NULL REFERENCES union_waves (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    event_id    bigint REFERENCES events (id),
    PRIMARY KEY (wave_id, company_id)
);

CREATE TABLE general_strikes (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period        integer NOT NULL UNIQUE,
    notice_day    integer NOT NULL CHECK (notice_day BETWEEN 1 AND 90),
    deadline_day  integer NOT NULL CHECK (deadline_day BETWEEN 1 AND 90),
    squeeze_bps   integer NOT NULL,
    waves         integer NOT NULL,
    award         bigint NOT NULL CHECK (award > 0),             -- the cost-of-living award asked of the Treasury
    status        text NOT NULL DEFAULT 'notice' CHECK (status IN ('notice', 'conceded', 'striking', 'over')),
    answer        text CHECK (answer IN ('concede', 'refuse', 'stand_in_concede', 'stand_in_refuse')),
    answered_by   uuid REFERENCES players (id),
    strike_from   timestamptz,
    strike_until  timestamptz,
    strike_days   integer,
    decided_at    timestamptz
);

ALTER TABLE market_status ADD COLUMN strike_until timestamptz;   -- a general strike closes the exchange until then

ALTER TABLE prediction_markets DROP CONSTRAINT prediction_markets_kind_check;
ALTER TABLE prediction_markets ADD CONSTRAINT prediction_markets_kind_check
    CHECK (kind IN ('rate_rise', 'profit_beat', 'live_kind', 'live_fall', 'union_wave', 'general_strike'));
