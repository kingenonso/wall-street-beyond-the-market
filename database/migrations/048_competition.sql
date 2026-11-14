-- Competition, part 1 (owner, 14 November 2026: "the main aim for this game is to compete with other empires and
-- players"; built on "build").
--
-- Contested mandates: a company that is raising money by selling new shares invites every empire to pitch to arrange
-- it. Each empire's banker names a fee and a forecast of how much of the issue will be taken up. The company chooses
-- for itself, from the record: the lowest fee, less what it trusts the banker for (their level, and how close their
-- empire's past forecasts came). The pitches are sealed until it chooses. The winner is paid its fee on what is raised.
--
-- Ranked work: each quarter, one company for each build, and one figure about it to forecast before the quarter is a
-- third gone. Entries are sealed until the quarter closes and the figure is known; then everybody is ranked by how
-- close they came, and the best entry of each empire earns its empire league points.

CREATE TABLE mandates (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    offer_id       bigint NOT NULL UNIQUE REFERENCES share_offers (id),
    company_id     uuid NOT NULL REFERENCES companies (id),
    period         integer NOT NULL,                       -- the quarter in which pitches are made and the offer closes
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'awarded', 'lapsed', 'settled')),
    winner_id      bigint,                                 -- the winning pitch
    taken_up_bps   integer,                                -- what share of the issue found buyers, once it is known
    fee_paid       bigint NOT NULL DEFAULT 0 CHECK (fee_paid >= 0),
    words          text,
    at             timestamptz NOT NULL
);
CREATE INDEX mandates_open ON mandates (status) WHERE status IN ('open', 'awarded');

CREATE TABLE mandate_pitches (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mandate_id     bigint NOT NULL REFERENCES mandates (id),
    empire_id      bigint NOT NULL REFERENCES empires (id),
    player_id      uuid NOT NULL REFERENCES players (id),
    fee_bps        integer NOT NULL CHECK (fee_bps > 0),
    take_up_bps    integer NOT NULL CHECK (take_up_bps BETWEEN 0 AND 10000),   -- the banker's forecast
    trust_bps      integer,                                -- what the company trusted the banker for, when it chose
    error_bps      integer,                                -- how far the forecast missed, once it is known
    at             timestamptz NOT NULL,
    UNIQUE (mandate_id, empire_id)                         -- one pitch for each empire: nobody pitches against their own
);
ALTER TABLE mandates ADD CONSTRAINT mandates_winner FOREIGN KEY (winner_id) REFERENCES mandate_pitches (id);

CREATE TABLE contests (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period         integer NOT NULL,
    build          text NOT NULL CHECK (build IN ('asset_manager', 'investment_banker', 'risk_manager')),
    company_id     uuid NOT NULL REFERENCES companies (id),
    measure        text NOT NULL CHECK (measure IN ('close_price', 'revenue', 'net_profit')),
    truth          bigint,                                 -- the figure, once the quarter has closed
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'judged', 'void')),
    at             timestamptz NOT NULL,
    UNIQUE (period, build)
);

CREATE TABLE contest_entries (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contest_id     bigint NOT NULL REFERENCES contests (id),
    player_id      uuid NOT NULL REFERENCES players (id),
    empire_id      bigint REFERENCES empires (id),         -- the empire they sat in when they entered
    guess          bigint NOT NULL,
    error_bps      integer,
    place          integer,
    points         integer NOT NULL DEFAULT 0,
    at             timestamptz NOT NULL,
    UNIQUE (contest_id, player_id)                         -- one entry each, and it cannot be changed
);
CREATE INDEX contest_entries_by_player ON contest_entries (player_id, id DESC);

-- A sealed answer stays as it was handed in.
CREATE FUNCTION contest_entry_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'An entry is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.guess <> OLD.guess OR NEW.player_id <> OLD.player_id OR NEW.at <> OLD.at THEN
        RAISE EXCEPTION 'A forecast is sealed when it is handed in.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE FUNCTION mandate_pitch_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'A pitch is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.fee_bps <> OLD.fee_bps OR NEW.take_up_bps <> OLD.take_up_bps OR NEW.empire_id <> OLD.empire_id OR NEW.at <> OLD.at THEN
        RAISE EXCEPTION 'A pitch is sealed when it is made.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER contest_entries_sealed BEFORE UPDATE OR DELETE ON contest_entries FOR EACH ROW EXECUTE FUNCTION contest_entry_sealed();
CREATE TRIGGER mandate_pitches_sealed BEFORE UPDATE OR DELETE ON mandate_pitches FOR EACH ROW EXECUTE FUNCTION mandate_pitch_sealed();
