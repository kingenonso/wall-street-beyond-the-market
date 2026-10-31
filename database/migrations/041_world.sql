-- The talent and funds stage, Part 4b: foreign markets.
-- Three foreign exchanges (in the style of New York, London and Frankfurt) with their own hours, indexes and economies;
-- about thirty companies listed abroad; foreign central banks; Nigerian arms of foreign companies, whose parents' dividends
-- wait for dollars and who may sell out and leave; ETFs of foreign shares on the Broad Street Exchange.

ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_code_check;
ALTER TABLE assets ADD CONSTRAINT assets_code_check
    CHECK (code ~ '^([A-Z]{3}|SHR-[A-Z]{3}|BND-[A-Z0-9]{3,12}|PRF-[A-Z]{3}|WRT-[A-Z]{3}[0-9]{1,4}|DEP-[A-Z]{3}|ETF-[A-Z]{3,5}|EUB-[A-Z0-9]{3,8}|FSH-[A-Z]{4})$');
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_kind_check;
ALTER TABLE assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('currency', 'share', 'bond', 'preferred', 'warrant', 'deposit', 'etf', 'foreign_share'));

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
            -- Dollars, pounds and euros come into existence only from the rest of the world (Part 4a); the Central Bank makes
            -- naira when it buys foreign currency for its reserves (and takes them out of existence when it sells them).
            OR (reason = 'fx_abroad' AND asset_kind = 'currency' AND NEW.asset <> 'NGN')
            OR (reason IN ('fx_reserves', 'fx_defence') AND NEW.asset = 'NGN')
            OR (reason = 'eurobond_issue' AND asset_kind = 'bond' AND NEW.asset LIKE 'EUB-%')
            -- Shares of companies listed abroad exist once, when their registry lists them; the rest of the world holds them (Part 4b).
            OR (reason = 'foreign_listing' AND asset_kind = 'foreign_share'
                AND NOT EXISTS (SELECT 1 FROM ledger_entries e WHERE e.asset = NEW.asset AND e.transaction_id <> NEW.transaction_id))
        ) THEN
            RAISE EXCEPTION 'New % cannot be brought into existence for the reason "%".', NEW.asset, reason
                USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_issuance_reason';
        END IF;
    END IF;

    IF NEW.amount > 0 AND reason <> 'debt_repayment' THEN
        SELECT issuer_account_id, kind INTO issuer, asset_kind FROM assets WHERE code = NEW.asset;
        IF issuer = NEW.account_id AND asset_kind = 'currency'
           AND NOT (reason IN ('fx_abroad', 'fx_reserves', 'fx_defence') AND NEW.asset <> 'NGN')
           AND NOT (reason IN ('fx_reserves', 'fx_defence') AND NEW.asset = 'NGN') THEN
            RAISE EXCEPTION '% cannot be taken out of existence for the reason "%".', NEW.asset, reason
                USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_destruction_reason';
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

ALTER TABLE market_indexes DROP CONSTRAINT IF EXISTS market_indexes_kind_check;
ALTER TABLE market_indexes ADD CONSTRAINT market_indexes_kind_check CHECK (kind IN ('shares', 'bonds', 'world'));

ALTER TABLE fx_alerts DROP CONSTRAINT IF EXISTS fx_alerts_kind_check;
ALTER TABLE fx_alerts ADD CONSTRAINT fx_alerts_kind_check CHECK (kind IN ('devalued', 'floated', 'repegged', 'defended', 'gap', 'reserves',
    'backlog', 'window', 'eurobond', 'licence', 'world_rate', 'world_fall', 'world_exit', 'world_sold', 'world_trapped', 'world_dividend'));

-- The three foreign exchanges: their city, currency, hours (in their own time) and index.
CREATE TABLE world_exchanges (
    code        text PRIMARY KEY CHECK (code ~ '^[A-Z]{3}$'),
    name        text NOT NULL,
    city        text NOT NULL,
    country     text NOT NULL,                   -- US, UK, EA (the euro area)
    zone        text NOT NULL,                   -- the city's time zone
    currency    text NOT NULL CHECK (currency IN ('USD', 'GBP', 'EUR')),
    opens       time NOT NULL,
    closes      time NOT NULL,
    index_code  text NOT NULL,
    index_name  text NOT NULL,
    opened_at   timestamptz NOT NULL
);

