-- Private equity stage, part 1: the empire becomes a working firm.
--
-- The frame every desk works inside:
--   titles          a deputy head, and a lead for each desk
--   approvals       a request one desk must decide before something happens; it never waits for ever
--   resolutions     what the members of an empire vote on
--   articles        the empire's own rules, as the members have voted them
--   duties          the standing work of each desk every quarter, and its score
--   documents       papers a Lawyer reads before the head signs: some clauses are traps
--   opinions        what a member put their name to, checked later against what happened
--   the record      what a head did, kept for good and carried from empire to empire
--   debts, units    what an empire owes, and who owns how much of it

ALTER TABLE empires ADD COLUMN rival_id bigint REFERENCES empires (id);
ALTER TABLE empire_seats ADD COLUMN frozen boolean NOT NULL DEFAULT false;      -- the Risk Manager has stopped this member's trading
ALTER TABLE empire_books ADD COLUMN desk text;                                  -- the desk a cost belongs to, for its budget
ALTER TABLE empire_books DROP CONSTRAINT empire_books_kind_check;
ALTER TABLE empire_books ADD CONSTRAINT empire_books_kind_check CHECK (kind IN ('cost', 'staff_pay', 'bonus', 'step', 'fee', 'taken', 'interest'));

CREATE TABLE empire_titles (
    empire_id   bigint NOT NULL REFERENCES empires (id),
    title       text NOT NULL CHECK (title IN ('deputy', 'lead')),
    build       text NOT NULL DEFAULT '',                    -- the desk, for a lead
    player_id   uuid NOT NULL REFERENCES players (id),
    since       timestamptz NOT NULL,
    PRIMARY KEY (empire_id, title, build)
);

CREATE TABLE empire_approvals (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL,                               -- expense, trade, deal, legal, idea, venture ...
    desk        text NOT NULL,                               -- the desk that decides: a build, or 'head'
    asked_by    uuid REFERENCES players (id),                -- empty when the empire itself asked
    title       text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    amount      bigint NOT NULL DEFAULT 0 CHECK (amount >= 0),
    payload     jsonb NOT NULL DEFAULT '{}',
    status      text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'approved', 'refused', 'overruled', 'lapsed')),
    reason      text CHECK (length(reason) <= 400),
    decided_by  uuid REFERENCES players (id),
    decided_as  text CHECK (decided_as IN ('desk', 'head', 'deputy', 'staff')),
    period      integer NOT NULL,
    asked_at    timestamptz NOT NULL,
    decided_at  timestamptz,
    overruled_by uuid REFERENCES players (id),
    overruled_at timestamptz,
    overrule_reason text CHECK (length(overrule_reason) <= 400)
);
CREATE INDEX empire_approvals_waiting ON empire_approvals (empire_id) WHERE status = 'waiting';

CREATE FUNCTION empire_approvals_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'A decision is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.empire_id <> OLD.empire_id OR NEW.kind <> OLD.kind OR NEW.asked_by IS DISTINCT FROM OLD.asked_by OR NEW.amount <> OLD.amount
       OR NEW.asked_at <> OLD.asked_at OR NEW.title <> OLD.title THEN
        RAISE EXCEPTION 'What was asked for is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status IN ('approved', 'overruled', 'lapsed') AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION 'A decision is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status = 'refused' AND NEW.status NOT IN ('refused', 'overruled') THEN
        RAISE EXCEPTION 'A refusal can only be overruled.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER empire_approvals_guarded BEFORE UPDATE OR DELETE ON empire_approvals FOR EACH ROW EXECUTE FUNCTION empire_approvals_guard();

CREATE TABLE empire_resolutions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL,
    title       text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    payload     jsonb NOT NULL DEFAULT '{}',
    proposed_by uuid REFERENCES players (id),                -- empty when the rules themselves call the vote
    period      integer NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'passed', 'failed', 'withdrawn')),
    opened_at   timestamptz NOT NULL,
    closes_at   timestamptz NOT NULL,
    decided_at  timestamptz,
    outcome     text
);
CREATE INDEX empire_resolutions_open ON empire_resolutions (empire_id) WHERE status = 'open';
CREATE UNIQUE INDEX empire_resolutions_one_open_of_a_kind ON empire_resolutions (empire_id, kind) WHERE status = 'open';

