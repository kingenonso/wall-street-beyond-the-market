-- Index funds and ETFs (the talent and funds stage, Part 3).
--
-- A family of indexes run by the game's index provider (and custom indexes published by fund managers); funds that copy
-- an index; ETFs, whose units trade on the exchange all day like a share and are made and unmade by approved dealers;
-- passive money; and futures and options on the main indexes. Every naira and every unit still moves through the ledger.

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE TABLE market_indexes (
    code          text PRIMARY KEY CHECK (code ~ '^[A-Z0-9]{2,10}$'),
    name          text NOT NULL,
    kind          text NOT NULL CHECK (kind IN ('shares', 'bonds')),
    rule          text NOT NULL,                     -- which companies or bonds it takes: top30, sector:banking, dividend, govbond, corpbond, custom
    rules_words   text NOT NULL,                     -- the published rules, in plain words
    cap_bps       integer NOT NULL DEFAULT 1500,
    owner_id      uuid REFERENCES players (id),      -- a manager's custom index; NULL for the game's own
    weighting     text NOT NULL DEFAULT 'value' CHECK (weighting IN ('value', 'equal')),
    level         bigint,                            -- at the last closing bell, hundredths of a point (1,000.00 at the start)
    level_day     date,
    div_period    integer,                           -- the last quarter whose dividends the level has counted (share indexes)
    started_day   date,
    created_at    timestamptz NOT NULL,
    status        text NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'retired'))
);

-- Who is in an index, and how many "index shares" of each it counts. Changed only at a review or an announced change.
CREATE TABLE index_members (
    index_code    text NOT NULL REFERENCES market_indexes (code),
    asset         text NOT NULL REFERENCES assets (code),
    ticker        text NOT NULL,                     -- a company's code, or a bond's
    quantity      numeric(30, 6) NOT NULL CHECK (quantity > 0),
    weight_bps    integer NOT NULL,                  -- at the review that set it
    last_price    bigint NOT NULL,                   -- at the last closing bell
    since_day     date NOT NULL,
    PRIMARY KEY (index_code, asset)
);

-- Changes decided at a review (or by a custom index's owner), announced ahead and made at a later closing bell.
CREATE TABLE index_changes (
    id            bigserial PRIMARY KEY,
    index_code    text NOT NULL REFERENCES market_indexes (code),
    period        integer NOT NULL,                  -- the review's quarter
    announced_at  timestamptz NOT NULL,
    effective_day date NOT NULL,                     -- made at that day's closing bell
    adds          jsonb NOT NULL,                    -- [{ticker, name}]
    drops         jsonb NOT NULL,
    plan          jsonb NOT NULL,                    -- the new membership: [{asset, ticker, weight_bps}]
    status        text NOT NULL DEFAULT 'announced' CHECK (status IN ('announced', 'made')),
    orders_placed boolean NOT NULL DEFAULT false
);
CREATE INDEX index_changes_waiting ON index_changes (status, effective_day);

-- Each index at each closing bell, for good.
CREATE TABLE index_levels (
    index_code    text NOT NULL REFERENCES market_indexes (code),
    session_date  date NOT NULL,
    level         bigint NOT NULL CHECK (level > 0),
    PRIMARY KEY (index_code, session_date)
);
CREATE TRIGGER index_levels_permanent BEFORE UPDATE OR DELETE ON index_levels FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Index funds: open funds of Part 2 that copy an index (the game deals for them)
-- ---------------------------------------------------------------------------

ALTER TABLE investment_funds DROP CONSTRAINT investment_funds_strategy_check;
ALTER TABLE investment_funds ADD CONSTRAINT investment_funds_strategy_check
    CHECK (strategy IN ('shares', 'banks', 'bonds', 'balanced', 'anything', 'index'));
ALTER TABLE investment_funds ADD COLUMN index_code text REFERENCES market_indexes (code);
ALTER TABLE investment_funds ADD COLUMN method text NOT NULL DEFAULT 'full' CHECK (method IN ('full', 'sample'));
ALTER TABLE investment_funds ADD CONSTRAINT investment_funds_index_needs_code CHECK (strategy <> 'index' OR index_code IS NOT NULL);

-- ---------------------------------------------------------------------------
-- ETFs
-- ---------------------------------------------------------------------------

ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_code_check;
ALTER TABLE assets ADD CONSTRAINT assets_code_check
    CHECK (code ~ '^([A-Z]{3}|SHR-[A-Z]{3}|BND-[A-Z0-9]{3,12}|PRF-[A-Z]{3}|WRT-[A-Z]{3}[0-9]{1,4}|DEP-[A-Z]{3}|ETF-[A-Z]{3,5})$');
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_unit_check;
ALTER TABLE assets ADD CONSTRAINT assets_unit_check CHECK (unit IN ('kobo', 'share', 'bond', 'preferred', 'warrant', 'unit'));
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_kind_check;
ALTER TABLE assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('currency', 'share', 'bond', 'preferred', 'warrant', 'deposit', 'etf'));

CREATE OR REPLACE FUNCTION ledger_apply_entry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    opened_in    bigint;
    reason       text;
    new_balance  bigint;
    issuer       uuid;
    asset_kind   text;
