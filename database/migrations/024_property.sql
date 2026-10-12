-- Stage 8: land, property, headquarters and the Auction House (owner, 12 October 2026).
--
--   districts            five in each city, each with a character (business, homes, shops, industry, farmland)
--   properties           buildings, small units and empty plots. Who owns them is in property_holdings
--                        (shares out of 10000, so several may own one together). A property company's
--                        buildings are part of its own business; anybody else's earn rent from tenants.
--   district_results     each quarter: a district's rent, price and how full its buildings are
--   property_results     each quarter: each property's value, rent, condition and tax
--   mortgages            loans from the banks against a property
--   auctions, auction_bids   the Auction House: live timed auctions. A bid's highest price (its limit) is
--                        never shown to anybody but the bidder; the cash behind it is held while it stands.
--   property_checks      an empire's desks' checks before it bids
--   headquarters         each empire's headquarters: its building, level, upkeep and condition

CREATE TABLE districts (
    id        integer PRIMARY KEY,
    city      text NOT NULL REFERENCES locations (name),
    name      text NOT NULL UNIQUE,
    kind      text NOT NULL CHECK (kind IN ('business', 'homes', 'shops', 'industry', 'farmland')),
    rent_bps  integer NOT NULL DEFAULT 10000,       -- rent against the start (prices included)
    occupancy_bps integer NOT NULL DEFAULT 9000,
    premium_bps   integer NOT NULL DEFAULT 0        -- how far prices stand above (or below) what rents justify: a bubble
);

CREATE TABLE properties (
    id            integer PRIMARY KEY,
    district_id   integer NOT NULL REFERENCES districts (id),
    kind          text NOT NULL CHECK (kind IN ('office', 'home', 'shop', 'warehouse', 'factory', 'farmland', 'land')),
    name          text NOT NULL,
    size_m2       integer NOT NULL CHECK (size_m2 > 0),
    base_rent     bigint NOT NULL CHECK (base_rent >= 0),          -- a quarter's rent at the start, when full
    land_value    bigint NOT NULL CHECK (land_value >= 0),         -- what the plot alone was worth at the start
    condition     smallint NOT NULL DEFAULT 90 CHECK (condition BETWEEN 0 AND 100),
    upkeep        boolean NOT NULL DEFAULT true,                   -- its owners keep it up each quarter
    title_flaw_bps integer NOT NULL DEFAULT 0,                     -- SECRET: the share a false seller does not truly own
    book_value    bigint NOT NULL DEFAULT 0,                       -- in a property company's books
    tax_owed      bigint NOT NULL DEFAULT 0,
    status        text NOT NULL DEFAULT 'standing' CHECK (status IN ('standing', 'plot', 'collapsed')),
    built_period  integer,
    UNIQUE (district_id, name)
);

CREATE TABLE property_holdings (
    property_id integer NOT NULL REFERENCES properties (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    share_bps   integer NOT NULL CHECK (share_bps BETWEEN 1 AND 10000),
    since_period integer NOT NULL,
    paid        bigint NOT NULL DEFAULT 0,                         -- what this owner paid for its share
    PRIMARY KEY (property_id, account_id)
);
CREATE INDEX property_holdings_by_account ON property_holdings (account_id);

CREATE TABLE property_company_base (                 -- what each property company's buildings earned at the start
    company_id uuid PRIMARY KEY REFERENCES companies (id),
    base_rent  bigint NOT NULL
);

CREATE TABLE district_results (
    period    integer NOT NULL,
    district_id integer NOT NULL REFERENCES districts (id),
    rent_bps  integer NOT NULL,
    occupancy_bps integer NOT NULL,
    premium_bps integer NOT NULL,
    price_bps integer NOT NULL,                      -- the price of property against the start
    sold      integer NOT NULL DEFAULT 0,
    sold_value bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (period, district_id)
);
CREATE TRIGGER district_results_permanent BEFORE UPDATE OR DELETE ON district_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE property_results (
    period      integer NOT NULL,
    property_id integer NOT NULL REFERENCES properties (id),
    value       bigint NOT NULL,
    rent_due    bigint NOT NULL,
    rent_paid   bigint NOT NULL,
    occupancy_bps integer NOT NULL,
    condition   smallint NOT NULL,
    tax         bigint NOT NULL,
    upkeep      bigint NOT NULL,
    PRIMARY KEY (period, property_id)
);
CREATE TRIGGER property_results_permanent BEFORE UPDATE OR DELETE ON property_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE mortgages (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id   integer NOT NULL REFERENCES properties (id),
    borrower      uuid NOT NULL REFERENCES ledger_accounts (id),
    bank_company_id uuid NOT NULL REFERENCES companies (id),
    principal     bigint NOT NULL CHECK (principal > 0),
    outstanding   bigint NOT NULL CHECK (outstanding >= 0),
    rate_bps      integer NOT NULL,
    taken_period  integer NOT NULL,
    term_quarters integer NOT NULL,
    missed        smallint NOT NULL DEFAULT 0,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaid', 'repossessed', 'shortfall')),
    at            timestamptz NOT NULL
);
CREATE INDEX mortgages_open ON mortgages (borrower) WHERE status IN ('open', 'shortfall');

CREATE TABLE auctions (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id   integer NOT NULL REFERENCES properties (id),
    seller        uuid NOT NULL REFERENCES ledger_accounts (id),
    reason        text NOT NULL CHECK (reason IN ('listing', 'owner', 'repossession', 'tax')),
    opens_at      timestamptz NOT NULL,
    ends_at       timestamptz NOT NULL,
    reserve       bigint NOT NULL CHECK (reserve >= 0),           -- SECRET: the lowest price the seller will take
    start_price   bigint NOT NULL CHECK (start_price > 0),
    fair          bigint NOT NULL CHECK (fair > 0),               -- what it was worth when the auction opened (public)
    price         bigint,                                         -- the leading price now
    leader        bigint,                                         -- the leading bid
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'sold', 'unsold', 'cancelled')),
    period        integer NOT NULL,
    settled_at    timestamptz
);
CREATE UNIQUE INDEX auctions_one_open ON auctions (property_id) WHERE status = 'open';