CREATE TABLE empire_resolution_votes (
    resolution_id bigint NOT NULL REFERENCES empire_resolutions (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    yes         boolean NOT NULL,
    at          timestamptz NOT NULL,
    PRIMARY KEY (resolution_id, player_id)
);

CREATE TABLE empire_articles (             -- the empire's own rules, as voted. The latest of each is in force.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    key         text NOT NULL,
    value       jsonb NOT NULL,
    resolution_id bigint REFERENCES empire_resolutions (id),
    period      integer NOT NULL,
    at          timestamptz NOT NULL
);
CREATE INDEX empire_articles_by_key ON empire_articles (empire_id, key, id DESC);
CREATE TRIGGER empire_articles_permanent BEFORE UPDATE OR DELETE ON empire_articles FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE desk_duties (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    build       text NOT NULL,                               -- the desk: a build, or 'head'
    period      integer NOT NULL,
    code        text NOT NULL,
    status      text NOT NULL DEFAULT 'due' CHECK (status IN ('due', 'done', 'missed')),
    score       integer CHECK (score BETWEEN 0 AND 100),
    assigned_to uuid REFERENCES players (id),
    done_by     uuid REFERENCES players (id),
    by_staff    boolean NOT NULL DEFAULT false,
    terms       jsonb,                                       -- what was put to whoever did it, fixed when it was first opened
    answers     jsonb,
    result      jsonb,
    done_at     timestamptz,
    UNIQUE (empire_id, build, period, code)
);

CREATE FUNCTION desk_duties_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status = 'due' AND OLD.terms IS NULL THEN
            RETURN OLD;                        -- a duty that never arose that quarter is not kept
        END IF;
        RAISE EXCEPTION 'A duty that has been done or missed is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status <> 'due' THEN
        RAISE EXCEPTION 'A duty that has been done or missed is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.terms IS NOT NULL AND NEW.terms IS DISTINCT FROM OLD.terms THEN
        RAISE EXCEPTION 'What a duty asks is fixed once it has been opened.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER desk_duties_guarded BEFORE UPDATE OR DELETE ON desk_duties FOR EACH ROW EXECUTE FUNCTION desk_duties_guard();

CREATE TABLE desk_scores (                 -- each desk's scorecard as each quarter closed. Permanent.
    empire_id   bigint NOT NULL REFERENCES empires (id),
    build       text NOT NULL,
    period      integer NOT NULL,
    duties      integer NOT NULL,          -- how many fell due
    done        integer NOT NULL,          -- done by players
    by_staff    integer NOT NULL,
    missed      integer NOT NULL,
    score       integer NOT NULL CHECK (score BETWEEN 0 AND 100),
    budget      bigint NOT NULL DEFAULT 0,
    spent       bigint NOT NULL DEFAULT 0,
    notes       jsonb NOT NULL DEFAULT '[]',
    PRIMARY KEY (empire_id, build, period)
);
CREATE TRIGGER desk_scores_permanent BEFORE UPDATE OR DELETE ON desk_scores FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_documents (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL,                               -- loan, bond, stake, insurance, contract ...
    title       text NOT NULL,
    ref         text,                                        -- what it belongs to, e.g. 'approval:12'
    clauses     jsonb NOT NULL,                              -- [{code, words, trap, plain}] : `trap` and `plain` never leave the server before review
    status      text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'signed', 'dropped')),
    struck      text[] NOT NULL DEFAULT '{}',                -- the clauses the reviewer had struck out
    kept_traps  text[] NOT NULL DEFAULT '{}',                -- the traps nobody struck: they are in force
    wrongly_struck text[] NOT NULL DEFAULT '{}',             -- fair clauses struck out: the other side charges for each
    reviewed_by uuid REFERENCES players (id),
    by_staff    boolean NOT NULL DEFAULT false,
    period      integer NOT NULL,
    at          timestamptz NOT NULL,
    reviewed_at timestamptz
);

