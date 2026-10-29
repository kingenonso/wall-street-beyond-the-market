-- Run Your Own Fund (the talent and funds stage, Part 2): open investment funds that anybody may put money into.
--
-- A fund is a ledger account holding cash, shares and bonds, and a register of units. A unit is worth the fund's value
-- divided by the units in issue. Money comes in and goes out only at the next closing bell's price ("forward pricing"),
-- so nobody can buy into a price they have already seen. Every naira still moves through the ledger: money waiting to
-- buy units is held in the fund dealing account until the bell.

CREATE TABLE investment_funds (
    id                 bigserial PRIMARY KEY,
    name               text NOT NULL CHECK (length(name) BETWEEN 3 AND 60),
    name_key           text NOT NULL UNIQUE,
    account_id         uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),
    founder_id         uuid REFERENCES players (id),
    manager_id         uuid REFERENCES players (id),             -- NULL when the regulator (or the computer) runs it
    computer           boolean NOT NULL DEFAULT false,
    regulator_run      boolean NOT NULL DEFAULT false,
    strategy           text NOT NULL CHECK (strategy IN ('shares', 'banks', 'bonds', 'balanced', 'anything')),
    fee_bps            integer NOT NULL CHECK (fee_bps BETWEEN 0 AND 200),             -- a year, of the fund
    perf_fee_bps       integer NOT NULL DEFAULT 0 CHECK (perf_fee_bps BETWEEN 0 AND 2000), -- of gains above the high-water mark
    high_water         bigint NOT NULL,                                                -- unit price, millionths of a kobo
    least_in           bigint NOT NULL CHECK (least_in > 0),
    status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closing', 'closed', 'merged')),
    gated_at           timestamptz,                                                    -- leavers are paid only in part
    gate_lifted_at     timestamptz,                                                    -- a gate cannot go straight back up
    gate_bps           integer NOT NULL DEFAULT 1000,
    units              bigint NOT NULL DEFAULT 0 CHECK (units >= 0),
    launched_at        timestamptz NOT NULL,
    launched_period    integer NOT NULL,
    closing_since      timestamptz,
    closed_at          timestamptz,
    merged_into        bigint REFERENCES investment_funds (id),
    small_quarters     integer NOT NULL DEFAULT 0,
    run_until          date,                                                           -- a run by its investors is on
    words              text NOT NULL DEFAULT '' CHECK (length(words) <= 400)
);
CREATE INDEX investment_funds_manager ON investment_funds (manager_id);