-- Each economy abroad, every quarter: its growth and inflation that quarter, and the rate its central bank set for the next.
CREATE TABLE world_economies (
    country        text NOT NULL CHECK (country IN ('US', 'UK', 'EA')),
    period         integer NOT NULL,             -- set as this quarter closed
    growth_bps     integer NOT NULL,             -- a year's growth at this quarter's pace
    inflation_bps  integer NOT NULL,
    rate_bps       integer NOT NULL,             -- the central bank's rate for the quarter after
    words          text NOT NULL DEFAULT '',
    at             timestamptz NOT NULL,
    PRIMARY KEY (country, period)
);
CREATE TRIGGER world_economies_permanent BEFORE UPDATE OR DELETE ON world_economies FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The companies listed abroad.
CREATE TABLE world_companies (
    id             bigserial PRIMARY KEY,
    ticker         text NOT NULL UNIQUE CHECK (ticker ~ '^[A-Z]{4}$'),
    name           text NOT NULL,
    exchange       text NOT NULL REFERENCES world_exchanges (code),
    city           text NOT NULL,
    sector         text NOT NULL,
    asset          text NOT NULL UNIQUE REFERENCES assets (code),
    shares         bigint NOT NULL CHECK (shares > 0),
    revenue        bigint NOT NULL,              -- the last quarter's sales (cents, pence or euro cents)
    margin_bps     integer NOT NULL,             -- its usual profit on sales
    payout_bps     integer NOT NULL,             -- the share of its profits it pays out
    trend_bps      integer NOT NULL DEFAULT 0,   -- its own growth above or below its economy's, a year
    beta_bps       integer NOT NULL DEFAULT 10000,
    about          text NOT NULL DEFAULT '',
    fair           numeric(20, 4) NOT NULL,      -- what one share is worth on its earnings and its country's interest rate (cents)
    eps_ttm        numeric(20, 4) NOT NULL,      -- profit for each share over the last four quarters (cents)
    dps            numeric(20, 4) NOT NULL DEFAULT 0   -- the last quarter's dividend for each share (cents)
);

-- Where each share's price stands: the price at the last re-basing, and today's buying and selling.
CREATE TABLE world_quotes (
    company_id   bigint PRIMARY KEY REFERENCES world_companies (id),
    base         numeric(20, 4) NOT NULL CHECK (base > 0),
    base_at      timestamptz NOT NULL,
    impact_bps   integer NOT NULL DEFAULT 0
);

