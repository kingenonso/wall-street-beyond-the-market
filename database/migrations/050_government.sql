-- Government, part 1 (owner: the Government Leader is an elected office; "build" given 14 November 2026).
--
-- Each game year the players elect a Government Leader. Candidates stand in the last quarter of a year; every player
-- past the protected start has one vote; the count is made as the year closes. A leader sets the year's budget: the rates
-- of income tax, company tax, and property and land tax, each within limits. The Assembly passes the budget or throws
-- it out: the head of every empire run by players sits in it beside computer-run members whose leanings are published.
-- The Assembly can also remove the leader by a vote of no confidence. When there is no leader (nobody stood, nobody
-- voted, the leader was removed, or did not put a budget by the deadline), a stand-in run by rules governs, with a
-- personality drawn by lot and published.

CREATE TABLE government_terms (
    year             integer PRIMARY KEY,                      -- the game year governed
    leader_id        uuid REFERENCES players (id),             -- null: the stand-in governs
    votes            integer NOT NULL DEFAULT 0,               -- what the leader won with
    stand_in         text NOT NULL CHECK (stand_in IN ('steady', 'hawk', 'dove')),   -- who governs when nobody else does
    removed_period   integer,                                  -- removed by the Assembly in this quarter
    words            text NOT NULL,
    at               timestamptz NOT NULL
);

CREATE TABLE government_candidates (
    year             integer NOT NULL,                         -- the year they would govern
    player_id        uuid NOT NULL REFERENCES players (id),
    pitch            text NOT NULL CHECK (length(pitch) BETWEEN 1 AND 400),
    at               timestamptz NOT NULL,
    PRIMARY KEY (year, player_id)
);

CREATE TABLE government_votes (
    year             integer NOT NULL,
    voter_id         uuid NOT NULL REFERENCES players (id),
    candidate_id     uuid NOT NULL REFERENCES players (id),
    at               timestamptz NOT NULL,
    PRIMARY KEY (year, voter_id)                               -- one vote each, and it is not changed
);

-- The rates in force. Changed only by a budget the Assembly passed, or by the stand-in's budget.
CREATE TABLE tax_rates (
    kind             text PRIMARY KEY CHECK (kind IN ('income', 'company', 'property', 'land')),
    bps              integer NOT NULL CHECK (bps >= 0),
    since_period     integer NOT NULL,
    set_by           text NOT NULL
);

CREATE TABLE budgets (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year             integer NOT NULL,
    period           integer NOT NULL,                         -- put to the Assembly in this quarter; counted when it closes
    proposed_by      uuid REFERENCES players (id),             -- null: the stand-in's budget
    rates            jsonb NOT NULL,                           -- {kind: bps}
    status           text NOT NULL DEFAULT 'voting' CHECK (status IN ('voting', 'passed', 'rejected')),
    votes_for        integer,
    votes_against    integer,
    words            text,
    at               timestamptz NOT NULL
);
CREATE UNIQUE INDEX budgets_one_a_year ON budgets (year);

CREATE TABLE motions (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year             integer NOT NULL,
    period           integer NOT NULL,
    kind             text NOT NULL CHECK (kind IN ('no_confidence')),
    proposed_by      uuid NOT NULL REFERENCES players (id),
    status           text NOT NULL DEFAULT 'voting' CHECK (status IN ('voting', 'passed', 'failed')),
    votes_for        integer,
    votes_against    integer,
    at               timestamptz NOT NULL
);
CREATE UNIQUE INDEX motions_one_open ON motions (year, kind) WHERE status = 'voting';

-- What each member of the Assembly who is a player voted. The computer-run members' votes are worked out from their
-- published leanings when the count is made, and recorded in the budget's or motion's totals.
CREATE TABLE assembly_votes (
    subject          text NOT NULL,                            -- 'budget:<id>' or 'motion:<id>'
    player_id        uuid NOT NULL REFERENCES players (id),
    empire_id        bigint NOT NULL REFERENCES empires (id),  -- the empire whose seat they hold
    vote             boolean NOT NULL,
    at               timestamptz NOT NULL,
    PRIMARY KEY (subject, empire_id)                           -- one vote for each empire's seat
);

CREATE FUNCTION government_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'A vote is cast once and kept.' USING ERRCODE = 'restrict_violation';
END $$;
CREATE TRIGGER government_votes_sealed BEFORE UPDATE OR DELETE ON government_votes FOR EACH ROW EXECUTE FUNCTION government_sealed();
CREATE TRIGGER assembly_votes_sealed BEFORE UPDATE OR DELETE ON assembly_votes FOR EACH ROW EXECUTE FUNCTION government_sealed();
