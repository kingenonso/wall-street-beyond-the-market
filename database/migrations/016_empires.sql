-- Stage 6: all builds, and empires.

-- ---------------------------------------------------------------------------
-- The other four builds a player may choose. (CEO is earned, never chosen.)
-- ---------------------------------------------------------------------------
ALTER TABLE players DROP CONSTRAINT players_build_check;
ALTER TABLE players ADD CONSTRAINT players_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
ALTER TABLE careers DROP CONSTRAINT careers_build_check;
ALTER TABLE careers ADD CONSTRAINT careers_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
ALTER TABLE employments DROP CONSTRAINT employments_build_check;
ALTER TABLE employments ADD CONSTRAINT employments_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
ALTER TABLE objectives DROP CONSTRAINT objectives_build_check;
ALTER TABLE objectives ADD CONSTRAINT objectives_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));

-- ---------------------------------------------------------------------------
-- Retirement savings: every fund has a bad side; saving extra is rewarded; retirement has a date.
-- ---------------------------------------------------------------------------
ALTER TABLE retirement_accounts ADD COLUMN extra_bps integer NOT NULL DEFAULT 0 CHECK (extra_bps BETWEEN 0 AND 2000);
ALTER TABLE retirement_accounts ADD COLUMN retired_period integer;            -- the quarter the pension began
ALTER TABLE retirement_accounts ADD COLUMN early_withdrawn_period integer;    -- the one early withdrawal, if taken
ALTER TABLE retirement_entries ADD COLUMN paid_out bigint NOT NULL DEFAULT 0 CHECK (paid_out >= 0);   -- pension paid in the quarter

-- What made up each fund's quarter: its shares, its bonds, its cash, and what it lost on companies that defaulted.
ALTER TABLE pension_fund_results ADD COLUMN shares_part_bps integer NOT NULL DEFAULT 0;
ALTER TABLE pension_fund_results ADD COLUMN bonds_part_bps integer NOT NULL DEFAULT 0;
ALTER TABLE pension_fund_results ADD COLUMN credit_loss_bps integer NOT NULL DEFAULT 0;
ALTER TABLE pension_fund_results ADD COLUMN prices_bps integer NOT NULL DEFAULT 0;      -- how much prices rose in the quarter

ALTER TABLE payslips ADD COLUMN extra_saving bigint NOT NULL DEFAULT 0 CHECK (extra_saving >= 0);      -- part of pension_yours
ALTER TABLE payslips ADD COLUMN employer_match bigint NOT NULL DEFAULT 0 CHECK (employer_match >= 0);  -- part of pension_employer

ALTER TABLE career_events DROP CONSTRAINT career_events_kind_check;
ALTER TABLE career_events ADD CONSTRAINT career_events_kind_check CHECK (kind IN (
    'build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up', 'review_opened', 'review_closed', 'demoted', 'fund_chosen',
    'saving_changed', 'retired', 'early_withdrawal', 'joined_empire', 'left_empire', 'sacked', 'theft_proved', 'founded_empire'));

-- ---------------------------------------------------------------------------
-- Empires. An empire has its own account in the ledger, thirteen seats, and a head.
-- ---------------------------------------------------------------------------
ALTER TABLE ledger_accounts DROP CONSTRAINT ledger_accounts_kind_check;
ALTER TABLE ledger_accounts ADD CONSTRAINT ledger_accounts_kind_check CHECK (kind IN (
    'central_bank', 'government', 'prize_pool', 'npc_public', 'npc_investors', 'company', 'player', 'exchange', 'empire', 'fund'));

CREATE TABLE empires (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text NOT NULL CHECK (length(name) BETWEEN 3 AND 40),
    kind            text NOT NULL CHECK (kind IN ('player', 'computer')),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('forming', 'active', 'closed')),
    account_id      uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),
    head_player_id  uuid REFERENCES players (id),          -- empty for an empire run by the computer
    trust           integer NOT NULL DEFAULT 50 CHECK (trust BETWEEN 0 AND 100),
    expense_limit   bigint NOT NULL DEFAULT 0 CHECK (expense_limit >= 0),   -- what a member may spend in a quarter, unless set for them
    trade_limit_bps integer NOT NULL DEFAULT 2000 CHECK (trade_limit_bps BETWEEN 0 AND 10000),
    founded_period  integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX empires_name_unique ON empires (lower(name));

-- The seats: two for each of the six builds. The head's place is on the empire itself.
-- A seat is held by a player, by computer-run staff (staffed), or by nobody.
CREATE TABLE empire_seats (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    build         text NOT NULL CHECK (build IN ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist')),
    slot          smallint NOT NULL CHECK (slot IN (1, 2)),
    player_id     uuid REFERENCES players (id),
    staffed       boolean NOT NULL DEFAULT false,          -- computer-run staff do this seat's work while no player holds it
    since         timestamptz,
    signing_limit bigint CHECK (signing_limit >= 0),       -- set by the head for whoever holds the seat; empty = the empire's usual
    UNIQUE (empire_id, build, slot)
);
CREATE UNIQUE INDEX empire_seats_one_seat_each ON empire_seats (player_id) WHERE player_id IS NOT NULL;

CREATE TABLE empire_members (              -- who was in which empire, and how it ended. Never changed once ended.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    build       text NOT NULL,
    joined_at   timestamptz NOT NULL,
    joined_period integer NOT NULL,
    left_at     timestamptz,
    left_period integer,
    left_reason text
);
CREATE UNIQUE INDEX empire_members_one_open ON empire_members (player_id) WHERE left_at IS NULL;
CREATE TRIGGER empire_members_no_delete BEFORE DELETE ON empire_members FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_applications (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    build       text NOT NULL,
    status      text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'accepted', 'refused', 'withdrawn')),
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX empire_applications_one_waiting ON empire_applications (player_id) WHERE status = 'waiting';

