-- The talent and funds stage, Part 4a: the currency desk and money from abroad.
-- Two naira rates (the Central Bank's official window and the street); the Central Bank's dollar reserves; dollar, pound and
-- euro accounts; bureaux de change; money sent home from abroad; companies' dollar debts; Eurobonds; the foreign investors'
-- dollar backlog; currency forwards (as swaps).

ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_code_check;
ALTER TABLE assets ADD CONSTRAINT assets_code_check
    CHECK (code ~ '^([A-Z]{3}|SHR-[A-Z]{3}|BND-[A-Z0-9]{3,12}|PRF-[A-Z]{3}|WRT-[A-Z]{3}[0-9]{1,4}|DEP-[A-Z]{3}|ETF-[A-Z]{3,5}|EUB-[A-Z0-9]{3,8})$');
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_unit_check;
ALTER TABLE assets ADD CONSTRAINT assets_unit_check CHECK (unit IN ('kobo', 'cent', 'share', 'bond', 'preferred', 'warrant', 'unit'));

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


-- Each quarter's naira: the market's rate (abroad_results), the Central Bank's official rate and how it runs it, its reserves.
CREATE TABLE fx_quarters (
    period            integer PRIMARY KEY,                -- set as this quarter closed, in force for the quarter after it
    official          bigint NOT NULL CHECK (official > 0),   -- kobo for one US dollar
    market            bigint NOT NULL CHECK (market > 0),
    regime            text NOT NULL CHECK (regime IN ('managed', 'float')),
    reserves          bigint NOT NULL,                    -- the Central Bank's dollars (cents), at the close
    cover_bps         integer NOT NULL,                   -- reserves against a quarter's imports
    gbp_usd           numeric(12, 6) NOT NULL,            -- dollars for one pound
    eur_usd           numeric(12, 6) NOT NULL,            -- dollars for one euro
    sold              bigint NOT NULL DEFAULT 0,          -- dollars the Central Bank sold defending the naira this quarter (cents)
    backlog           bigint NOT NULL DEFAULT 0,          -- foreign investors' naira waiting for dollars to leave (kobo)
    event             text CHECK (event IN ('devalued', 'floated', 'repegged', 'defended')),
    words             text NOT NULL DEFAULT '',
    at                timestamptz NOT NULL
);
CREATE TRIGGER fx_quarters_permanent BEFORE UPDATE OR DELETE ON fx_quarters FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Each trading day's street market.
CREATE TABLE fx_days (
    session_date   date PRIMARY KEY,
    official       bigint NOT NULL,
    street         bigint NOT NULL,                       -- the street's middle rate, kobo for one dollar
    premium_bps    integer NOT NULL,                      -- how far the street is above the official rate
    street_net     bigint NOT NULL DEFAULT 0,             -- dollars bought (+) or sold (-) on the street that day (cents)
    window_paid    bigint NOT NULL DEFAULT 0,             -- dollars the official window handed out (cents)
    remitted       bigint NOT NULL DEFAULT 0,             -- dollars sent home from abroad (cents)
    reserves       bigint NOT NULL,
    gbp_usd        numeric(12, 6) NOT NULL,
    eur_usd        numeric(12, 6) NOT NULL,
    at             timestamptz NOT NULL
);
CREATE TRIGGER fx_days_permanent BEFORE UPDATE OR DELETE ON fx_days FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Where the street stands now (moved by every deal on it, between bells).
CREATE TABLE fx_street (
    id             integer PRIMARY KEY CHECK (id = 1),
    impact_bps     integer NOT NULL DEFAULT 0,            -- today's buying pushes the street up, selling down
    session_date   date
);

-- Every currency deal: the street, the official window, a bureau de change. Permanent (it is what a bureau reports, and
-- what stops dollars bought at the official rate being sold on the street).
CREATE TABLE fx_trades (
    id          bigserial PRIMARY KEY,
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    venue       text NOT NULL CHECK (venue IN ('street', 'window', 'bdc')),
    bdc_id      bigint,
    side        text NOT NULL CHECK (side IN ('buy', 'sell')),       -- buying or selling the foreign currency
    currency    text NOT NULL CHECK (currency IN ('USD', 'GBP', 'EUR')),
    amount      bigint NOT NULL CHECK (amount > 0),                  -- cents
    rate        bigint NOT NULL CHECK (rate > 0),                    -- kobo for one unit of the currency
    naira       bigint NOT NULL CHECK (naira > 0),
    period      integer NOT NULL,
    at          timestamptz NOT NULL
);
CREATE INDEX fx_trades_account ON fx_trades (account_id, period);
CREATE TRIGGER fx_trades_permanent BEFORE UPDATE OR DELETE ON fx_trades FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Requests for dollars at the official window: they wait in line for the Central Bank's daily allocation.
CREATE TABLE fx_window (
    id          bigserial PRIMARY KEY,
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    amount      bigint NOT NULL CHECK (amount > 0),                  -- dollars asked for (cents)
    filled      bigint NOT NULL DEFAULT 0 CHECK (filled >= 0),
    held        bigint NOT NULL DEFAULT 0 CHECK (held >= 0),         -- naira held for what is still to be filled
    status      text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'filled', 'cancelled', 'expired')),
    period      integer NOT NULL,
    placed_at   timestamptz NOT NULL,
    closed_at   timestamptz,
    CHECK (filled <= amount)
);
CREATE INDEX fx_window_line ON fx_window (status, id);

