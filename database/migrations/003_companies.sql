-- Stage 2: the world, its companies and their accounts.

-- One row describing the world itself.
CREATE TABLE world_state (
    id                  boolean PRIMARY KEY DEFAULT true CHECK (id),   -- only one row can exist
    -- The moment the game calendar begins. Fixed when the world is created.
    world_start         timestamptz NOT NULL,
    -- Game quarters are numbered 1, 2, 3... from the start. 0 means none has closed yet.
    last_closed_period  integer NOT NULL DEFAULT 0 CHECK (last_closed_period >= 0),
    -- TEMPORARY STAND-IN (Stage 12 gives tax to the Government): company tax rate,
    -- in hundredths of a percent. 3000 = 30%.
    company_tax_bps     integer NOT NULL CHECK (company_tax_bps BETWEEN 0 AND 10000),
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- The calendar cannot be rewound, skipped forward or restarted: the start never
-- changes and quarters close one at a time, in order.
CREATE FUNCTION world_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RAISE EXCEPTION 'The world cannot be removed.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'world_is_permanent';
    END IF;
    IF NEW.world_start <> OLD.world_start OR NEW.created_at <> OLD.created_at
       OR NEW.last_closed_period NOT IN (OLD.last_closed_period, OLD.last_closed_period + 1) THEN
        RAISE EXCEPTION 'The calendar only moves forward, one quarter at a time.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'world_is_permanent';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER world_state_guard BEFORE UPDATE OR DELETE ON world_state
    FOR EACH ROW EXECUTE FUNCTION world_state_guard();
CREATE TRIGGER world_state_no_truncate BEFORE TRUNCATE ON world_state
    FOR EACH STATEMENT EXECUTE FUNCTION world_state_guard();

CREATE TABLE sectors (
    code        text PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    sort_order  integer NOT NULL
);

CREATE TABLE companies (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker        text NOT NULL UNIQUE CHECK (ticker ~ '^[A-Z]{3}$'),
    name          text NOT NULL UNIQUE,
    sector        text NOT NULL REFERENCES sectors (code),
    headquarters  text NOT NULL,
    account_id    uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),   -- where its cash is held
    share_asset   text NOT NULL UNIQUE REFERENCES assets (code),

    -- TEMPORARY STAND-IN (replaced in Stage 3 by real demand from households).
    -- How this company's sales and costs move each quarter. All rates are in
    -- hundredths of a percent: 400 = 4%.
    revenue_growth_bps  integer NOT NULL,
    season_bps          integer[] NOT NULL CHECK (cardinality(season_bps) = 4),  -- 10000 = an average quarter
    cost_of_sales_bps   integer NOT NULL CHECK (cost_of_sales_bps BETWEEN 0 AND 10000),
    opex_growth_bps     integer NOT NULL,
    depreciation_bps    integer NOT NULL CHECK (depreciation_bps BETWEEN 0 AND 10000),
    payout_bps          integer NOT NULL CHECK (payout_bps BETWEEN 0 AND 10000)
);

-- What a company owes: bank loans and bonds.
CREATE TABLE company_debts (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id             uuid NOT NULL REFERENCES companies (id),
    lender_account_id      uuid NOT NULL REFERENCES ledger_accounts (id),
    kind                   text NOT NULL CHECK (kind IN ('bank_loan', 'bond')),
    name                   text NOT NULL,
    original_principal     bigint NOT NULL CHECK (original_principal > 0),
    principal_outstanding  bigint NOT NULL CHECK (principal_outstanding >= 0),
    annual_rate_bps        integer NOT NULL CHECK (annual_rate_bps >= 0),
    start_period           integer NOT NULL,
    maturity_period        integer NOT NULL,     -- the quarter by which it must be fully repaid
    -- 'amortising': repaid a little every quarter. 'bullet': repaid all at once at the end.
    repayment              text NOT NULL CHECK (repayment IN ('amortising', 'bullet')),
    CHECK (principal_outstanding <= original_principal),
    CHECK (maturity_period > start_period)
);
CREATE INDEX company_debts_by_company ON company_debts (company_id);
CREATE INDEX company_debts_by_lender ON company_debts (lender_account_id);

