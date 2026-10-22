-- The crises stage, Part 1: money kept at real, named banks; trust in each bank; the Crisis Watch; bank runs that
-- spread and can be stopped; the Central Bank's emergency lending; the deposit guarantee; banks that fail, are
-- rescued at the Auction House or taken into public hands; and the record of every crisis.

-- ---------------------------------------------------------------------------
-- Deposits. Money kept at a bank is a claim on that bank, recorded in the ledger as the bank's own "deposit"
-- asset (DEP-<ticker>), one kobo a unit. The bank is its issuer: what it owes its savers is exactly what it has
-- put out. A claim comes into existence only when money is paid in (or, once, when the savers the bank already
-- had are written into the ledger), and goes out of existence when it is paid back or written down.
-- ---------------------------------------------------------------------------
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_code_check;
ALTER TABLE assets ADD CONSTRAINT assets_code_check
    CHECK (code ~ '^([A-Z]{3}|SHR-[A-Z]{3}|BND-[A-Z0-9]{3,12}|PRF-[A-Z]{3}|WRT-[A-Z]{3}[0-9]{1,4}|DEP-[A-Z]{3})$');
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_kind_check;
ALTER TABLE assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('currency', 'share', 'bond', 'preferred', 'warrant', 'deposit'));

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
            OR (reason IN ('deposit_record', 'savings_placed', 'deposit_placed', 'company_savings') AND asset_kind = 'deposit')
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

-- Each bank's deposit asset.
CREATE TABLE bank_deposits (
    company_id   uuid PRIMARY KEY REFERENCES companies (id),
    asset        text NOT NULL UNIQUE REFERENCES assets (code),
    recorded_period integer NOT NULL,                    -- when the savers it already had were written into the ledger
    at           timestamptz NOT NULL
);

-- How much of each city's savings at each bank belongs to savers under the guarantee line (those above it run first).
CREATE TABLE household_deposits_covered (
    company_id  uuid NOT NULL REFERENCES companies (id),
    location    text NOT NULL REFERENCES locations (name),
    covered     bigint NOT NULL DEFAULT 0 CHECK (covered >= 0),
    PRIMARY KEY (company_id, location)
);

-- What households drew out in fear and keep at home for now; they put it back into the banks they trust as calm returns.
CREATE TABLE household_cash_held (
    location   text PRIMARY KEY REFERENCES locations (name),
    amount     bigint NOT NULL DEFAULT 0 CHECK (amount >= 0)
);

-- Every move of savers' money, day by day (the ledger holds the money; this says who, where and why, for the records).
CREATE TABLE deposit_flows (
    id          bigserial PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    holder      text NOT NULL CHECK (holder IN ('households', 'player', 'empire', 'company')),
    location    text REFERENCES locations (name),
    kind        text NOT NULL CHECK (kind IN ('placed', 'withdrawn', 'run', 'returned', 'bail_in', 'recorded')),
    amount      bigint NOT NULL CHECK (amount > 0),
    period      integer NOT NULL,
    day         integer NOT NULL,
    at          timestamptz NOT NULL
);
CREATE INDEX deposit_flows_bank ON deposit_flows (company_id, period, day);
CREATE INDEX deposit_flows_account ON deposit_flows (account_id, period);

-- Interest paid on savings, once a quarter, on the least kept through the whole quarter.
CREATE TABLE savings_interest (
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    period      integer NOT NULL,
    lowest      bigint NOT NULL,
    rate_bps    integer NOT NULL,
    amount      bigint NOT NULL,
    PRIMARY KEY (account_id, company_id, period)
);

-- ---------------------------------------------------------------------------
-- Trust. Each bank's trust score (0 to 100), every game day, with the parts it was made of (all public signals).
-- ---------------------------------------------------------------------------
CREATE TABLE bank_confidence (
    company_id  uuid NOT NULL REFERENCES companies (id),
    period      integer NOT NULL,
    day         integer NOT NULL,
    score       integer NOT NULL CHECK (score BETWEEN 0 AND 100),
    state       text NOT NULL CHECK (state IN ('calm', 'worried', 'run', 'panic', 'closed')),
    parts       jsonb NOT NULL,
    withdrawn   bigint NOT NULL DEFAULT 0,               -- what savers drew out that day
    at          timestamptz NOT NULL,
    PRIMARY KEY (company_id, period, day)
);

-- The whole country, each game day: trust in the banks taken together, and whether every saving is guaranteed.
CREATE TABLE crisis_days (
    period      integer NOT NULL,
    day         integer NOT NULL,
    national    integer NOT NULL,
    blanket     boolean NOT NULL DEFAULT false,
    at          timestamptz NOT NULL,
    PRIMARY KEY (period, day)
);

-- The Crisis Watch's reading at each close: every warning sign, its level and why.
CREATE TABLE crisis_watch (
    period      integer PRIMARY KEY,
    readings    jsonb NOT NULL,
    at          timestamptz NOT NULL
);

