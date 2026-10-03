-- Stage 7: mastery, rank cases, the CEO rank, leagues, and resignation letters.

-- ---------------------------------------------------------------------------
-- Rank. A career stops at Levels 20, 40, 60 and 80 until that level's rank case is passed.
-- ---------------------------------------------------------------------------
ALTER TABLE careers ADD COLUMN rank smallint NOT NULL DEFAULT 0 CHECK (rank BETWEEN 0 AND 4);
ALTER TABLE players ADD COLUMN ceo_since timestamptz;            -- the day the CEO rank was earned

CREATE TABLE rank_cases (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id     uuid NOT NULL REFERENCES players (id),
    track         text NOT NULL,                 -- a build, or 'ceo'
    gate          smallint NOT NULL,             -- the level it lets the player past (60 for the CEO case)
    period        integer NOT NULL,
    fee           bigint NOT NULL CHECK (fee >= 0),
    terms         jsonb NOT NULL,                -- what the player is shown, and what the parts are
    state         text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'passed', 'failed', 'not_done')),
    submission    jsonb,
    result        jsonb,
    started_at    timestamptz NOT NULL,
    due_at        timestamptz NOT NULL,
    judged_at     timestamptz,
    CHECK ((state = 'active') = (judged_at IS NULL))
);
CREATE UNIQUE INDEX rank_cases_one_open ON rank_cases (player_id) WHERE state = 'active';
CREATE INDEX rank_cases_by_player ON rank_cases (player_id, id DESC);

-- A player may report a piece of work, or a rank case, whose marking they believe is wrong.
CREATE TABLE work_reports (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id     uuid NOT NULL REFERENCES players (id),
    objective_id  bigint REFERENCES objectives (id),
    rank_case_id  bigint REFERENCES rank_cases (id),
    template      text NOT NULL,
    words         text NOT NULL CHECK (length(words) BETWEEN 10 AND 600),
    at            timestamptz NOT NULL,
    CHECK ((objective_id IS NULL) <> (rank_case_id IS NULL))
);
CREATE UNIQUE INDEX work_reports_once ON work_reports (player_id, objective_id) WHERE objective_id IS NOT NULL;
CREATE UNIQUE INDEX work_reports_case_once ON work_reports (player_id, rank_case_id) WHERE rank_case_id IS NOT NULL;

ALTER TABLE career_events DROP CONSTRAINT career_events_kind_check;
ALTER TABLE career_events ADD CONSTRAINT career_events_kind_check CHECK (kind IN (
    'build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up', 'review_opened', 'review_closed', 'demoted', 'fund_chosen',
    'saving_changed', 'retired', 'early_withdrawal', 'joined_empire', 'left_empire', 'sacked', 'theft_proved', 'founded_empire',
    'fund_opened', 'struck_off', 'rank_case', 'rank_passed', 'ceo', 'resigned', 'counter_offer'));

-- ---------------------------------------------------------------------------
-- Signing limits: one flat figure for everybody (added by the owner, 3 October 2026).
-- A player-run empire starts at the same figure until its head sets another.
-- ---------------------------------------------------------------------------
ALTER TABLE empires ALTER COLUMN expense_limit SET DEFAULT 50000000;
UPDATE empires SET expense_limit = 50000000 WHERE kind = 'player' AND expense_limit = 0;

-- ---------------------------------------------------------------------------
-- Leagues: divisions, a points table for each game year, and what happened as each year ended.
-- ---------------------------------------------------------------------------
ALTER TABLE empires ADD COLUMN division smallint NOT NULL DEFAULT 1 CHECK (division >= 1);

CREATE TABLE league_points (               -- why each empire's points changed. Permanent.
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id  bigint NOT NULL REFERENCES empires (id),
    season     integer NOT NULL,           -- the game year
    period     integer NOT NULL,
    points     integer NOT NULL,
    why        text NOT NULL,
    reference  text,                       -- so that the same thing is never counted twice
    at         timestamptz NOT NULL
);
CREATE UNIQUE INDEX league_points_once ON league_points (empire_id, reference) WHERE reference IS NOT NULL;
CREATE INDEX league_points_by_season ON league_points (season, empire_id);

CREATE TABLE league_seasons (              -- how each empire ended each game year. Permanent.
    season      integer NOT NULL,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    division    smallint NOT NULL,
    place       smallint NOT NULL,
    points      integer NOT NULL,
    moved       text NOT NULL DEFAULT 'stayed' CHECK (moved IN ('up', 'down', 'stayed')),
    PRIMARY KEY (season, empire_id)
);

-- ---------------------------------------------------------------------------
-- Leaving an empire: a resignation letter, a counter-offer, and a notice period.
-- ---------------------------------------------------------------------------
CREATE TABLE empire_resignations (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    player_id     uuid NOT NULL REFERENCES players (id),
    letter        text NOT NULL CHECK (length(letter) <= 600),
    given_at      timestamptz NOT NULL,
    given_period  integer NOT NULL,
    leaves_at     timestamptz,             -- in an empire run by players: fourteen real days on
    leaves_period integer,                 -- in an empire run by the computer: when this quarter ends
    status        text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'withdrawn', 'stayed', 'left', 'released', 'overtaken')),
    offer_bonus   bigint CHECK (offer_bonus >= 0),          -- the counter-offer, if the head has made one
    offer_limit   bigint CHECK (offer_limit >= 0),
    offer_words   text CHECK (length(offer_words) <= 400),
    offered_at    timestamptz,
    ended_at      timestamptz
);
CREATE UNIQUE INDEX empire_resignations_one_waiting ON empire_resignations (player_id) WHERE status = 'waiting';

-- Electing a head: one vote each, for a member who has earned the CEO rank.
CREATE TABLE empire_head_votes (
    empire_id    bigint NOT NULL REFERENCES empires (id),
    voter_id     uuid NOT NULL REFERENCES players (id),
    candidate_id uuid NOT NULL REFERENCES players (id),
    at           timestamptz NOT NULL,
    PRIMARY KEY (empire_id, voter_id)
);

-- Work comes in three settings, and its template's code says which. The once-a-quarter rule is
-- unchanged: each setting of each piece of work has its own code.
ALTER TABLE objectives ADD COLUMN setting text NOT NULL DEFAULT 'solo' CHECK (setting IN ('solo', 'empire', 'live'));
ALTER TABLE objectives ADD COLUMN track text;        -- the syllabus map the work belongs to: a build, or 'ceo'
UPDATE objectives SET track = build;
UPDATE objectives SET setting = 'empire' WHERE terms ? 'step_id' OR template = 'lw_pact';
ALTER TABLE objectives ALTER COLUMN track SET NOT NULL;

-- The quarter in which capital was put into an empire (or handed back), so that a year's growth
-- can be measured with it left out.
ALTER TABLE empire_capital ADD COLUMN period integer;

-- Work that names no track belongs to the map of the build it was done in.
CREATE FUNCTION objectives_track_default() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.track IS NULL THEN
        NEW.track := NEW.build;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER objectives_track_default BEFORE INSERT ON objectives FOR EACH ROW EXECUTE FUNCTION objectives_track_default();