CREATE TABLE signed_opinions (             -- what a member put their name to, and how it turned out. Permanent once settled.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id   uuid NOT NULL REFERENCES players (id),
    build       text NOT NULL,
    empire_id   bigint REFERENCES empires (id),
    kind        text NOT NULL,
    subject     text NOT NULL CHECK (length(subject) <= 200),
    call        jsonb NOT NULL DEFAULT '{}',
    period      integer NOT NULL,
    check_period integer,                                    -- the quarter whose close settles it
    outcome     text CHECK (outcome IN ('right', 'wrong', 'void')),
    outcome_words text,
    at          timestamptz NOT NULL,
    settled_at  timestamptz
);
CREATE INDEX signed_opinions_by_player ON signed_opinions (player_id, id DESC);
CREATE INDEX signed_opinions_unsettled ON signed_opinions (check_period) WHERE outcome IS NULL;

CREATE FUNCTION signed_opinions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.outcome IS NOT NULL THEN
        RAISE EXCEPTION 'A signed opinion is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.player_id <> OLD.player_id OR NEW.kind <> OLD.kind OR NEW.subject <> OLD.subject OR NEW.call <> OLD.call OR NEW.period <> OLD.period THEN
        RAISE EXCEPTION 'A signed opinion is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER signed_opinions_guarded BEFORE UPDATE OR DELETE ON signed_opinions FOR EACH ROW EXECUTE FUNCTION signed_opinions_guard();

CREATE TABLE ceo_records (                 -- what a head did. Permanent; it follows them from empire to empire.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id   uuid NOT NULL REFERENCES players (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL,                               -- overrule, strategy, confidence, season, letter ...
    words       text NOT NULL CHECK (length(words) <= 600),
    good        boolean,                                     -- how it turned out, when that is known
    reference   text,
    period      integer NOT NULL,
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX ceo_records_once ON ceo_records (reference) WHERE reference IS NOT NULL;
CREATE INDEX ceo_records_by_player ON ceo_records (player_id, id DESC);
CREATE TRIGGER ceo_records_no_delete BEFORE DELETE ON ceo_records FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_debts (                -- what an empire has borrowed
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL CHECK (kind IN ('loan', 'bond')),
    lender_account uuid REFERENCES ledger_accounts (id),     -- the bank, for a loan
    lender_name text NOT NULL,
    bond_code   text,                                        -- for a bond the empire issued
    principal   bigint NOT NULL CHECK (principal > 0),
    outstanding bigint NOT NULL CHECK (outstanding >= 0),
    rate_bps    integer NOT NULL CHECK (rate_bps BETWEEN 0 AND 10000),   -- a year
    taken_period integer NOT NULL,
    due_period  integer NOT NULL,
    document_id bigint REFERENCES empire_documents (id),
    traps       text[] NOT NULL DEFAULT '{}',                -- the clauses in force that nobody struck out
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'called', 'repaid', 'defaulted')),
    called_at   timestamptz,
    breach_since integer,                                    -- the quarter a covenant was first found broken
    at          timestamptz NOT NULL
);
CREATE INDEX empire_debts_open ON empire_debts (empire_id) WHERE status IN ('open', 'called');

CREATE TABLE empire_units (                -- who owns how much of an empire
    empire_id   bigint NOT NULL REFERENCES empires (id),
    holder_account uuid NOT NULL REFERENCES ledger_accounts (id),
    player_id   uuid REFERENCES players (id),
    units       bigint NOT NULL CHECK (units >= 0),
    PRIMARY KEY (empire_id, holder_account)
);

CREATE TABLE empire_stake_offers (          -- an empire sells a stake in itself: anybody may put money in, for units
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    wanted      bigint NOT NULL CHECK (wanted > 0),
    raised      bigint NOT NULL DEFAULT 0 CHECK (raised >= 0),
    unit_price  bigint NOT NULL CHECK (unit_price > 0),      -- kobo for each unit, fixed when the offer opened
    approval_id bigint REFERENCES empire_approvals (id),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    opened_at   timestamptz NOT NULL,
    closes_at   timestamptz NOT NULL
);