CREATE TABLE empire_capital (              -- money members have put into an empire. Permanent.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    amount      bigint NOT NULL,           -- a refund is a minus figure
    at          timestamptz NOT NULL
);
CREATE TRIGGER empire_capital_permanent BEFORE UPDATE OR DELETE ON empire_capital FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The empire's books: every payment out of the empire that is not a trade. Members see the
-- category, the description and the amount. Who entered it, and whether it is what it says,
-- is known only to the server: that is what an audit finds.
CREATE TABLE empire_books (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    period      integer NOT NULL,
    category    text NOT NULL,
    description text NOT NULL,
    amount      bigint NOT NULL CHECK (amount > 0),
    genuine     boolean NOT NULL,
    entered_by  uuid REFERENCES players (id),
    thief_level integer,                   -- the level of whoever disguised it, when it is not genuine
    found       boolean NOT NULL DEFAULT false,
    at          timestamptz NOT NULL
);
CREATE INDEX empire_books_by_empire ON empire_books (empire_id, period);
CREATE TRIGGER empire_books_no_delete BEFORE DELETE ON empire_books FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_audits (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL CHECK (kind IN ('accountant', 'staff', 'ai', 'report')),
    auditor_id  uuid REFERENCES players (id),
    hired_by    uuid REFERENCES players (id),
    period      integer NOT NULL,
    from_period integer NOT NULL,
    to_period   integer NOT NULL,
    fee         bigint NOT NULL DEFAULT 0,
    examined    integer NOT NULL DEFAULT 0,
    findings    bigint[] NOT NULL DEFAULT '{}',     -- entries the audit found to be false (seen by the auditor)
    reported    bigint[],                           -- of those, the ones the auditor put in the report
    status      text NOT NULL DEFAULT 'filed' CHECK (status IN ('open', 'filed')),
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX empire_audits_one_ai_a_season ON empire_audits (empire_id, period) WHERE kind = 'ai';
CREATE UNIQUE INDEX empire_audits_one_each_quarter ON empire_audits (empire_id, auditor_id, period) WHERE kind = 'accountant';

CREATE TABLE empire_cases (                -- a theft that an audit has proved
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    book_id     bigint NOT NULL UNIQUE REFERENCES empire_books (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    amount      bigint NOT NULL,
    audit_id    bigint NOT NULL REFERENCES empire_audits (id),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'punished', 'forgiven')),
    repaid      bigint NOT NULL DEFAULT 0,
    fine        bigint NOT NULL DEFAULT 0,
    debt_left   bigint NOT NULL DEFAULT 0 CHECK (debt_left >= 0),
    reward_to   uuid REFERENCES players (id),       -- whoever reported it
    reward_paid bigint NOT NULL DEFAULT 0,
    decided_at  timestamptz,
    at          timestamptz NOT NULL
);

-- A player's legal record. The courts (a later stage) add to it; a proved theft is the first kind of entry.
CREATE TABLE legal_records (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id   uuid NOT NULL REFERENCES players (id),
    kind        text NOT NULL,
    words       text NOT NULL,
    at          timestamptz NOT NULL
);
CREATE TRIGGER legal_records_permanent BEFORE UPDATE OR DELETE ON legal_records FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE empire_trades (               -- what each member has traded for the empire, against their limit
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    period      integer NOT NULL,
    what        text NOT NULL,
    value       bigint NOT NULL,
    at          timestamptz NOT NULL
);

-- Work that needs several builds. Each step is handed from one build to the next.
CREATE TABLE empire_tasks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL CHECK (kind IN ('investment')),
    company_id  uuid REFERENCES companies (id),
    period      integer NOT NULL,
    amount      bigint NOT NULL DEFAULT 0,
    shares_before bigint,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'failed')),
    started_by  uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    done_at     timestamptz
);
CREATE UNIQUE INDEX empire_tasks_one_open ON empire_tasks (empire_id) WHERE status = 'open';

CREATE TABLE empire_task_steps (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id     bigint NOT NULL REFERENCES empire_tasks (id),
    position    integer NOT NULL,
    build       text NOT NULL,                         -- 'head' for the head's approval
    what        text NOT NULL,
    hands_on    text NOT NULL,                         -- what is handed to the next build
    template    text,
    status      text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'current', 'done')),
    objective_id bigint REFERENCES objectives (id),
    done_by     uuid REFERENCES players (id),
    done_by_staff boolean NOT NULL DEFAULT false,
    ticks       integer NOT NULL DEFAULT 0,            -- how many times the staff have looked at it while it waited for a player
    ready_at    timestamptz,
    done_at     timestamptz,
    UNIQUE (task_id, position)
);