-- Bureaux de change run by empires: licensed, with their own prices around the street's middle rate.
CREATE TABLE bdcs (
    id           bigserial PRIMARY KEY,
    empire_id    bigint NOT NULL REFERENCES empires (id),
    name         text NOT NULL,
    buy_bps      integer NOT NULL CHECK (buy_bps BETWEEN 0 AND 1000),    -- it buys dollars this far below the street's middle
    sell_bps     integer NOT NULL CHECK (sell_bps BETWEEN 0 AND 1000),   -- and sells this far above
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    licensed_at  timestamptz NOT NULL,
    closed_at    timestamptz
);
CREATE UNIQUE INDEX bdcs_one_open ON bdcs (empire_id) WHERE status = 'open';

-- What a bureau reported to the regulator: every deal at or above the reporting line (filed by the game as it happens).
CREATE TABLE bdc_reports (
    id         bigserial PRIMARY KEY,
    bdc_id     bigint NOT NULL REFERENCES bdcs (id),
    trade_id   bigint REFERENCES fx_trades (id),
    customer   text NOT NULL,                      -- 'a player', 'an empire', 'households'
    amount     bigint NOT NULL,
    naira      bigint NOT NULL,
    at         timestamptz NOT NULL
);
CREATE TRIGGER bdc_reports_permanent BEFORE UPDATE OR DELETE ON bdc_reports FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Money-transfer companies carrying what Nigerians abroad send home: the computer's and empires'.
CREATE TABLE remitters (
    id          bigserial PRIMARY KEY,
    empire_id   bigint REFERENCES empires (id),    -- empty: one of the computer's
    name        text NOT NULL,
    fee_bps     integer NOT NULL CHECK (fee_bps BETWEEN 0 AND 1500),
    days        integer NOT NULL CHECK (days BETWEEN 0 AND 5),              -- how long the money takes to arrive
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    licensed_at timestamptz NOT NULL,
    closed_at   timestamptz
);
CREATE UNIQUE INDEX remitters_one_open ON remitters (empire_id) WHERE status = 'open' AND empire_id IS NOT NULL;