BEGIN
    SELECT created_txid, kind INTO opened_in, reason FROM ledger_transactions WHERE id = NEW.transaction_id;
    IF opened_in IS DISTINCT FROM txid_current() THEN
        RAISE EXCEPTION 'That ledger transaction is closed. Nothing can be added to it.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_transaction_closed';
    END IF;

    INSERT INTO ledger_balances (account_id, asset, balance)
    VALUES (NEW.account_id, NEW.asset, NEW.amount)
    ON CONFLICT (account_id, asset)
        DO UPDATE SET balance = ledger_balances.balance + EXCLUDED.balance
    RETURNING balance INTO new_balance;

    IF new_balance < 0 THEN
        SELECT issuer_account_id INTO issuer FROM assets WHERE code = NEW.asset;
        IF issuer IS DISTINCT FROM NEW.account_id THEN
            RAISE EXCEPTION 'Not enough % in the account to make this payment.', NEW.asset
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ledger_insufficient_balance';
        END IF;
        SELECT kind INTO asset_kind FROM assets WHERE code = NEW.asset;
        IF NEW.amount < 0 AND NOT (
               (reason = 'opening_balance' AND NOT EXISTS (SELECT 1 FROM world_state WHERE last_closed_period >= 1))
            OR (reason IN ('share_issue', 'share_split') AND asset_kind = 'share')
            OR (reason = 'bond_issue' AND asset_kind = 'bond')
            OR (reason = 'preferred_issue' AND asset_kind = 'preferred')
            OR (reason = 'warrant_issue' AND asset_kind = 'warrant')
            OR (reason = 'central_bank_lending' AND asset_kind = 'currency')
            OR (reason = 'deposit_record' AND asset_kind = 'deposit'
                AND NOT EXISTS (SELECT 1 FROM ledger_entries e WHERE e.asset = NEW.asset AND e.transaction_id <> NEW.transaction_id))
            OR (reason IN ('savings_placed', 'deposit_placed', 'company_savings') AND asset_kind = 'deposit')
            -- ETF units come into existence only when an approved dealer makes them, against a basket or cash (Part 3).
            OR (reason = 'etf_create' AND asset_kind = 'etf')
        ) THEN
            RAISE EXCEPTION 'New % cannot be brought into existence for the reason "%".', NEW.asset, reason
                USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_issuance_reason';
        END IF;
    END IF;

    IF NEW.amount > 0 AND reason <> 'debt_repayment' THEN
        SELECT issuer_account_id, kind INTO issuer, asset_kind FROM assets WHERE code = NEW.asset;
        IF issuer = NEW.account_id AND asset_kind = 'currency' THEN
            RAISE EXCEPTION '% cannot be taken out of existence for the reason "%".', NEW.asset, reason
                USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_destruction_reason';
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TABLE etfs (
    id               bigserial PRIMARY KEY,
    code             text NOT NULL UNIQUE CHECK (code ~ '^[A-Z]{3,5}$'),
    name             text NOT NULL,
    name_key         text NOT NULL UNIQUE,
    asset            text NOT NULL UNIQUE REFERENCES assets (code),
    account_id       uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),
    founder_id       uuid REFERENCES players (id),
    manager_id       uuid REFERENCES players (id),
    computer         boolean NOT NULL DEFAULT false,
    index_code       text REFERENCES market_indexes (code),
    commodity        text CHECK (commodity IN ('OIL', 'METALS')),
    leverage_bps     integer NOT NULL DEFAULT 10000 CHECK (leverage_bps IN (10000, 20000, -10000)),
    method           text NOT NULL DEFAULT 'full' CHECK (method IN ('full', 'sample', 'swap')),
    fee_bps          integer NOT NULL CHECK (fee_bps BETWEEN 0 AND 200),
    status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closing', 'closed')),
    nav              bigint NOT NULL,                     -- kobo a unit, at the last closing bell
    nav_day          date,
    tracked_level    numeric(30, 6),                      -- what it tracks, at the last closing bell (for a daily reset)
    reference_price  bigint NOT NULL,                     -- the last bell's closing price; the day's limits are measured from it
    last_price       bigint,
    session_date     date,
    premium_bps      integer NOT NULL DEFAULT 0,          -- where the market makers' quotes sit against the fund's value
    small_quarters   integer NOT NULL DEFAULT 0,
    launched_at      timestamptz NOT NULL,
    launched_period  integer NOT NULL,
    closing_since    timestamptz,
    closed_at        timestamptz,
    words            text NOT NULL DEFAULT '' CHECK (length(words) <= 400),
    CHECK ((index_code IS NULL) <> (commodity IS NULL))
);

