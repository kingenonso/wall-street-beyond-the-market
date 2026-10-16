-- The gap stage, Part 2: Stage 8's missing pieces. Zoning and rezoning, infrastructure, the twelve-step purchase and the
-- Land Registry, claims besides a bad title, development projects, hotels and malls, households' home loans, and
-- property funds.

-- Hotels and malls are kinds of building.
ALTER TABLE properties DROP CONSTRAINT IF EXISTS properties_kind_check;
ALTER TABLE properties ADD CONSTRAINT properties_kind_check
    CHECK (kind IN ('office', 'home', 'shop', 'warehouse', 'factory', 'farmland', 'land', 'hotel', 'mall'));

-- Zoning: what may stand on a plot. Every property has a zone.
ALTER TABLE properties ADD COLUMN zone text NOT NULL DEFAULT 'commercial'
    CHECK (zone IN ('residential', 'commercial', 'industrial', 'agricultural', 'resource', 'mixed'));
ALTER TABLE properties ADD COLUMN beside_project bigint;          -- land beside an infrastructure project
UPDATE properties p SET zone = CASE d.kind WHEN 'business' THEN 'commercial' WHEN 'homes' THEN 'residential' WHEN 'shops' THEN 'commercial'
                                            WHEN 'industry' THEN 'industrial' ELSE 'agricultural' END
  FROM districts d WHERE d.id = p.district_id;
-- The second plot of every business district may be built on for homes too, and so may the second of every shops district.
UPDATE properties p SET zone = 'mixed' FROM districts d WHERE d.id = p.district_id AND d.kind IN ('business', 'shops') AND p.name LIKE 'Plot 2,%';
-- Port Harcourt's farmland plots sit on oil and gas.
UPDATE properties p SET zone = 'resource' FROM districts d WHERE d.id = p.district_id AND d.kind = 'farmland' AND d.city = 'Port Harcourt'
   AND p.kind = 'land';
-- Hotels and malls: each business district's third big building is a hotel; each shops district's mall is a mall.
UPDATE properties p SET kind = 'hotel' FROM districts d WHERE d.id = p.district_id AND d.kind = 'business' AND p.kind = 'office'
   AND p.name LIKE '% Plaza';
UPDATE properties p SET kind = 'mall' FROM districts d WHERE d.id = p.district_id AND d.kind = 'shops' AND p.kind = 'shop'
   AND p.name LIKE '% Mall';

-- How hotels and malls are doing against the start: hotels follow the hospitality companies' sales, malls the city's shopping.
CREATE TABLE property_kind_index (
    kind     text PRIMARY KEY,
    bps      integer NOT NULL DEFAULT 10000
);
INSERT INTO property_kind_index (kind) VALUES ('hotel'), ('mall');

ALTER TABLE districts ADD COLUMN infra_bps integer NOT NULL DEFAULT 0;      -- what infrastructure nearby adds to its prices

-- Rezonings: by the planning office (by rule, until the Government stage), or asked for by an owner.
CREATE TABLE rezonings (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id  integer NOT NULL REFERENCES properties (id),
    from_zone    text NOT NULL,
    to_zone      text NOT NULL,
    asked_by     uuid REFERENCES ledger_accounts (id),             -- none: the planners did it themselves
    fee          bigint NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'asked' CHECK (status IN ('asked', 'granted', 'refused')),
    period       integer NOT NULL,
    decided_period integer,
    words        text,
    at           timestamptz NOT NULL
);
CREATE INDEX rezonings_waiting ON rezonings (status) WHERE status = 'asked';

-- Infrastructure: a road, a rail line or a port beside a district.
CREATE TABLE infrastructure_projects (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind          text NOT NULL CHECK (kind IN ('road', 'rail', 'port')),
    name          text NOT NULL,
    district_id   integer NOT NULL REFERENCES districts (id),
    announced_period integer NOT NULL,
    finish_period integer NOT NULL,
    uplift_bps    integer NOT NULL,                                  -- what it adds to the district's prices when done
    spent         bigint NOT NULL DEFAULT 0,
    status        text NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'done')),
    at            timestamptz NOT NULL
);

-- Claims on a property besides a flawed title. SECRET until a claims search finds them or they come to light.
CREATE TABLE property_claims (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id  integer NOT NULL REFERENCES properties (id),
    kind         text NOT NULL CHECK (kind IN ('old_loan', 'right_of_way', 'dispute')),
    amount       bigint NOT NULL DEFAULT 0,                          -- an old loan: what is owed on it; a dispute: what settles it
    cut_bps      integer NOT NULL DEFAULT 0,                         -- a right of way: what it takes off the value
    lender       uuid REFERENCES companies (id),                     -- an old loan: the bank it is owed to
    status       text NOT NULL DEFAULT 'hidden' CHECK (status IN ('hidden', 'known', 'settled', 'faded')),
    known_period integer,
    at           timestamptz NOT NULL
);
CREATE INDEX property_claims_by_property ON property_claims (property_id);
ALTER TABLE properties ADD COLUMN frozen boolean NOT NULL DEFAULT false;   -- a dispute: nothing may be done with it until settled
ALTER TABLE properties ADD COLUMN value_cut_bps integer NOT NULL DEFAULT 0;   -- a known right of way takes this off its value

-- Every property has its claims drawn once, from its number (so every world gets the same, and nobody can tell which).
INSERT INTO property_claims (property_id, kind, amount, cut_bps, status, at)
SELECT p.id, 'old_loan', 0, 0, 'hidden', now() FROM properties p WHERE (p.id::bigint * 7919 + 13) % 10000 < 500;
INSERT INTO property_claims (property_id, kind, amount, cut_bps, status, at)
SELECT p.id, 'right_of_way', 0, 1000, 'hidden', now() FROM properties p WHERE (p.id::bigint * 104729 + 71) % 10000 < 400;
INSERT INTO property_claims (property_id, kind, amount, cut_bps, status, at)
SELECT p.id, 'dispute', 0, 0, 'hidden', now() FROM properties p WHERE (p.id::bigint * 15485863 + 211) % 10000 < 300;