CREATE TABLE remittances (
    remitter_id   bigint NOT NULL REFERENCES remitters (id),
    session_date  date NOT NULL,
    dollars       bigint NOT NULL,      -- cents sent
    naira         bigint NOT NULL,      -- what the families received
    fee           bigint NOT NULL,      -- what the company kept (kobo)
    cost          bigint NOT NULL DEFAULT 0,   -- what its speed cost it (kobo)
    PRIMARY KEY (remitter_id, session_date)
);
CREATE TRIGGER remittances_permanent BEFORE UPDATE OR DELETE ON remittances FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Dollar debts: a company's loan in dollars is kept in naira, revalued every quarter at the official rate.
ALTER TABLE company_debts ADD COLUMN currency text NOT NULL DEFAULT 'NGN' CHECK (currency IN ('NGN', 'USD'));
ALTER TABLE company_debts ADD COLUMN fx_rate bigint CHECK (fx_rate > 0);   -- kobo a dollar at the last revaluation
ALTER TABLE company_debts ADD CONSTRAINT company_debts_fx_rate CHECK ((currency = 'NGN') = (fx_rate IS NULL));

CREATE TABLE fx_revaluations (
    company_id  uuid NOT NULL REFERENCES companies (id),
    debt_id     uuid NOT NULL REFERENCES company_debts (id),
    period      integer NOT NULL,
    amount      bigint NOT NULL,        -- naira the debt grew by (a loss) or shrank by (a gain, negative)
    rate        bigint NOT NULL,
    PRIMARY KEY (debt_id, period)
);
CREATE TRIGGER fx_revaluations_permanent BEFORE UPDATE OR DELETE ON fx_revaluations FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Eurobonds: dollar bonds of the Government and of large companies, bought and sold with dollars.
CREATE TABLE eurobonds (
    id               bigserial PRIMARY KEY,
    asset            text NOT NULL UNIQUE REFERENCES assets (code),
    name             text NOT NULL,
    issuer           text NOT NULL CHECK (issuer IN ('government', 'company')),
    company_id       uuid REFERENCES companies (id),
    debt_id          uuid REFERENCES company_debts (id),
    face             bigint NOT NULL CHECK (face > 0),          -- cents for one bond
    coupon_bps       integer NOT NULL CHECK (coupon_bps >= 0),
    issued_period    integer NOT NULL,
    maturity_period  integer NOT NULL,
    units            bigint NOT NULL CHECK (units > 0),
    redeemed_period  integer,
    defaulted        boolean NOT NULL DEFAULT false,
    CHECK ((issuer = 'company') = (company_id IS NOT NULL))
);

CREATE TABLE eurobond_payments (
    eurobond_id  bigint NOT NULL REFERENCES eurobonds (id),
    period       integer NOT NULL,
    per_bond     bigint NOT NULL,       -- cents paid on one bond (interest, and the face when it is repaid)
    paid         bigint NOT NULL,
    short        bigint NOT NULL DEFAULT 0,
    at           timestamptz NOT NULL,
    PRIMARY KEY (eurobond_id, period)
);
CREATE TRIGGER eurobond_payments_permanent BEFORE UPDATE OR DELETE ON eurobond_payments FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- Pop-ups: a devaluation, a float, a wide gap, reserves falling, the Central Bank stepping in, the dollar backlog.
CREATE TABLE fx_alerts (
    id          bigserial PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('devalued', 'floated', 'repegged', 'defended', 'gap', 'reserves', 'backlog',
                                              'window', 'eurobond', 'licence')),
    account_id  uuid REFERENCES ledger_accounts (id),       -- empty: for everybody
    headline    text NOT NULL,
    words       text NOT NULL,
    at          timestamptz NOT NULL
);

-- The bell work already done.
CREATE TABLE fx_progress (
    id             integer PRIMARY KEY CHECK (id = 1),
    dealt_through  date
);

ALTER TABLE swaps DROP CONSTRAINT IF EXISTS swaps_kind_check;
ALTER TABLE swaps ADD CONSTRAINT swaps_kind_check CHECK (kind IN ('rate', 'oil', 'fx'));
INSERT INTO fx_progress (id) VALUES (1);
INSERT INTO fx_street (id) VALUES (1);

-- Foreign investors' money that wanted to leave but found no dollars (Part 4a).
ALTER TABLE abroad_results ADD COLUMN fx_backlog bigint NOT NULL DEFAULT 0;

-- A company's currency loss (or gain, negative) on its dollar debts, a line between interest and profit before tax.
ALTER TABLE company_results ADD COLUMN currency_loss bigint NOT NULL DEFAULT 0;