-- Each trading day's closing price, for good.
CREATE TABLE world_days (
    company_id   bigint NOT NULL REFERENCES world_companies (id),
    day          date NOT NULL,                  -- the exchange's own date
    close        numeric(20, 4) NOT NULL,
    PRIMARY KEY (company_id, day)
);
CREATE TRIGGER world_days_permanent BEFORE UPDATE OR DELETE ON world_days FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE world_index_days (
    exchange     text NOT NULL REFERENCES world_exchanges (code),
    day          date NOT NULL,
    level        bigint NOT NULL,                -- hundredths of a point, in the exchange's own currency
    PRIMARY KEY (exchange, day)
);
CREATE TRIGGER world_index_days_permanent BEFORE UPDATE OR DELETE ON world_index_days FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Each company's quarter: sales, profit, profit and dividend for each share.
CREATE TABLE world_results (
    company_id   bigint NOT NULL REFERENCES world_companies (id),
    period       integer NOT NULL,
    revenue      bigint NOT NULL,
    profit       bigint NOT NULL,
    eps          numeric(20, 4) NOT NULL,
    dps          numeric(20, 4) NOT NULL,
    fair         numeric(20, 4) NOT NULL,
    pe           numeric(10, 2) NOT NULL,
    words        text NOT NULL DEFAULT '',
    PRIMARY KEY (company_id, period)
);
CREATE TRIGGER world_results_permanent BEFORE UPDATE OR DELETE ON world_results FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Dividends paid, for each share, in the company's currency and in naira at the street rate that day (for indexes).
CREATE TABLE world_dividends (
    company_id   bigint NOT NULL REFERENCES world_companies (id),
    period       integer NOT NULL,
    per_share    numeric(20, 4) NOT NULL,        -- after the tax withheld abroad
    naira        numeric(20, 4) NOT NULL,        -- kobo for each share
    paid         bigint NOT NULL,                -- to everybody holding it outside the rest of the world
    PRIMARY KEY (company_id, period)
);
CREATE TRIGGER world_dividends_permanent BEFORE UPDATE OR DELETE ON world_dividends FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Every deal by a player or an empire.
CREATE TABLE world_trades (
    id           bigserial PRIMARY KEY,
    account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id   bigint NOT NULL REFERENCES world_companies (id),
    side         text NOT NULL CHECK (side IN ('buy', 'sell')),
    shares       bigint NOT NULL CHECK (shares > 0),
    price        bigint NOT NULL CHECK (price > 0),        -- cents (or pence) for each share
    amount       bigint NOT NULL CHECK (amount > 0),       -- in the currency
    rate         bigint NOT NULL CHECK (rate > 0),         -- kobo for one unit of the currency on the street at that moment
    period       integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE INDEX world_trades_account ON world_trades (account_id, at);
CREATE INDEX world_trades_company ON world_trades (company_id, at);
CREATE TRIGGER world_trades_permanent BEFORE UPDATE OR DELETE ON world_trades FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- What a holding cost, for the gain on the share and the gain on the currency.
CREATE TABLE world_positions (
    account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id   bigint NOT NULL REFERENCES world_companies (id),
    cost         bigint NOT NULL DEFAULT 0,      -- in the currency
    cost_naira   bigint NOT NULL DEFAULT 0,      -- what that currency cost in naira at the time
    PRIMARY KEY (account_id, company_id)
);

-- Nigerian companies whose largest owner is a company listed abroad.
CREATE TABLE world_arms (
    company_id        uuid PRIMARY KEY REFERENCES companies (id),
    parent_id         bigint NOT NULL REFERENCES world_companies (id),
    parent_account    uuid NOT NULL REFERENCES ledger_accounts (id),
    status            text NOT NULL DEFAULT 'parent' CHECK (status IN ('parent', 'leaving', 'left')),
    pressure          integer NOT NULL DEFAULT 0,          -- quarters in a row the parent has had reason to leave
    announced_period  integer,
    deadline_period   integer,
    asking_bps        integer NOT NULL DEFAULT 1000,       -- while leaving: how far below the market it sells its stake
    sold_to           text,
    sold_period       integer,
    words             text NOT NULL DEFAULT ''
);

-- Each quarter: what a parent wanted to send home, what went, and what is still waiting.
CREATE TABLE world_repatriation (
    company_id   uuid NOT NULL REFERENCES companies (id),
    period       integer NOT NULL,
    waiting      bigint NOT NULL,                -- naira the parent holds here, before (kobo)
    sent         bigint NOT NULL,                -- naira turned into dollars and sent home
    dollars      bigint NOT NULL,
    PRIMARY KEY (company_id, period)
);
CREATE TRIGGER world_repatriation_permanent BEFORE UPDATE OR DELETE ON world_repatriation FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Pieces of a leaving parent's stake bought by empires.
CREATE TABLE world_stake_sales (
    id           bigserial PRIMARY KEY,
    company_id   uuid NOT NULL REFERENCES companies (id),
    buyer        text NOT NULL,
    account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    shares       bigint NOT NULL CHECK (shares > 0),
    price        bigint NOT NULL CHECK (price > 0),
    period       integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE TRIGGER world_stake_sales_permanent BEFORE UPDATE OR DELETE ON world_stake_sales FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