-- The Land Registry: every change of hands, however it happened.
CREATE TABLE land_register (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id  integer NOT NULL REFERENCES properties (id),
    how          text NOT NULL CHECK (how IN ('auction', 'private', 'leaseback', 'claim', 'fund')),
    price        bigint NOT NULL DEFAULT 0,
    fee          bigint NOT NULL DEFAULT 0,
    period       integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE INDEX land_register_by_property ON land_register (property_id);

-- A purchase outside the Auction House: twelve steps, from confirming the seller to handing over the keys.
CREATE TABLE property_sales (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id  integer NOT NULL REFERENCES properties (id),
    seller       uuid NOT NULL REFERENCES ledger_accounts (id),
    buyer        uuid NOT NULL REFERENCES ledger_accounts (id),
    price        bigint NOT NULL CHECK (price > 0),
    mortgage_bank uuid REFERENCES companies (id),
    mortgage     bigint NOT NULL DEFAULT 0,
    held         bigint NOT NULL DEFAULT 0,                          -- the buyer's money held from the contract until registration
    steps        jsonb NOT NULL DEFAULT '{}',
    consent_due  timestamptz,
    status       text NOT NULL DEFAULT 'offered'
                 CHECK (status IN ('offered', 'agreed', 'consent', 'contracted', 'done', 'declined', 'withdrawn', 'failed')),
    offered_by   uuid REFERENCES players (id),
    period       integer NOT NULL,
    at           timestamptz NOT NULL,
    done_at      timestamptz
);
CREATE UNIQUE INDEX property_sales_one_open ON property_sales (property_id)
    WHERE status IN ('offered', 'agreed', 'consent', 'contracted');

-- Development: a permit, a design and a budget; a construction loan paid out phase by phase; the work bought from the
-- cement, steel and building companies.
CREATE TABLE developments (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id  integer NOT NULL REFERENCES properties (id),
    owner        uuid NOT NULL REFERENCES ledger_accounts (id),
    kind         text NOT NULL,                                      -- what it will be
    budget       bigint NOT NULL CHECK (budget > 0),
    materials_bps integer NOT NULL DEFAULT 10000,                    -- what materials cost when the budget was set
    spent        bigint NOT NULL DEFAULT 0,
    phase        smallint NOT NULL DEFAULT 0,                        -- phases finished
    permit_due   timestamptz,
    permit_delayed boolean NOT NULL DEFAULT false,
    loan_bank    uuid REFERENCES companies (id),
    loan_most    bigint NOT NULL DEFAULT 0,
    loan_drawn   bigint NOT NULL DEFAULT 0,
    loan_rate_bps integer,
    status       text NOT NULL DEFAULT 'permit' CHECK (status IN ('permit', 'building', 'done', 'stopped')),
    then_what    text NOT NULL DEFAULT 'let' CHECK (then_what IN ('let', 'sell')),
    log          jsonb NOT NULL DEFAULT '[]',
    started_period integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE UNIQUE INDEX developments_one_a_plot ON developments (property_id) WHERE status IN ('permit', 'building');

-- Households' home loans, city by city and bank by bank (part of what households owe the banks).
CREATE TABLE home_loans (
    bank_company_id uuid NOT NULL REFERENCES companies (id),
    location     text NOT NULL REFERENCES locations (name),
    principal    bigint NOT NULL DEFAULT 0 CHECK (principal >= 0),
    PRIMARY KEY (bank_company_id, location)
);
INSERT INTO home_loans (bank_company_id, location, principal)
SELECT bank_company_id, location, principal * 2000 / 10000 FROM household_debts WHERE principal > 0;
CREATE TABLE home_loan_results (
    period       integer NOT NULL,
    location     text NOT NULL,
    lent         bigint NOT NULL,
    repaid       bigint NOT NULL,
    defaulted    bigint NOT NULL,
    recovered    bigint NOT NULL,
    repossessed  integer NOT NULL,
    book         bigint NOT NULL,
    rate_bps     integer NOT NULL,
    PRIMARY KEY (period, location)
);
-- What a bank lost on home loans households did not repay, counted in its next accounts.
CREATE TABLE bank_home_losses (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bank_company_id uuid NOT NULL REFERENCES companies (id),
    period       integer NOT NULL,
    amount       bigint NOT NULL CHECK (amount >= 0),
    counted_in   integer
);

-- Property funds: units bought and sold at the fund's value.
CREATE TABLE property_funds (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text NOT NULL UNIQUE,
    account_id   uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),
    manager      uuid REFERENCES players (id),                       -- none: run by the computer
    fee_bps      integer NOT NULL CHECK (fee_bps BETWEEN 0 AND 200),
    units        bigint NOT NULL DEFAULT 0 CHECK (units >= 0),
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    opened_period integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE UNIQUE INDEX property_funds_one_a_manager ON property_funds (manager) WHERE status = 'open';
CREATE TABLE property_fund_units (
    fund_id      bigint NOT NULL REFERENCES property_funds (id),
    account      uuid NOT NULL REFERENCES ledger_accounts (id),
    units        bigint NOT NULL CHECK (units >= 0),
    PRIMARY KEY (fund_id, account)
);
CREATE TABLE property_fund_results (
    period       integer NOT NULL,
    fund_id      bigint NOT NULL REFERENCES property_funds (id),
    value        bigint NOT NULL,
    units        bigint NOT NULL,
    fee          bigint NOT NULL,
    PRIMARY KEY (period, fund_id)
);

