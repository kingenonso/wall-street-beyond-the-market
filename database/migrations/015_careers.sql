-- Stage 5: players as professionals.
--
-- A player chooses a build (their profession), is hired by a company, is paid a salary by that
-- company out of its own cash, chooses one of the six banks, saves for retirement, and takes on
-- professional objectives that the server checks against the game's own records.
-- Nothing here makes money: every payment has a named payer.

-- ---------------------------------------------------------------------------
-- The build, and the career in it.
-- ---------------------------------------------------------------------------
ALTER TABLE players ADD COLUMN build text CHECK (build IN ('asset_manager', 'accountant'));
ALTER TABLE players ADD COLUMN build_changed_at timestamptz;

-- One row for each build a player has worked in. The level is worked out from the experience,
-- so it cannot be set by hand. A player may hold up to three builds.
CREATE TABLE careers (
    player_id        uuid NOT NULL REFERENCES players (id),
    build            text NOT NULL CHECK (build IN ('asset_manager', 'accountant')),
    experience       integer NOT NULL DEFAULT 0 CHECK (experience >= 0),
    -- A performance review is open or it is not. While one is open, the next five pieces of
    -- work finished decide how it ends.
    review_open      boolean NOT NULL DEFAULT false,
    review_opened_at timestamptz,
    review_from      bigint,                   -- only work judged after this point (objectives.judged_seq) counts towards the review
    reviewed_up_to   bigint NOT NULL DEFAULT 0, -- failures up to this point have already been answered for
    started_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, build)
);

-- The player's professional record: every step up, every review, every job. Never changed.
CREATE TABLE career_events (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id  uuid NOT NULL REFERENCES players (id),
    build      text,
    kind       text NOT NULL CHECK (kind IN ('build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up',
                                             'review_opened', 'review_closed', 'demoted', 'fund_chosen')),
    words      text NOT NULL,
    at         timestamptz NOT NULL
);
CREATE INDEX career_events_by_player ON career_events (player_id, id DESC);
CREATE TRIGGER career_events_permanent BEFORE UPDATE OR DELETE ON career_events
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER career_events_no_truncate BEFORE TRUNCATE ON career_events
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Jobs. A player has one employer at a time.
-- ---------------------------------------------------------------------------
CREATE TABLE employments (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id      uuid NOT NULL REFERENCES players (id),
    company_id     uuid NOT NULL REFERENCES companies (id),
    build          text NOT NULL CHECK (build IN ('asset_manager', 'accountant')),
    started_at     timestamptz NOT NULL,
    started_period integer NOT NULL,            -- the quarter that was running when they started
    started_day    integer NOT NULL CHECK (started_day BETWEEN 1 AND 90),
    ended_at       timestamptz,
    ended_period   integer,
    ended_reason   text
);
CREATE TRIGGER employments_no_delete BEFORE DELETE ON employments
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER employments_no_truncate BEFORE TRUNCATE ON employments
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
CREATE UNIQUE INDEX employments_one_job ON employments (player_id) WHERE ended_at IS NULL;
CREATE INDEX employments_by_company ON employments (company_id) WHERE ended_at IS NULL;

