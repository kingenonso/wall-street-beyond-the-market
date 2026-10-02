-- Stage 3, Part A: households, wages, spending, companies buying from each
-- other, and head offices that matter (design document, sections 4, 10 and 11).
--
-- The single stand-in account for "the public" is gone. In its place are the
-- households of each of the five locations, who earn wages and pensions and
-- spend them at the companies.

CREATE TABLE locations (
    name              text PRIMARY KEY,
    sort_order        integer NOT NULL,
    -- This location's share of the country's people, in hundredths of a percent.
    population_bps    integer NOT NULL CHECK (population_bps BETWEEN 1 AND 10000),
    -- What it costs to run a business here against the national average (10000).
    running_cost_bps  integer NOT NULL CHECK (running_cost_bps BETWEEN 1000 AND 30000),
    -- What one worker here is paid in a quarter, in kobo.
    quarterly_wage    bigint NOT NULL CHECK (quarterly_wage > 0)
);

CREATE TABLE households (
    location                 text PRIMARY KEY REFERENCES locations (name),
    account_id               uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),
    -- How households decide what to spend each quarter: this share of what they
    -- earned last quarter, plus this share of their savings.
    spend_from_income_bps    integer NOT NULL CHECK (spend_from_income_bps BETWEEN 0 AND 10000),
    spend_from_savings_bps   integer NOT NULL CHECK (spend_from_savings_bps BETWEEN 0 AND 10000)
);

-- What each kind of company buys from other kinds, as a share of its own sales.
CREATE TABLE sector_inputs (
    buyer     text NOT NULL REFERENCES sectors (code),
    supplier  text NOT NULL REFERENCES sectors (code),
    bps       integer NOT NULL CHECK (bps BETWEEN 1 AND 10000),
    PRIMARY KEY (buyer, supplier)
);

-- Where spending goes, by sector. Only the proportions between sectors matter.
CREATE TABLE sector_demand (
    sector          text PRIMARY KEY REFERENCES sectors (code),
    household_bps   bigint NOT NULL CHECK (household_bps >= 0),    -- of every naira households spend
    government_bps  integer NOT NULL CHECK (government_bps >= 0),  -- of every naira the Government buys
    investment_bps  integer NOT NULL CHECK (investment_bps >= 0)   -- of every naira companies spend on buildings and machines
);

-- What happened to each location's households each quarter. Never changed afterwards.
CREATE TABLE household_results (
    location    text NOT NULL REFERENCES locations (name),
    period      integer NOT NULL CHECK (period >= 0),
    wages       bigint NOT NULL,      -- paid by companies
    government  bigint NOT NULL,      -- public-sector pay
    pensions    bigint NOT NULL,
    income      bigint NOT NULL,      -- everything received this quarter
    spending    bigint NOT NULL,      -- everything spent at companies this quarter
    cash        bigint NOT NULL,      -- savings at the end of the quarter
    jobs        bigint NOT NULL,      -- people employed by the companies
    closed_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (location, period)
);
CREATE TRIGGER household_results_permanent BEFORE UPDATE OR DELETE ON household_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER household_results_no_truncate BEFORE TRUNCATE ON household_results
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- Each company: what its location does to its running costs, the share of its
-- sales it aims to spend on running costs, and the share that goes on direct labour.
ALTER TABLE companies ADD COLUMN location_cost_bps integer NOT NULL DEFAULT 10000;
ALTER TABLE companies ADD COLUMN opex_bps integer NOT NULL DEFAULT 0 CHECK (opex_bps BETWEEN 0 AND 20000);
ALTER TABLE companies ADD COLUMN labour_bps integer NOT NULL DEFAULT 0 CHECK (labour_bps BETWEEN 0 AND 10000);

ALTER TABLE company_results ADD COLUMN staff bigint NOT NULL DEFAULT 0;
ALTER TABLE company_results ADD COLUMN wages bigint NOT NULL DEFAULT 0;
ALTER TABLE company_results ADD COLUMN sales_households bigint NOT NULL DEFAULT 0;
ALTER TABLE company_results ADD COLUMN sales_business bigint NOT NULL DEFAULT 0;
ALTER TABLE company_results ADD COLUMN sales_government bigint NOT NULL DEFAULT 0;

CREATE INDEX ledger_transactions_by_period ON ledger_transactions (period);