CREATE TABLE auction_bids (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auction_id    bigint NOT NULL REFERENCES auctions (id),
    bidder        uuid NOT NULL REFERENCES ledger_accounts (id),
    player_id     uuid REFERENCES players (id),                  -- who placed it (for an empire: its head)
    empire_id     bigint REFERENCES empires (id),
    limit_price   bigint NOT NULL CHECK (limit_price > 0),       -- SECRET to everybody but the bidder
    partner       uuid REFERENCES ledger_accounts (id),          -- a partner who pays part (and owns that part)
    partner_bps   integer NOT NULL DEFAULT 0 CHECK (partner_bps BETWEEN 0 AND 9000),
    mortgage_bank uuid REFERENCES companies (id),                -- a bank lending part of the price
    mortgage_bps  integer NOT NULL DEFAULT 0 CHECK (mortgage_bps BETWEEN 0 AND 8000),
    held          bigint NOT NULL DEFAULT 0,                     -- the bidder's own cash held while the bid stands
    partner_held  bigint NOT NULL DEFAULT 0,
    status        text NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'outbid', 'withdrawn', 'won', 'lost')),
    computer      boolean NOT NULL DEFAULT false,
    at            timestamptz NOT NULL
);
CREATE INDEX auction_bids_live ON auction_bids (auction_id) WHERE status = 'live';
CREATE TABLE auction_events (                  -- what everybody watching an auction sees: prices, never limits
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auction_id bigint NOT NULL REFERENCES auctions (id),
    at         timestamptz NOT NULL,
    price      bigint,
    words      text NOT NULL
);

CREATE TABLE property_checks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    auction_id  bigint NOT NULL REFERENCES auctions (id),
    step        text NOT NULL CHECK (step IN ('title', 'valuation', 'limit', 'money')),
    player_id   uuid REFERENCES players (id),
    answer      jsonb NOT NULL,
    at          timestamptz NOT NULL,
    UNIQUE (empire_id, auction_id, step)
);

CREATE TABLE headquarters (
    empire_id     bigint PRIMARY KEY REFERENCES empires (id),
    property_id   integer NOT NULL UNIQUE REFERENCES properties (id),
    level         smallint NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 120),
    spent         bigint NOT NULL DEFAULT 0,                     -- on its levels
    condition     smallint NOT NULL DEFAULT 100 CHECK (condition BETWEEN 0 AND 100),
    upkeep_approved boolean NOT NULL DEFAULT false,              -- the head approves its upkeep each quarter (or leaves it standing)
    upkeep_asked  boolean NOT NULL DEFAULT false,                -- the Risk Manager has asked for it
    warnings      smallint NOT NULL DEFAULT 0,
    collapsed_period integer,
    since         timestamptz NOT NULL
);

-- A bigger headquarters adds seats: more than two for a build.
ALTER TABLE empire_seats DROP CONSTRAINT IF EXISTS empire_seats_slot_check;
ALTER TABLE empire_seats ADD CONSTRAINT empire_seats_slot_check CHECK (slot BETWEEN 1 AND 6);
ALTER TABLE empire_seats ADD COLUMN hq_frozen boolean NOT NULL DEFAULT false; -- a seat above the twelve, frozen while its headquarters is down

-- A property company selling a building: its book value leaves the balance sheet.
ALTER TABLE company_asset_sales ALTER COLUMN asset_id DROP NOT NULL;
ALTER TABLE company_asset_sales ADD COLUMN property_id integer REFERENCES properties (id);

CREATE TABLE auction_partners (               -- a partner who agrees to pay part of a bid, and own that part
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auction_id  bigint NOT NULL REFERENCES auctions (id),
    bidder      uuid NOT NULL REFERENCES ledger_accounts (id),
    partner     uuid NOT NULL REFERENCES ledger_accounts (id),
    partner_bps integer NOT NULL CHECK (partner_bps BETWEEN 500 AND 9000),
    most        bigint NOT NULL CHECK (most > 0),                -- the highest price the partner goes to (SECRET)
    held        bigint NOT NULL DEFAULT 0,
    status      text NOT NULL DEFAULT 'asked' CHECK (status IN ('asked', 'agreed', 'refused', 'used', 'released')),
    at          timestamptz NOT NULL,
    UNIQUE (auction_id, bidder, partner)
);