CREATE TABLE empire_pacts (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        text NOT NULL,
    legal       boolean NOT NULL,
    from_empire bigint NOT NULL REFERENCES empires (id),
    to_empire   bigint NOT NULL REFERENCES empires (id),
    drafted_by  uuid REFERENCES players (id),
    terms       text NOT NULL CHECK (length(terms) <= 400),
    status      text NOT NULL DEFAULT 'drafted' CHECK (status IN ('drafted', 'proposed', 'signed', 'refused', 'broken', 'ended')),
    period      integer NOT NULL,
    signed_period integer,
    broken_by   bigint REFERENCES empires (id),
    reported_by bigint REFERENCES empires (id),
    exposed_at  timestamptz,
    exposed_by  uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    CHECK (from_empire <> to_empire)
);

CREATE TABLE empire_investigations (       -- a journalist looking into an empire: once a quarter each
    journalist_id uuid NOT NULL REFERENCES players (id),
    period      integer NOT NULL,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    found_pact  bigint REFERENCES empire_pacts (id),
    at          timestamptz NOT NULL,
    PRIMARY KEY (journalist_id, period)
);

CREATE TABLE empire_messages (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    body        text NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
    at          timestamptz NOT NULL
);
CREATE INDEX empire_messages_by_empire ON empire_messages (empire_id, id DESC);

CREATE TABLE empire_events (               -- the decision log. Permanent.
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    words       text NOT NULL,
    at          timestamptz NOT NULL
);
CREATE TRIGGER empire_events_permanent BEFORE UPDATE OR DELETE ON empire_events FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- A step in an empire's task is a piece of work in its own right: it does not use up the one
-- piece of each kind a player may take in a quarter. Each player may try a given step once.
ALTER TABLE objectives DROP CONSTRAINT objectives_player_id_build_template_period_key;
CREATE UNIQUE INDEX objectives_once_a_quarter ON objectives (player_id, build, template, period) WHERE NOT (terms ? 'step_id');
CREATE UNIQUE INDEX objectives_step_once ON objectives (player_id, ((terms ->> 'step_id'))) WHERE terms ? 'step_id';
CREATE UNIQUE INDEX empire_tasks_one_a_quarter ON empire_tasks (empire_id, period);

-- ---------------------------------------------------------------------------
-- Pension funds run by players. A fund keeps its books, and is audited, exactly as an empire is,
-- so it is held as a row of the same table: its "head" is its manager, and it has no seats.
-- ---------------------------------------------------------------------------
ALTER TABLE empires DROP CONSTRAINT empires_kind_check;
ALTER TABLE empires ADD CONSTRAINT empires_kind_check CHECK (kind IN ('player', 'computer', 'pension'));
ALTER TABLE empires ADD COLUMN fee_bps integer NOT NULL DEFAULT 0 CHECK (fee_bps BETWEEN 0 AND 50);   -- a pension fund's fee each quarter
ALTER TABLE empires ADD COLUMN units bigint NOT NULL DEFAULT 0 CHECK (units >= 0);                   -- a pension fund's units in issue
ALTER TABLE empires ADD COLUMN struck_off boolean NOT NULL DEFAULT false;                            -- its manager was removed by the regulator
ALTER TABLE empires ADD COLUMN manager_id uuid REFERENCES players (id);                              -- whoever opened a pension fund, for good
CREATE UNIQUE INDEX empires_one_fund_each ON empires (manager_id) WHERE kind = 'pension';

ALTER TABLE retirement_accounts ADD COLUMN managed_fund_id bigint REFERENCES empires (id);
ALTER TABLE retirement_accounts ADD COLUMN units bigint NOT NULL DEFAULT 0 CHECK (units >= 0);
ALTER TABLE retirement_accounts ADD COLUMN leaving boolean NOT NULL DEFAULT false;     -- has asked for the savings back; paid as the fund has cash

CREATE TABLE fund_prices (                 -- what a unit of each player-run fund was worth as each quarter closed. Permanent.
    fund_id     bigint NOT NULL REFERENCES empires (id),
    period      integer NOT NULL,
    unit_price  bigint NOT NULL,           -- in millionths of a kobo, so that small funds are priced exactly
    worth       bigint NOT NULL,
    units       bigint NOT NULL,
    savers      integer NOT NULL,
    PRIMARY KEY (fund_id, period)
);
CREATE TRIGGER fund_prices_permanent BEFORE UPDATE OR DELETE ON fund_prices FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

ALTER TABLE career_events DROP CONSTRAINT career_events_kind_check;
ALTER TABLE career_events ADD CONSTRAINT career_events_kind_check CHECK (kind IN (
    'build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up', 'review_opened', 'review_closed', 'demoted', 'fund_chosen',
    'saving_changed', 'retired', 'early_withdrawal', 'joined_empire', 'left_empire', 'sacked', 'theft_proved', 'founded_empire',
    'fund_opened', 'struck_off'));