-- One payslip for each player for each quarter. Never changed.
CREATE TABLE payslips (
    player_id         uuid NOT NULL REFERENCES players (id),
    period            integer NOT NULL,
    employment_id     bigint NOT NULL REFERENCES employments (id),
    company_id        uuid NOT NULL REFERENCES companies (id),
    build             text NOT NULL,
    level             integer NOT NULL,
    days_worked       integer NOT NULL CHECK (days_worked BETWEEN 0 AND 90),
    worked            boolean NOT NULL,          -- did they finish any piece of work since the last pay day?
    gross             bigint NOT NULL CHECK (gross >= 0),
    pension_yours     bigint NOT NULL CHECK (pension_yours >= 0),
    pension_employer  bigint NOT NULL CHECK (pension_employer >= 0),
    tax               bigint NOT NULL CHECK (tax >= 0),
    living_costs      bigint NOT NULL CHECK (living_costs >= 0),
    take_home         bigint NOT NULL CHECK (take_home >= 0),
    paid              bigint NOT NULL CHECK (paid >= 0),       -- of the take-home pay, what arrived on pay day
    owed              bigint NOT NULL CHECK (owed >= 0),       -- what the employer could not pay and still owes
    note              text NOT NULL DEFAULT '',
    created_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, period),
    CHECK (gross = pension_yours + tax + living_costs + take_home),
    CHECK (paid + owed = take_home)
);
CREATE TRIGGER payslips_permanent BEFORE UPDATE OR DELETE ON payslips
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER payslips_no_truncate BEFORE TRUNCATE ON payslips
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- The player's bank: one of the six. It pays interest on cash left with it.
-- ---------------------------------------------------------------------------
CREATE TABLE bank_customers (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id    uuid NOT NULL REFERENCES players (id),
    company_id   uuid NOT NULL REFERENCES companies (id),
    since        timestamptz NOT NULL,
    since_period integer NOT NULL,
    recorded_at  timestamptz NOT NULL DEFAULT now(),   -- the database's own clock, to set beside the ledger's
    ended_at     timestamptz
);
CREATE TRIGGER bank_customers_no_delete BEFORE DELETE ON bank_customers
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER bank_customers_no_truncate BEFORE TRUNCATE ON bank_customers
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
CREATE UNIQUE INDEX bank_customers_one_bank ON bank_customers (player_id) WHERE ended_at IS NULL;