-- Bills a company could not pay when they fell due. They stay owed until paid.
CREATE TABLE company_payables (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          uuid NOT NULL REFERENCES companies (id),
    payee_account_id    uuid NOT NULL REFERENCES ledger_accounts (id),
    kind                text NOT NULL,
    amount_outstanding  bigint NOT NULL CHECK (amount_outstanding >= 0),
    incurred_period     integer NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX company_payables_by_company ON company_payables (company_id);

-- ---------------------------------------------------------------------------
-- THE TRUE RECORD: what really happened in each company, each quarter.
-- Seen only by the server. Players never read this table. One row per company
-- per quarter, never changed afterwards. Period 0 is the opening position.
-- All amounts are whole kobo.
-- ---------------------------------------------------------------------------
CREATE TABLE company_results (
    company_id            uuid NOT NULL REFERENCES companies (id),
    period                integer NOT NULL CHECK (period >= 0),

    -- Income statement: what was earned and what it cost.
    revenue               bigint NOT NULL,
    interest_income       bigint NOT NULL,
    cost_of_sales         bigint NOT NULL,
    operating_expenses    bigint NOT NULL,
    depreciation          bigint NOT NULL,
    operating_profit      bigint NOT NULL,
    interest_expense      bigint NOT NULL,
    profit_before_tax     bigint NOT NULL,
    tax                   bigint NOT NULL,
    net_profit            bigint NOT NULL,

    -- Cash flow statement: where cash came from and went. Read from the ledger.
    cash_opening          bigint NOT NULL,
    cash_from_operations  bigint NOT NULL,
    cash_from_investing   bigint NOT NULL,
    cash_from_financing   bigint NOT NULL,
    cash_closing          bigint NOT NULL,
    capital_spending      bigint NOT NULL,
    debt_repaid           bigint NOT NULL,
    dividends_paid        bigint NOT NULL,

    -- Balance sheet: what it owns and what it owes at the end of the quarter.
    cash                  bigint NOT NULL,
    customer_loans        bigint NOT NULL,   -- banks: lending to the public (stand-in, fixed until Stage 3)
    loans_to_companies    bigint NOT NULL,   -- lending to other companies in this table
    fixed_assets          bigint NOT NULL,
    total_assets          bigint NOT NULL,
    borrowings            bigint NOT NULL,
    payables              bigint NOT NULL,
    customer_funds        bigint NOT NULL,   -- banks: deposits; insurers: reserves (stand-in, fixed until Stage 3)
    total_liabilities     bigint NOT NULL,
    share_capital         bigint NOT NULL,
    retained_earnings     bigint NOT NULL,
    total_equity          bigint NOT NULL,

    principal_overdue     bigint NOT NULL,   -- debt past its repayment date and still unpaid
    shares_in_issue       bigint NOT NULL,

    -- Carried forward to work out the next quarter (stand-in model).
    base_revenue          bigint NOT NULL,
    base_opex             bigint NOT NULL,

    -- Everything this company's account had received and paid, by reason, up to
    -- this moment. The next quarter's movements are the difference from here, so
    -- no movement is counted twice and none is missed, whenever it happened.
    ledger_totals         jsonb NOT NULL,

    -- The causes behind this quarter's figures, for the "Why?" record.
    drivers               jsonb NOT NULL,
    closed_at             timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (company_id, period),
    -- A balance sheet must balance, and cash must reconcile. Checked by the database.
    CHECK (total_assets = cash + customer_loans + loans_to_companies + fixed_assets),
    CHECK (total_liabilities = borrowings + payables + customer_funds),
    CHECK (total_equity = share_capital + retained_earnings),
    CHECK (total_assets = total_liabilities + total_equity),
    CHECK (cash = cash_closing),
    CHECK (cash_closing = cash_opening + cash_from_operations + cash_from_investing + cash_from_financing)
);

-- ---------------------------------------------------------------------------
-- THE REPORTED RECORD: what each company filed for the public to read.
-- Kept apart from the true record on purpose (design document, section 13).
-- Today every company reports honestly, so the two agree. From Stage 11 a
-- company can file figures that differ from the truth, and that gap is fraud.
-- A filing is never changed; a correction is filed as a new version.
-- ---------------------------------------------------------------------------
CREATE TABLE company_reports (
    company_id      uuid NOT NULL REFERENCES companies (id),
    period          integer NOT NULL CHECK (period >= 0),
    version         integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    figures         jsonb NOT NULL,        -- the statements, as filed
    credit_rating   text NOT NULL          -- worked out from the filed figures
                    CHECK (credit_rating IN ('AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'CCC', 'D')),
    rating_reasons  jsonb NOT NULL,
    filed_by        text NOT NULL,
    filed_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, period, version)
);

CREATE FUNCTION records_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'This record is permanent: % on % is not allowed.', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation', CONSTRAINT = 'record_is_permanent';
END;
$$;
CREATE TRIGGER company_results_permanent BEFORE UPDATE OR DELETE ON company_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER company_results_no_truncate BEFORE TRUNCATE ON company_results
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
-- A filing is stamped with the real time by the database, takes the next version
-- number in line, and can only be for a quarter that has ended (or is being closed).
CREATE FUNCTION company_reports_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    latest  integer;
    closed  integer;
BEGIN
    SELECT coalesce(max(version), 0) INTO latest FROM company_reports
     WHERE company_id = NEW.company_id AND period = NEW.period;
    SELECT last_closed_period INTO closed FROM world_state;
    IF NEW.version <> latest + 1 OR NEW.period > coalesce(closed, 0) + 1 THEN
        RAISE EXCEPTION 'A filing must be the next version, for a quarter that has ended.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'filing_in_order';
    END IF;
    NEW.filed_at := now();
    RETURN NEW;
END;
$$;
CREATE TRIGGER company_reports_check BEFORE INSERT ON company_reports
    FOR EACH ROW EXECUTE FUNCTION company_reports_check();

CREATE TRIGGER company_reports_permanent BEFORE UPDATE OR DELETE ON company_reports
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER company_reports_no_truncate BEFORE TRUNCATE ON company_reports
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();
