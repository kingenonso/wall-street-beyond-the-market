-- Stage 3, Part B: prices, the Central Bank, real bank lending, events,
-- the Money Watch and the news wire (design document, sections 10, 11, 12, 14).

-- ---------------------------------------------------------------------------
-- The economy, quarter by quarter. One row per quarter, never changed.
-- Rates and indexes are in hundredths of a percent; an index starts at 10000.
-- ---------------------------------------------------------------------------
CREATE TABLE economy_results (
    period                 integer PRIMARY KEY CHECK (period >= 0),
    price_index_bps        bigint NOT NULL CHECK (price_index_bps > 0),    -- the general level of prices
    inflation_bps          integer NOT NULL,                               -- price rise over the last year
    wage_index_bps         bigint NOT NULL CHECK (wage_index_bps > 0),     -- what a worker is paid, against the start
    capacity_index_bps     bigint NOT NULL CHECK (capacity_index_bps > 0), -- how much the economy can produce
    policy_rate_bps        integer NOT NULL,                               -- the Central Bank's rate in force this quarter
    next_policy_rate_bps   integer NOT NULL,                               -- the rate it set for the next quarter
    rate_reason            text NOT NULL,
    company_sales          bigint NOT NULL,
    household_spending     bigint NOT NULL,
    money                  bigint NOT NULL,                                -- all the naira in existence
    energy_bps             bigint NOT NULL CHECK (energy_bps > 0),         -- commodity prices
    metals_bps             bigint NOT NULL CHECK (metals_bps > 0),
    agriculture_bps        bigint NOT NULL CHECK (agriculture_bps > 0),
    materials_bps          bigint NOT NULL CHECK (materials_bps > 0),
    premium_index_bps      bigint NOT NULL CHECK (premium_index_bps > 0),  -- the price of insurance
    confidence_bps         integer NOT NULL,                               -- how ready households are to spend (10000 = usual)
    demand_gap_bps         integer NOT NULL DEFAULT 0,                     -- spending against what the economy can supply (0 = in step)
    closed_at              timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER economy_results_permanent BEFORE UPDATE OR DELETE ON economy_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER economy_results_no_truncate BEFORE TRUNCATE ON economy_results
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Banks lend for real.
-- ---------------------------------------------------------------------------
-- What each location's households owe each bank.
CREATE TABLE household_debts (
    bank_company_id  uuid NOT NULL REFERENCES companies (id),
    location         text NOT NULL REFERENCES locations (name),
    principal        bigint NOT NULL CHECK (principal >= 0),
    PRIMARY KEY (bank_company_id, location)
);

ALTER TABLE household_results ADD COLUMN claims bigint NOT NULL DEFAULT 0;      -- paid by insurers
ALTER TABLE household_results ADD COLUMN borrowed bigint NOT NULL DEFAULT 0;    -- new loans taken this quarter
ALTER TABLE household_results ADD COLUMN debt bigint NOT NULL DEFAULT 0;        -- owed to the banks at the end of the quarter

-- A bank may also borrow from the Central Bank.
ALTER TABLE company_debts DROP CONSTRAINT company_debts_kind_check;
ALTER TABLE company_debts ADD CONSTRAINT company_debts_kind_check
    CHECK (kind IN ('bank_loan', 'bond', 'central_bank_loan'));
ALTER TABLE company_debts DROP CONSTRAINT company_debts_check;      -- outstanding <= original: a loan can now be topped up
-- What the lender has written off as unlikely to be repaid. The borrower still owes all of it.
ALTER TABLE company_debts ADD COLUMN provision bigint NOT NULL DEFAULT 0 CHECK (provision >= 0);
-- A borrower may repay part of a written-down loan before its lender next closes its books;
-- the lender takes the write-down back at its next close, so no "provision <= loan" rule here.

ALTER TABLE company_results ADD COLUMN loan_losses bigint NOT NULL DEFAULT 0;

-- New money can now also come into existence when the Central Bank lends to a
-- bank, and goes out of existence when the bank repays. Still nothing else.
CREATE OR REPLACE FUNCTION ledger_apply_entry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    opened_in    bigint;
    reason       text;
    new_balance  bigint;
    issuer       uuid;
    asset_kind   text;
BEGIN
    -- Rule 4: entries can only join a transaction that is still being written.
    SELECT created_txid, kind INTO opened_in, reason FROM ledger_transactions WHERE id = NEW.transaction_id;
    IF opened_in IS DISTINCT FROM txid_current() THEN
        RAISE EXCEPTION 'That ledger transaction is closed. Nothing can be added to it.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_transaction_closed';
    END IF;

    -- Rule 5: this is the only place a balance changes.
    INSERT INTO ledger_balances (account_id, asset, balance)
    VALUES (NEW.account_id, NEW.asset, NEW.amount)
    ON CONFLICT (account_id, asset)
        DO UPDATE SET balance = ledger_balances.balance + EXCLUDED.balance
    RETURNING balance INTO new_balance;

    -- Rule 3: only the issuer of an asset may go below zero in it.
    IF new_balance < 0 THEN
        SELECT issuer_account_id INTO issuer FROM assets WHERE code = NEW.asset;
        IF issuer IS DISTINCT FROM NEW.account_id THEN
            RAISE EXCEPTION 'Not enough % in the account to make this payment.', NEW.asset
                USING ERRCODE = 'check_violation', CONSTRAINT = 'ledger_insufficient_balance';
        END IF;
        -- The issuer paying out while below zero is new money, or new shares, coming
        -- into existence. That is allowed for these reasons only.
        --   * opening balances: only before the world's first quarter has closed;
        --   * a share issue: only for shares, never for money;
        --   * the Central Bank lending to a bank: only for money.
        SELECT kind INTO asset_kind FROM assets WHERE code = NEW.asset;
        IF NEW.amount < 0 AND NOT (
               (reason = 'opening_balance' AND NOT EXISTS (SELECT 1 FROM world_state WHERE last_closed_period >= 1))
            OR (reason = 'share_issue' AND asset_kind = 'share')
            OR (reason = 'central_bank_lending' AND asset_kind = 'currency')
        ) THEN
            RAISE EXCEPTION 'New % cannot be brought into existence for the reason "%".', NEW.asset, reason
                USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_issuance_reason';
        END IF;
    END IF;

    -- Money paid back to the Central Bank goes out of existence. That is allowed for one
    -- reason only: a bank repaying what the Central Bank lent it.
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

-- ---------------------------------------------------------------------------
-- The ten kinds of people (design document, section 4).
-- ---------------------------------------------------------------------------
CREATE TABLE household_mindsets (
    location   text NOT NULL REFERENCES locations (name),
    mindset    text NOT NULL CHECK (mindset IN (
                   'optimistic', 'pessimistic', 'risk_averse', 'risk_seeking', 'herding',
                   'contrarian', 'loyal', 'fearful', 'sceptical', 'opportunistic')),
    share_bps  integer NOT NULL CHECK (share_bps BETWEEN 0 AND 10000),
    PRIMARY KEY (location, mindset)
);

-- ---------------------------------------------------------------------------
-- Events: the real causes of good and bad quarters.
-- An event belongs to one quarter and happens on one of its 90 days. It is
-- decided when the quarter before closes, and stays out of sight until its day.
-- ---------------------------------------------------------------------------
CREATE TABLE events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period      integer NOT NULL CHECK (period >= 1),
    day         integer NOT NULL CHECK (day BETWEEN 1 AND 90),
    kind        text NOT NULL CHECK (kind IN (
                    'flood', 'power_failure', 'security_incident', 'port_disruption', 'pipeline_incident', 'drought',
                    'local_boom', 'sector_strike', 'sector_demand_surge', 'good_harvest', 'network_outage',
                    'new_competition', 'company_strike', 'scandal', 'contract_win', 'factory_fire', 'product_recall',
                    'new_product', 'energy_price_jump', 'energy_price_fall', 'metals_price_jump', 'metals_price_fall',
                    'materials_shortage')),
    location    text REFERENCES locations (name),
    sector      text REFERENCES sectors (code),
    company_id  uuid REFERENCES companies (id),
    -- How hard it hits, each in hundredths of a percent.
    sales_bps   integer NOT NULL DEFAULT 0,     -- change in the pull of the companies it touches
    cost_bps    integer NOT NULL DEFAULT 0,     -- extra cost, as a share of their sales
    damage_bps  integer NOT NULL DEFAULT 0,     -- share of their buildings and machines destroyed
    mood_bps    integer NOT NULL DEFAULT 0,     -- change in local households' readiness to spend
    commodity   text CHECK (commodity IN ('energy', 'metals', 'agriculture', 'materials')),
    price_bps   integer NOT NULL DEFAULT 0,     -- change in that commodity's price
    severe      boolean NOT NULL DEFAULT false,
    facts       jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_by_period ON events (period, day);
CREATE TRIGGER events_permanent BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER events_no_truncate BEFORE TRUNCATE ON events
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- The Money Watch (design document, section 10).
-- ---------------------------------------------------------------------------
CREATE TABLE money_watch_results (
    period               integer PRIMARY KEY CHECK (period >= 0),
    reading              text NOT NULL CHECK (reading IN ('green', 'amber', 'red')),
    money                bigint NOT NULL,
    money_growth_bps     integer NOT NULL,     -- over the last year
    output_growth_bps    integer NOT NULL,     -- sales of all companies, over the last year
    holders              jsonb NOT NULL,       -- where the money sits, in hundredths of a percent
    unusual_accounts     integer NOT NULL,
    grants_left          bigint NOT NULL,      -- how many more starting grants the Treasury's reserve can pay
    reasons              jsonb NOT NULL,
    action               text NOT NULL,
    closed_at            timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER money_watch_permanent BEFORE UPDATE OR DELETE ON money_watch_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER money_watch_no_truncate BEFORE TRUNCATE ON money_watch_results
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- Accounts the Money Watch wants a person to look at. Seen by the operators only.
CREATE TABLE money_watch_flags (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period      integer NOT NULL,
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    reason      text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- The news wire (design document, section 12). News is never invented: every
-- item reports something recorded elsewhere in the game.
-- ---------------------------------------------------------------------------
CREATE TABLE news_items (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period      integer NOT NULL CHECK (period >= 1),   -- the quarter in which it is published
    day         integer NOT NULL CHECK (day BETWEEN 1 AND 90),
    outlet      text NOT NULL,
    kind        text NOT NULL,
    story       text NOT NULL,                          -- items about the same affair share a story
    importance  integer NOT NULL,
    headline    text NOT NULL CHECK (headline <> ''),
    body        text NOT NULL CHECK (body <> ''),
    tickers     text[] NOT NULL DEFAULT '{}',
    sectors     text[] NOT NULL DEFAULT '{}',
    locations   text[] NOT NULL DEFAULT '{}',
    facts       jsonb NOT NULL DEFAULT '{}',            -- the recorded figures the item was written from
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX news_items_by_time ON news_items (period DESC, day DESC, importance DESC);
CREATE INDEX news_items_by_kind ON news_items (kind, outlet, period DESC, day DESC, id DESC);
CREATE INDEX news_items_by_ticker ON news_items USING gin (tickers);
CREATE TRIGGER news_items_permanent BEFORE UPDATE OR DELETE ON news_items
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER news_items_no_truncate BEFORE TRUNCATE ON news_items
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