-- ---------------------------------------------------------------------------
-- What institutions did.
-- ---------------------------------------------------------------------------
-- The Central Bank's emergency lending to a bank whose savers are leaving (at a penalty rate, against its loans).
CREATE TABLE central_bank_support (
    id          bigserial PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    period      integer NOT NULL,
    day         integer NOT NULL,
    amount      bigint NOT NULL CHECK (amount > 0),
    at          timestamptz NOT NULL
);
CREATE INDEX central_bank_support_bank ON central_bank_support (company_id, period, day);

-- The Government's promise that every saving, whatever its size, is safe.
CREATE TABLE blanket_guarantees (
    id            bigserial PRIMARY KEY,
    from_period   integer NOT NULL,
    from_day      integer NOT NULL,
    until_period  integer,
    until_day     integer,
    reason        text NOT NULL,
    at            timestamptz NOT NULL
);

-- A bank in trouble raises new money: its big institutional owners buy new shares at a discount.
CREATE TABLE emergency_placements (
    id          bigserial PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    period      integer NOT NULL,
    day         integer NOT NULL,
    shares      bigint NOT NULL,
    price       bigint NOT NULL,
    amount      bigint NOT NULL,
    at          timestamptz NOT NULL
);

-- What the deposit guarantee fund borrowed from the Treasury when its own money was not enough.
CREATE TABLE guarantee_fund_loans (
    id           bigserial PRIMARY KEY,
    amount       bigint NOT NULL CHECK (amount > 0),
    outstanding  bigint NOT NULL CHECK (outstanding >= 0),
    period       integer NOT NULL,
    at           timestamptz NOT NULL
);

-- A bank the Central Bank closed: what it owed, what it had, who bore the loss, and where it went.
CREATE TABLE bank_resolutions (
    id              bigserial PRIMARY KEY,
    company_id      uuid NOT NULL REFERENCES companies (id),
    period          integer NOT NULL,
    day             integer NOT NULL,
    reason          text NOT NULL,
    equity          bigint NOT NULL,                 -- its owners' funds when closed (below zero: a hole)
    bail_in         bigint NOT NULL DEFAULT 0,       -- savings above the guarantee written down to fill the hole
    covered         bigint NOT NULL DEFAULT 0,       -- what the guarantee fund put in to fill what was left of it
    capital_needed  bigint NOT NULL,                 -- the new money it needs to open again, sound
    auction_id      bigint,
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'sold', 'public', 'resold')),
    new_owner       uuid REFERENCES ledger_accounts (id),
    price           bigint,
    resale_period   integer,                         -- public hands: when its shares go back on sale
    words           text NOT NULL DEFAULT '',
    at              timestamptz NOT NULL,
    ended_at        timestamptz
);
CREATE UNIQUE INDEX bank_resolutions_one_open ON bank_resolutions (company_id) WHERE status = 'open';

-- A share whose trading is stopped (a bank closed by the Central Bank, until it is resolved).
ALTER TABLE market_instruments ADD COLUMN halted_reason text;

-- The Auction House sells a closed bank to whoever puts in the most new money, or the guarantee fund's stake later.
ALTER TABLE auctions ADD COLUMN bank_id uuid REFERENCES companies (id);
ALTER TABLE auctions DROP CONSTRAINT IF EXISTS auctions_one_lot;
ALTER TABLE auctions ADD CONSTRAINT auctions_one_lot CHECK (num_nonnulls(property_id, title_id, bank_id) = 1);
ALTER TABLE auctions DROP CONSTRAINT IF EXISTS auctions_reason_check;
ALTER TABLE auctions ADD CONSTRAINT auctions_reason_check CHECK (reason IN ('listing', 'owner', 'repossession', 'tax', 'rescue', 'public_sale'));
CREATE UNIQUE INDEX auctions_one_open_bank ON auctions (bank_id) WHERE status = 'open' AND bank_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Crises: each one from its first warning to its place in history.
-- ---------------------------------------------------------------------------
CREATE TABLE economic_crises (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL CHECK (kind IN ('banking', 'housing', 'commodity', 'government_debt', 'corporate',
                                                  'market_cash', 'trade', 'confidence')),
    title           text NOT NULL,
    step            integer NOT NULL CHECK (step BETWEEN 1 AND 10),
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'faded', 'ended')),
    started_period  integer NOT NULL,
    started_day     integer NOT NULL,
    ended_period    integer,
    ended_day       integer,
    banks           uuid[] NOT NULL DEFAULT '{}',
    weakness        text NOT NULL,                   -- SECRET until it ends: the hidden weakness it grew from
    steps           jsonb NOT NULL DEFAULT '[]',     -- [{step, period, day, words}]
    report          jsonb,                           -- written when it ends: permanent
    at              timestamptz NOT NULL
);
CREATE UNIQUE INDEX economic_crises_one_open_kind ON economic_crises (kind) WHERE status = 'open';

-- Ledger accounts for the deposit guarantee fund are of the Government kind (no new kind is needed).