-- Players' orders in ETF units, matched by the order-matching engine. Orders last until the day's closing bell.
CREATE TABLE etf_orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etf_id       bigint NOT NULL REFERENCES etfs (id),
    account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    player_id    uuid REFERENCES players (id),
    maker        boolean NOT NULL DEFAULT false,          -- the market makers' own quote
    side         text NOT NULL CHECK (side IN ('buy', 'sell')),
    limit_price  bigint NOT NULL CHECK (limit_price > 0),
    quantity     bigint NOT NULL CHECK (quantity > 0),
    remaining    bigint NOT NULL CHECK (remaining >= 0),
    reserved     bigint NOT NULL DEFAULT 0 CHECK (reserved >= 0),   -- cash (buy) or units (sell) held for it
    filled_value bigint NOT NULL DEFAULT 0,               -- what its fills came to, so far
    fee_paid     bigint NOT NULL DEFAULT 0,               -- the exchange's fee on them, so far (worked out on the running total)
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'filled', 'cancelled', 'expired')),
    session_date date NOT NULL,
    placed_at    timestamptz NOT NULL
);
CREATE INDEX etf_orders_book ON etf_orders (etf_id, side, status) WHERE status = 'open';

CREATE TABLE etf_trades (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etf_id       bigint NOT NULL REFERENCES etfs (id),
    buyer        uuid NOT NULL REFERENCES ledger_accounts (id),
    seller       uuid NOT NULL REFERENCES ledger_accounts (id),
    price        bigint NOT NULL CHECK (price > 0),
    quantity     bigint NOT NULL CHECK (quantity > 0),
    session_date date NOT NULL,
    traded_at    timestamptz NOT NULL
);
CREATE INDEX etf_trades_day ON etf_trades (etf_id, session_date);

-- Units made and unmade by dealers.
CREATE TABLE etf_creations (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etf_id       bigint NOT NULL REFERENCES etfs (id),
    account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    side         text NOT NULL CHECK (side IN ('create', 'redeem')),
    how          text NOT NULL CHECK (how IN ('basket', 'cash')),
    units        bigint NOT NULL CHECK (units > 0),
    nav          bigint NOT NULL,
    fee          bigint NOT NULL DEFAULT 0,
    at           timestamptz NOT NULL
);

-- Each ETF at each closing bell, for good: its value, its closing price, and how far apart they were.
CREATE TABLE etf_days (
    etf_id        bigint NOT NULL REFERENCES etfs (id),
    session_date  date NOT NULL,
    nav           bigint NOT NULL,
    close         bigint NOT NULL,
    units         bigint NOT NULL,
    volume        bigint NOT NULL DEFAULT 0,
    created       bigint NOT NULL DEFAULT 0,
    redeemed      bigint NOT NULL DEFAULT 0,
    tracked_bps   integer,                              -- the day's move in what it tracks (times its leverage)
    PRIMARY KEY (etf_id, session_date)
);
CREATE TRIGGER etf_days_permanent BEFORE UPDATE OR DELETE ON etf_days FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Empires approved to make and unmake ETF units (the game's own dealers, the pension funds, always are).
CREATE TABLE etf_dealers (
    empire_id    bigint PRIMARY KEY REFERENCES empires (id),
    approved_at  timestamptz NOT NULL,
    status       text NOT NULL DEFAULT 'approved' CHECK (status IN ('approved', 'withdrawn'))
);

-- A player who has read the warning about 2x and inverse ETFs.
CREATE TABLE etf_warnings (
    player_id    uuid PRIMARY KEY REFERENCES players (id),
    at           timestamptz NOT NULL
);

CREATE TABLE etf_follows (
    player_id  uuid NOT NULL REFERENCES players (id),
    etf_id     bigint NOT NULL REFERENCES etfs (id),
    at         timestamptz NOT NULL,
    PRIMARY KEY (player_id, etf_id)
);

-- Pop-ups: index changes, an ETF far from its value, record money in or out, launches and closures.
CREATE TABLE etf_alerts (
    id          bigserial PRIMARY KEY,
    etf_id      bigint REFERENCES etfs (id),
    index_code  text REFERENCES market_indexes (code),
    kind        text NOT NULL CHECK (kind IN ('index_change', 'off_value', 'flows', 'launched', 'closing', 'closed')),
    everyone    boolean NOT NULL DEFAULT false,
    headline    text NOT NULL,
    words       text NOT NULL,
    at          timestamptz NOT NULL
);

-- The quarter's record for every passive vehicle (ETFs and index funds): how closely it followed what it tracks.
CREATE TABLE tracking_quarters (
    vehicle      text NOT NULL CHECK (vehicle IN ('etf', 'fund')),
    vehicle_id   bigint NOT NULL,
    period       integer NOT NULL,
    return_bps   integer,
    tracked_bps  integer,
    difference_bps integer,
    error_bps    integer,                               -- the yearly swing of the daily gaps (tracking error)
    PRIMARY KEY (vehicle, vehicle_id, period)
);
CREATE TRIGGER tracking_quarters_permanent BEFORE UPDATE OR DELETE ON tracking_quarters FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The passive share of the market, each quarter.
CREATE TABLE passive_quarters (
    period        integer PRIMARY KEY,
    passive_value bigint NOT NULL,
    market_value  bigint NOT NULL,
    share_bps     integer NOT NULL,
    target_bps    integer NOT NULL
);

CREATE TABLE etf_progress (
    id               boolean PRIMARY KEY DEFAULT true CHECK (id),
    dealt_through    date
);
INSERT INTO etf_progress (id) VALUES (true);