CREATE TABLE empire_payouts (              -- dividends paid to the partners. Permanent.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    period      integer NOT NULL,
    amount      bigint NOT NULL CHECK (amount > 0),
    units       bigint NOT NULL,
    resolution_id bigint REFERENCES empire_resolutions (id),
    at          timestamptz NOT NULL
);
CREATE TRIGGER empire_payouts_permanent BEFORE UPDATE OR DELETE ON empire_payouts FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_accounts (             -- the empire's own quarterly accounts, as closed. Permanent.
    empire_id   bigint NOT NULL REFERENCES empires (id),
    period      integer NOT NULL,
    figures     jsonb NOT NULL,
    PRIMARY KEY (empire_id, period)
);
CREATE TRIGGER empire_accounts_permanent BEFORE UPDATE OR DELETE ON empire_accounts FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_budgets (              -- what the head gave each desk to spend in a quarter
    empire_id   bigint NOT NULL REFERENCES empires (id),
    period      integer NOT NULL,
    desk        text NOT NULL,
    amount      bigint NOT NULL CHECK (amount >= 0),
    set_by      uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    PRIMARY KEY (empire_id, period, desk)
);

CREATE TABLE empire_happenings (           -- what the world throws at an empire, and how its desks answered
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL,
    title       text NOT NULL,
    body        text NOT NULL,
    desks       text[] NOT NULL,                             -- the desks that must answer
    payload     jsonb NOT NULL DEFAULT '{}',                 -- keys starting with _ never leave the server before it is settled
    period      integer NOT NULL,
    opened_at   timestamptz NOT NULL,
    due_at      timestamptz NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'settled')),
    score       integer CHECK (score BETWEEN 0 AND 100),
    cost        bigint NOT NULL DEFAULT 0,
    covered     bigint NOT NULL DEFAULT 0,
    outcome     text,
    settled_at  timestamptz,
    UNIQUE (empire_id, period, kind)
);
CREATE TABLE happening_answers (
    happening_id bigint NOT NULL REFERENCES empire_happenings (id),
    desk        text NOT NULL,
    player_id   uuid REFERENCES players (id),
    choice      text NOT NULL,
    score       integer,
    at          timestamptz NOT NULL,
    PRIMARY KEY (happening_id, desk)
);
CREATE TRIGGER happening_answers_permanent BEFORE UPDATE OR DELETE ON happening_answers FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_cover (                -- insurance the empire has bought against what may happen to it
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL,
    insurer_id  uuid NOT NULL REFERENCES companies (id),
    premium     bigint NOT NULL CHECK (premium > 0),
    cover       bigint NOT NULL CHECK (cover > 0),
    from_period integer NOT NULL,
    to_period   integer NOT NULL,
    claimed     bigint NOT NULL DEFAULT 0,
    bought_by   uuid REFERENCES players (id),
    at          timestamptz NOT NULL
);

CREATE TABLE member_contracts (            -- what a member agreed to on joining: notice, bonus terms, a non-compete
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    notice_days integer NOT NULL CHECK (notice_days BETWEEN 0 AND 14),
    bonus_bps   integer NOT NULL CHECK (bonus_bps BETWEEN 0 AND 2000),   -- a share of the desk's bonus pool promised to them
    non_compete integer NOT NULL CHECK (non_compete BETWEEN 0 AND 2),   -- quarters they may not join the empire's rival after leaving
    status      text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'signed', 'refused', 'ended')),
    offered_by  uuid REFERENCES players (id),
    drafted_by  uuid REFERENCES players (id),                -- the Lawyer who drafted it
    offered_at  timestamptz NOT NULL,
    signed_at   timestamptz,
    ended_at    timestamptz,
    bars_until  integer,                                     -- the last quarter the non-compete binds, once ended
    bars_empire bigint REFERENCES empires (id)
);
CREATE UNIQUE INDEX member_contracts_one_live ON member_contracts (empire_id, player_id) WHERE status IN ('offered', 'signed');

CREATE TABLE empire_apprentices (
    empire_id   bigint NOT NULL REFERENCES empires (id),
    mentor_id   uuid NOT NULL REFERENCES players (id),
    apprentice_id uuid NOT NULL REFERENCES players (id),
    build       text NOT NULL,
    since_period integer NOT NULL,
    at          timestamptz NOT NULL,
    ended_at    timestamptz
);
CREATE UNIQUE INDEX empire_apprentices_one_mentor ON empire_apprentices (apprentice_id) WHERE ended_at IS NULL;