CREATE TABLE fund_units (
    fund_id     bigint NOT NULL REFERENCES investment_funds (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    units       bigint NOT NULL DEFAULT 0 CHECK (units >= 0),
    leaving     bigint NOT NULL DEFAULT 0 CHECK (leaving >= 0 AND leaving <= units),    -- units asked back, not yet paid
    since       timestamptz NOT NULL,
    PRIMARY KEY (fund_id, account_id)
);

-- Money in and money out, each dealt at the next closing bell.
CREATE TABLE fund_orders (
    id          bigserial PRIMARY KEY,
    fund_id     bigint NOT NULL REFERENCES investment_funds (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    player_id   uuid REFERENCES players (id),                       -- who placed it (an empire's head, for an empire)
    side        text NOT NULL CHECK (side IN ('in', 'out')),
    amount      bigint NOT NULL DEFAULT 0 CHECK (amount >= 0),      -- in: the cash held for it
    units       bigint NOT NULL DEFAULT 0 CHECK (units >= 0),       -- out: the units asked back
    placed_at   timestamptz NOT NULL,
    status      text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'dealt', 'cancelled', 'refused')),
    dealt_at    timestamptz,
    session_date date,
    price       bigint,
    units_done  bigint NOT NULL DEFAULT 0,
    paid        bigint NOT NULL DEFAULT 0,
    words       text
);
CREATE INDEX fund_orders_waiting ON fund_orders (fund_id, status) WHERE status = 'waiting';

-- Each closing bell's price, for good.
CREATE TABLE fund_days (
    fund_id       bigint NOT NULL REFERENCES investment_funds (id),
    session_date  date NOT NULL,
    unit_price    bigint NOT NULL,
    worth         bigint NOT NULL,
    units         bigint NOT NULL,
    money_in      bigint NOT NULL DEFAULT 0,
    money_out     bigint NOT NULL DEFAULT 0,
    fee           bigint NOT NULL DEFAULT 0,
    benchmark     bigint,                                           -- the benchmark's level that day (a hundred-thousandth)
    PRIMARY KEY (fund_id, session_date)
);
CREATE TRIGGER fund_days_permanent BEFORE UPDATE OR DELETE ON fund_days FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Each quarter: the star rating and the figures behind it, for good.
CREATE TABLE fund_quarters (
    fund_id      bigint NOT NULL REFERENCES investment_funds (id),
    period       integer NOT NULL,
    unit_price   bigint NOT NULL,
    worth        bigint NOT NULL,
    holders      integer NOT NULL,
    stars        smallint CHECK (stars BETWEEN 1 AND 5),
    quarter_bps  integer,
    year_bps     integer,
    bench_bps    integer,
    risk_ratio   numeric(8, 2),
    perf_fee     bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (fund_id, period)
);
CREATE TRIGGER fund_quarters_permanent BEFORE UPDATE OR DELETE ON fund_quarters FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- What a fund held at a quarter's end. Published one quarter later.
CREATE TABLE fund_disclosures (
    fund_id   bigint NOT NULL REFERENCES investment_funds (id),
    period    integer NOT NULL,
    holdings  jsonb NOT NULL,
    PRIMARY KEY (fund_id, period)
);

CREATE TABLE fund_follows (
    player_id  uuid NOT NULL REFERENCES players (id),
    fund_id    bigint NOT NULL REFERENCES investment_funds (id),
    at         timestamptz NOT NULL,
    PRIMARY KEY (player_id, fund_id)
);

-- Pop-ups for the fund's holders and followers (and, for the big ones, everybody).
CREATE TABLE fund_alerts (
    id        bigserial PRIMARY KEY,
    fund_id   bigint NOT NULL REFERENCES investment_funds (id),
    kind      text NOT NULL CHECK (kind IN ('stars', 'holdings', 'gated', 'gate_lifted', 'run', 'closing', 'closed', 'merged',
                                            'struck_off', 'launched')),
    everyone  boolean NOT NULL DEFAULT false,
    headline  text NOT NULL,
    words     text NOT NULL,
    at        timestamptz NOT NULL
);

-- A short loan to pay investors who leave, at most a tenth of the fund, repaid as cash allows.
CREATE TABLE fund_loans (
    id          bigserial PRIMARY KEY,
    fund_id     bigint NOT NULL REFERENCES investment_funds (id),
    owed        bigint NOT NULL CHECK (owed >= 0),
    rate_bps    integer NOT NULL,
    taken_at    timestamptz NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaid'))
);

-- The fund's costs as written in its books. A manager can write a false cost and take the money: the regulator's audit
-- may find it. Never shown to anybody but the regulator's findings.
CREATE TABLE fund_books (
    id          bigserial PRIMARY KEY,
    fund_id     bigint NOT NULL REFERENCES investment_funds (id),
    period      integer NOT NULL,
    words       text NOT NULL,
    amount      bigint NOT NULL CHECK (amount > 0),
    genuine     boolean NOT NULL,
    entered_by  uuid REFERENCES players (id),
    found       boolean NOT NULL DEFAULT false,
    at          timestamptz NOT NULL
);

CREATE TABLE fund_merges (
    id           bigserial PRIMARY KEY,
    from_fund    bigint NOT NULL REFERENCES investment_funds (id),
    into_fund    bigint NOT NULL REFERENCES investment_funds (id),
    proposed_at  timestamptz NOT NULL,
    accepted_at  timestamptz,
    takes_effect timestamptz,
    status       text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'agreed', 'done', 'refused', 'withdrawn'))
);
CREATE UNIQUE INDEX fund_merges_one ON fund_merges (from_fund) WHERE status IN ('proposed', 'agreed');

CREATE TABLE fund_progress (
    id               boolean PRIMARY KEY DEFAULT true CHECK (id),
    dealt_through    date
);
INSERT INTO fund_progress (id) VALUES (true);

-- Proven Talent shows the funds a player has run, as its own section.
ALTER TABLE talent_settings ALTER COLUMN show SET DEFAULT ARRAY['investing', 'work', 'calls', 'audits', 'journalism', 'leadership', 'funds',
                                                                  'crisis', 'challenges'];