CREATE TABLE deposit_interest (
    player_id       uuid NOT NULL REFERENCES players (id),
    period          integer NOT NULL,
    company_id      uuid NOT NULL REFERENCES companies (id),
    lowest_balance  bigint NOT NULL CHECK (lowest_balance >= 0),
    rate_bps        integer NOT NULL CHECK (rate_bps >= 0),
    amount          bigint NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (player_id, period)
);
CREATE TRIGGER deposit_interest_permanent BEFORE UPDATE OR DELETE ON deposit_interest
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER deposit_interest_no_truncate BEFORE TRUNCATE ON deposit_interest
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Retirement savings. The money itself is with the pension funds (it was paid to them with
-- everybody else's pension contributions). This is the player's claim on it. It is locked.
-- ---------------------------------------------------------------------------
CREATE TABLE retirement_accounts (
    player_id       uuid PRIMARY KEY REFERENCES players (id),
    fund            text NOT NULL DEFAULT 'balanced' CHECK (fund IN ('growth', 'balanced', 'cautious', 'income')),
    value           bigint NOT NULL DEFAULT 0 CHECK (value >= 0),
    fund_chosen_period integer,                 -- a player may change fund once in a game year
    previous_fund   text                        -- the fund held before the last change: it earns for the quarter of the change
);

CREATE TABLE retirement_entries (
    player_id          uuid NOT NULL REFERENCES players (id),
    period             integer NOT NULL,
    fund               text NOT NULL,
    opening            bigint NOT NULL,
    growth             bigint NOT NULL,          -- may be a loss
    paid_in_by_you     bigint NOT NULL CHECK (paid_in_by_you >= 0),
    paid_in_by_employer bigint NOT NULL CHECK (paid_in_by_employer >= 0),
    closing            bigint NOT NULL CHECK (closing >= 0),
    PRIMARY KEY (player_id, period)
);
CREATE TRIGGER retirement_entries_permanent BEFORE UPDATE OR DELETE ON retirement_entries
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER retirement_entries_no_truncate BEFORE TRUNCATE ON retirement_entries
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- What each kind of fund earned in each quarter, and the index level it was measured from.
CREATE TABLE pension_fund_results (
    period        integer NOT NULL,
    fund          text NOT NULL CHECK (fund IN ('growth', 'balanced', 'cautious', 'income')),
    return_bps    integer NOT NULL,
    index_level   bigint NOT NULL,
    PRIMARY KEY (period, fund)
);
CREATE TRIGGER pension_fund_results_permanent BEFORE UPDATE OR DELETE ON pension_fund_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER pension_fund_results_no_truncate BEFORE TRUNCATE ON pension_fund_results
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Professional objectives: pieces of practical work. The server sets the terms, judges the
-- result from the game's own records, and has the named payer pay.
-- ---------------------------------------------------------------------------
CREATE TABLE objectives (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id         uuid NOT NULL REFERENCES players (id),
    build             text NOT NULL CHECK (build IN ('asset_manager', 'accountant')),
    template          text NOT NULL,
    module            text NOT NULL,
    period            integer NOT NULL,          -- the quarter that was running when it was taken on
    client_company_id uuid REFERENCES companies (id),
    payer_account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    payer_name        text NOT NULL,
    title             text NOT NULL,
    terms             jsonb NOT NULL,            -- fixed when it is taken on; never changed afterwards
    reward            bigint NOT NULL CHECK (reward >= 0),
    experience        integer NOT NULL CHECK (experience >= 0),
    accepted_at       timestamptz NOT NULL,
    state             text NOT NULL DEFAULT 'active'
                      CHECK (state IN ('active', 'passed', 'failed', 'not_done', 'withdrawn')),
    progress          jsonb NOT NULL DEFAULT '{}',
    submission        jsonb,
    submitted_at      timestamptz,
    result            jsonb,
    judged_at         timestamptz,
    judged_period     integer,                   -- the quarter the result counts in, for pay day
    judged_seq        bigint,                    -- the order in which objectives were judged
    paid              bigint NOT NULL DEFAULT 0 CHECK (paid >= 0 AND paid <= reward),
    -- One of each kind of work in a quarter: it cannot be taken again to try for a better result.
    UNIQUE (player_id, build, template, period),
    CHECK ((state = 'active') = (judged_at IS NULL))
);
CREATE SEQUENCE objectives_judged_seq;
CREATE INDEX objectives_active ON objectives (state) WHERE state = 'active';
CREATE INDEX objectives_by_player ON objectives (player_id, id DESC);

-- Once judged, an objective is a permanent record. While active, its terms cannot be changed.
CREATE FUNCTION objectives_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'An objective is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.state <> 'active' THEN
        RAISE EXCEPTION 'This objective has been judged. Its record cannot be changed.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.player_id <> OLD.player_id OR NEW.template <> OLD.template OR NEW.terms <> OLD.terms OR NEW.reward <> OLD.reward
       OR NEW.experience <> OLD.experience OR NEW.payer_account_id <> OLD.payer_account_id OR NEW.period <> OLD.period
       OR NEW.accepted_at <> OLD.accepted_at OR NEW.build <> OLD.build OR NEW.payer_name <> OLD.payer_name
       OR NEW.title <> OLD.title OR NEW.module <> OLD.module
       OR NEW.client_company_id IS DISTINCT FROM OLD.client_company_id THEN
        RAISE EXCEPTION 'The terms of an objective are fixed when it is taken on.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.submission IS NOT NULL AND NEW.submission IS DISTINCT FROM OLD.submission THEN
        RAISE EXCEPTION 'Work that has been handed in cannot be changed.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER objectives_guarded BEFORE UPDATE OR DELETE ON objectives
    FOR EACH ROW EXECUTE FUNCTION objectives_guard();
CREATE TRIGGER objectives_no_truncate BEFORE TRUNCATE ON objectives
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- The Money Watch gains a measure: what was paid to players in the quarter, by reason.
-- ---------------------------------------------------------------------------
ALTER TABLE money_watch_results ADD COLUMN paid_to_players jsonb NOT NULL DEFAULT '{}';