CREATE TABLE poach_offers (                -- one empire's head asks another's member to come over
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_empire bigint NOT NULL REFERENCES empires (id),
    to_empire   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    build       text NOT NULL,
    bonus       bigint NOT NULL CHECK (bonus > 0),            -- paid by the empire that wins them, on the day they move
    words       text CHECK (length(words) <= 400),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'matched', 'accepted', 'declined', 'lapsed', 'withdrawn')),
    matched     bigint,                                      -- what the home empire offered to keep them
    at          timestamptz NOT NULL,
    match_by    timestamptz NOT NULL,
    decided_at  timestamptz
);
CREATE UNIQUE INDEX poach_offers_one_open ON poach_offers (from_empire, player_id) WHERE status IN ('open', 'matched');

CREATE TABLE client_engagements (          -- a player hires a bookkeeper; the fee goes to the bookkeeper's empire desk
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id   uuid NOT NULL REFERENCES players (id),
    adviser_id  uuid NOT NULL REFERENCES players (id),
    empire_id   bigint REFERENCES empires (id),
    fee         bigint NOT NULL CHECK (fee > 0),
    period      integer NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'lapsed', 'cancelled')),
    report      jsonb,
    rating      smallint CHECK (rating BETWEEN 1 AND 5),
    at          timestamptz NOT NULL,
    done_at     timestamptz
);
CREATE UNIQUE INDEX client_engagements_one_a_quarter ON client_engagements (client_id, period) WHERE status <> 'cancelled';

CREATE TABLE board_plans (                 -- what the head set at the board meeting for the coming quarter
    empire_id   bigint NOT NULL REFERENCES empires (id),
    period      integer NOT NULL,
    plan        jsonb NOT NULL,
    set_by      uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    PRIMARY KEY (empire_id, period)
);

CREATE TABLE empire_strategies (           -- the year's direction and targets, and how it turned out
    empire_id   bigint NOT NULL REFERENCES empires (id),
    season      integer NOT NULL,
    choice      text NOT NULL CHECK (choice IN ('grow', 'income', 'takeovers', 'safe')),
    targets     jsonb NOT NULL,
    set_by      uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    result      jsonb,
    PRIMARY KEY (empire_id, season)
);

CREATE TABLE empire_risk_reports (         -- what the Risk Manager's desk wrote at each Closing Bell. Permanent.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    day         date NOT NULL,
    figures     jsonb NOT NULL,
    UNIQUE (empire_id, day)
);
CREATE TRIGGER empire_risk_reports_permanent BEFORE UPDATE OR DELETE ON empire_risk_reports FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Tasks: up to three in hand at once, and one of each kind started in a quarter.
DROP INDEX empire_tasks_one_open;
DROP INDEX empire_tasks_one_a_quarter;
ALTER TABLE empire_tasks DROP CONSTRAINT empire_tasks_kind_check;
ALTER TABLE empire_tasks ADD CONSTRAINT empire_tasks_kind_check CHECK (kind IN ('investment', 'raise_money', 'rescue', 'defend'));
CREATE UNIQUE INDEX empire_tasks_one_of_a_kind_a_quarter ON empire_tasks (empire_id, kind, period);
ALTER TABLE empire_tasks ADD COLUMN priority smallint NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3);
ALTER TABLE empire_tasks ADD COLUMN decision jsonb NOT NULL DEFAULT '{}';      -- the head's call in a defence
ALTER TABLE empire_task_steps ADD COLUMN assigned_to uuid REFERENCES players (id);

ALTER TABLE career_events DROP CONSTRAINT career_events_kind_check;
ALTER TABLE career_events ADD CONSTRAINT career_events_kind_check CHECK (kind IN (
    'build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up', 'review_opened', 'review_closed', 'demoted', 'fund_chosen',
    'saving_changed', 'retired', 'early_withdrawal', 'joined_empire', 'left_empire', 'sacked', 'theft_proved', 'founded_empire',
    'fund_opened', 'struck_off', 'rank_case', 'rank_passed', 'ceo', 'resigned', 'counter_offer',
    'promoted', 'poached', 'apprentice', 'contract', 'opinion'));
