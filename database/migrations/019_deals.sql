-- Private equity stage, part 2A: deals and private companies.
--
--   private companies   companies owned by their founders and not traded on the exchange
--   secrets             what a private company's papers do not say: found by digging, or learnt the hard way
--   sale processes      a company put up for sale, by sealed bids or by an auction the seller runs
--   deal files          an empire's working file on a company it may buy: confidentiality, the six-desk checks
--   bids                what an empire offers, how it pays (its cash, partners, a buyout loan) and who signed
--   deal terms          the clauses of the sale agreement, argued over clause by clause; the seller's promises
--   claims              a promise that turned out false, claimed against the seller
--   running             the dials of a company an empire controls, its assets, managers, routes and plans
--   trouble             pay pressure, rescue plans and administration
--   exits               a company sold, or listed on the exchange, and how the gain was shared

ALTER TABLE companies ADD COLUMN listed boolean NOT NULL DEFAULT true;
ALTER TABLE companies ADD COLUMN price_bps integer NOT NULL DEFAULT 10000 CHECK (price_bps BETWEEN 5000 AND 20000);  -- its prices against the usual
ALTER TABLE companies ADD COLUMN status text NOT NULL DEFAULT 'trading' CHECK (status IN ('trading', 'administration', 'wound_up'));

ALTER TABLE ledger_accounts DROP CONSTRAINT ledger_accounts_kind_check;
ALTER TABLE ledger_accounts ADD CONSTRAINT ledger_accounts_kind_check CHECK (kind IN (
    'central_bank', 'government', 'prize_pool', 'npc_public', 'npc_investors', 'company', 'player', 'exchange', 'empire', 'fund',
    'escrow'));

ALTER TABLE empire_debts DROP CONSTRAINT empire_debts_kind_check;
ALTER TABLE empire_debts ADD CONSTRAINT empire_debts_kind_check CHECK (kind IN ('loan', 'bond', 'buyout'));
ALTER TABLE empire_debts ADD COLUMN company_id uuid REFERENCES companies (id);          -- a buyout loan: secured on this company's shares
ALTER TABLE empire_debts ADD COLUMN covenants jsonb NOT NULL DEFAULT '{}';            -- {debt_x_most, cover_least} for a buyout loan

ALTER TABLE empire_tasks DROP CONSTRAINT empire_tasks_kind_check;
ALTER TABLE empire_tasks ADD CONSTRAINT empire_tasks_kind_check CHECK (kind IN ('investment', 'raise_money', 'rescue', 'defend', 'acquisition'));

-- What makes a private company itself. `secrets` never leaves the server: only what an empire has
-- found (deal_finds) is shown, and only to that empire.
CREATE TABLE private_profiles (
    company_id      uuid PRIMARY KEY REFERENCES companies (id),
    management      smallint NOT NULL CHECK (management BETWEEN 1 AND 5),     -- how well it is run
    appeared_period integer NOT NULL DEFAULT 0,                              -- a start-up appears later
    founded_by_note text,
    secrets         jsonb NOT NULL DEFAULT '[]',     -- [{code, kind, amount, bps, from_period, done}] : the truth
    labour_adj_bps  integer NOT NULL DEFAULT 0,      -- lasting changes from technology and plans (points of sales)
    opex_adj_bps    integer NOT NULL DEFAULT 0,      -- ...to running costs (a share of them)
    pull_adj_bps    integer NOT NULL DEFAULT 0,      -- ...to its pull on customers
    pay_index_bps   integer NOT NULL DEFAULT 10000,  -- the pay it gives, in the units of the world's wage index
    last_pull_bps   integer NOT NULL DEFAULT 10000,  -- last quarter's combined pull, to judge the demand its assets must serve
    morale_bps      integer NOT NULL DEFAULT 10000,
    route_base      bigint NOT NULL DEFAULT 0        -- an airline: its routes' pull when the world began
);

-- Who controls a company an empire bought (the largest holder among empires), and since when.
CREATE TABLE owned_companies (
    company_id  uuid PRIMARY KEY REFERENCES companies (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    bought_period integer NOT NULL,
    cost        bigint NOT NULL CHECK (cost >= 0),   -- what this empire paid for its part
    deal_id     bigint,
    since       timestamptz NOT NULL
);
CREATE INDEX owned_companies_by_empire ON owned_companies (empire_id);

CREATE TABLE sale_processes (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    seller_account uuid NOT NULL REFERENCES ledger_accounts (id),   -- whoever holds the shares on sale
    seller_empire_id bigint REFERENCES empires (id),                -- when an empire sells
    shares      bigint NOT NULL CHECK (shares > 0),                 -- the shares on sale
    mode        text NOT NULL CHECK (mode IN ('sealed', 'auction')),
    asking      bigint NOT NULL CHECK (asking > 0),                 -- the price the seller names for all of them
    reserve     bigint NOT NULL CHECK (reserve > 0),                -- below this it will not sell. Never shown.
    opened_period integer NOT NULL,
    closes_period integer NOT NULL,                             -- it is decided as this quarter closes
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'sold', 'failed', 'withdrawn')),
    highest     bigint,                                             -- an auction's highest bid, shown to all
    winner_bid  bigint,
    price       bigint,
    outcome     text,
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX sale_processes_one_open ON sale_processes (company_id) WHERE status = 'open';

CREATE TABLE deal_files (                    -- an empire's working file on a company on sale
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    process_id  bigint NOT NULL REFERENCES sale_processes (id),
    brought_by  uuid REFERENCES players (id),                   -- the Investment Banker who brought it
    nda_by      uuid REFERENCES players (id),                   -- who drafted the confidentiality agreement
    nda_at      timestamptz,
    terms_document_id bigint REFERENCES empire_documents (id),  -- the sale agreement the seller sent, read by Legal Counsel
    valuation   bigint,                                         -- the banker's figure
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'won', 'lost', 'dropped')),
    at          timestamptz NOT NULL,
    UNIQUE (empire_id, process_id)
);

CREATE TABLE deal_steps (                    -- the six-desk chain of checks on a company
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id     bigint NOT NULL REFERENCES deal_files (id),
    step        text NOT NULL CHECK (step IN ('background', 'accounts', 'valuation', 'stress', 'legal', 'fairness')),
    build       text NOT NULL,
    terms       jsonb,                       -- what it asks; `_truth` never leaves the server
    assigned_to uuid REFERENCES players (id),
    answers     jsonb,
    score       smallint,
    found       jsonb NOT NULL DEFAULT '[]',  -- what the check turned up, in words
    by_staff    boolean NOT NULL DEFAULT false,
    done_by     uuid REFERENCES players (id),
    status      text NOT NULL DEFAULT 'due' CHECK (status IN ('due', 'done')),
    done_at     timestamptz,
    UNIQUE (file_id, step)
);

CREATE TABLE deal_finds (                    -- secrets an empire has found, by digging or the hard way
    empire_id   bigint NOT NULL REFERENCES empires (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    code        text NOT NULL,
    how         text NOT NULL,
    at          timestamptz NOT NULL,
    PRIMARY KEY (empire_id, company_id, code)
);

CREATE TABLE deal_bids (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    process_id  bigint NOT NULL REFERENCES sale_processes (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    file_id     bigint REFERENCES deal_files (id),
    amount      bigint NOT NULL CHECK (amount > 0),              -- the price offered, before clause charges
    clause_charge bigint NOT NULL DEFAULT 0,                     -- what the seller adds for the clauses struck or added
    equity      bigint NOT NULL DEFAULT 0,                       -- from the empire's own cash
    loan        bigint NOT NULL DEFAULT 0,                       -- a buyout loan, secured on the company
    lender_account uuid REFERENCES ledger_accounts (id),
    loan_rate_bps integer,
    covenants   jsonb NOT NULL DEFAULT '{}',
    held        bigint NOT NULL DEFAULT 0,                       -- the empire's cash held in escrow while the bid stands
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'live', 'won', 'lost', 'withdrawn', 'refused')),
    approval_id bigint REFERENCES empire_approvals (id),
    signed_by   jsonb NOT NULL DEFAULT '{}',                     -- {banker, accountant, risk_manager, head}: who answers for it
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX deal_bids_one_standing ON deal_bids (process_id, empire_id) WHERE status IN ('pending', 'live');

CREATE TABLE deal_partners (                 -- co-investors in a bid: other empires or players, each owning a stated share
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bid_id      bigint NOT NULL REFERENCES deal_bids (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    empire_id   bigint REFERENCES empires (id),
    player_id   uuid REFERENCES players (id),
    amount      bigint NOT NULL CHECK (amount > 0),
    status      text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited', 'pledged', 'declined', 'used', 'returned')),
    at          timestamptz NOT NULL,
    UNIQUE (bid_id, account_id)
);

CREATE TABLE deal_terms (                    -- the sale agreement, clause by clause
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    process_id  bigint NOT NULL REFERENCES sale_processes (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),       -- the buyer's side
    code        text NOT NULL,
    status      text NOT NULL CHECK (status IN ('in', 'struck', 'asked', 'refused', 'agreed')),
    charge_bps  integer NOT NULL DEFAULT 0,                    -- what the other side charges for the change, of the price
    by_player   uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    UNIQUE (process_id, empire_id, code)
);

CREATE TABLE deals (                         -- a purchase completed
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    process_id  bigint NOT NULL REFERENCES sale_processes (id),
    bid_id      bigint NOT NULL REFERENCES deal_bids (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    seller_account uuid NOT NULL REFERENCES ledger_accounts (id),
    price       bigint NOT NULL,
    shares      bigint NOT NULL,
    escrow_account uuid REFERENCES ledger_accounts (id),
    escrow      bigint NOT NULL DEFAULT 0,                     -- held back from the seller against claims
    escrow_until integer,                                      -- the quarter whose close releases it
    terms       jsonb NOT NULL DEFAULT '{}',                   -- the clauses in force: {code: true}
    period      integer NOT NULL,
    status      text NOT NULL DEFAULT 'held' CHECK (status IN ('held', 'exited', 'failed')),
    at          timestamptz NOT NULL
);

CREATE TABLE deal_claims (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deal_id     bigint NOT NULL REFERENCES deals (id),
    code        text NOT NULL,
    amount      bigint NOT NULL CHECK (amount >= 0),
    paid        bigint NOT NULL DEFAULT 0,
    status      text NOT NULL CHECK (status IN ('paid', 'refused')),
    words       text NOT NULL,
    by_player   uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    UNIQUE (deal_id, code)
);

CREATE TABLE company_dials (                 -- what the controlling empire set for a quarter
    company_id  uuid NOT NULL REFERENCES companies (id),
    period      integer NOT NULL,
    price_bps   integer NOT NULL CHECK (price_bps BETWEEN 7000 AND 14000),
    staff_bps   integer NOT NULL CHECK (staff_bps BETWEEN 7000 AND 13000),
    pay_rise_bps integer NOT NULL DEFAULT 0 CHECK (pay_rise_bps BETWEEN 0 AND 3000),
    marketing   bigint NOT NULL DEFAULT 0 CHECK (marketing >= 0),
    technology  bigint NOT NULL DEFAULT 0 CHECK (technology >= 0),
    maintenance_bps integer NOT NULL DEFAULT 10000 CHECK (maintenance_bps BETWEEN 0 AND 20000),
    payout_bps  integer NOT NULL CHECK (payout_bps BETWEEN 0 AND 10000),
    borrow      bigint NOT NULL DEFAULT 0 CHECK (borrow >= 0),
    buy_assets  smallint NOT NULL DEFAULT 0 CHECK (buy_assets BETWEEN 0 AND 10),
    set_by      uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    PRIMARY KEY (company_id, period)
);

CREATE TABLE company_assets (                -- planes, hangars, hotels, vessels, plant: bought, kept up, sold, worn out
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    kind        text NOT NULL,
    name        text NOT NULL,
    base        text,                                     -- the city it works from
    cost        bigint NOT NULL CHECK (cost > 0),
    capacity    bigint NOT NULL CHECK (capacity >= 0),    -- sales it can serve in a quarter, in kobo, when in good order
    condition_bps integer NOT NULL CHECK (condition_bps BETWEEN 0 AND 10000),
    stated_bps  integer,                                  -- what the seller's papers say of its condition
    life_quarters integer NOT NULL CHECK (life_quarters > 0),
    age_quarters integer NOT NULL DEFAULT 0,
    route_id    bigint,                                   -- a plane: the route it flies
    status      text NOT NULL DEFAULT 'working' CHECK (status IN ('working', 'grounded', 'sold', 'scrapped')),
    bought_period integer NOT NULL,
    ended_period integer
);
CREATE INDEX company_assets_by_company ON company_assets (company_id) WHERE status IN ('working', 'grounded');

CREATE TABLE company_asset_sales (          -- an asset sold: its book value leaves the balance sheet in that quarter's close
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    asset_id    bigint NOT NULL REFERENCES company_assets (id),
    period      integer NOT NULL,
    book        bigint NOT NULL CHECK (book >= 0),
    proceeds    bigint NOT NULL CHECK (proceeds >= 0),
    at          timestamptz NOT NULL
);

CREATE TABLE company_managers (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    name        text NOT NULL,
    quality     smallint NOT NULL CHECK (quality BETWEEN 1 AND 5),
    pay         bigint NOT NULL CHECK (pay >= 0),            -- a quarter
    hired_period integer NOT NULL,
    left_period integer
);
CREATE UNIQUE INDEX company_managers_one ON company_managers (company_id) WHERE left_period IS NULL;

CREATE TABLE airline_routes (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    city_a      text NOT NULL,
    city_b      text NOT NULL,
    fare_bps    integer NOT NULL DEFAULT 10000 CHECK (fare_bps BETWEEN 6000 AND 16000),
    opened_period integer NOT NULL,
    closed_period integer,
    CHECK (city_a < city_b)
);
CREATE UNIQUE INDEX airline_routes_one ON airline_routes (company_id, city_a, city_b) WHERE closed_period IS NULL;

CREATE TABLE company_plans (                 -- the 100-day plan after a purchase, and a company doctor's rescue
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    empire_id   bigint REFERENCES empires (id),
    kind        text NOT NULL CHECK (kind IN ('hundred_days', 'rescue')),
    code        text NOT NULL,
    cost        bigint NOT NULL DEFAULT 0,
    fee         bigint NOT NULL DEFAULT 0,               -- a rescue: paid to the doctor only if it works
    fee_paid    boolean NOT NULL DEFAULT false,          -- ...in the company's next close
    doctor_id   uuid REFERENCES players (id),
    chance_bps  integer NOT NULL DEFAULT 10000,
    started_period integer NOT NULL,
    due_period  integer NOT NULL,
    status      text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'running', 'done', 'failed', 'refused')),
    outcome     text,
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX company_plans_once ON company_plans (company_id, kind, code) WHERE status IN ('proposed', 'running');

CREATE TABLE administrations (               -- a company that could not pay its way, wound up in order
    company_id  uuid PRIMARY KEY REFERENCES companies (id),
    started_period integer NOT NULL,
    ended_period integer,
    raised      bigint NOT NULL DEFAULT 0,
    paid        jsonb NOT NULL DEFAULT '[]',              -- [{who, rank, owed, paid}] in the order paid
    words       text
);

CREATE TABLE deal_exits (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES companies (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    kind        text NOT NULL CHECK (kind IN ('to_empire', 'to_buyer', 'listing', 'administration')),
    proceeds    bigint NOT NULL,
    cost        bigint NOT NULL,
    gain        bigint NOT NULL,
    fees        jsonb NOT NULL DEFAULT '[]',
    period      integer NOT NULL,
    at          timestamptz NOT NULL
);

ALTER TABLE career_events DROP CONSTRAINT career_events_kind_check;
ALTER TABLE career_events ADD CONSTRAINT career_events_kind_check CHECK (kind IN (
    'build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up', 'review_opened', 'review_closed', 'demoted', 'fund_chosen',
    'saving_changed', 'retired', 'early_withdrawal', 'joined_empire', 'left_empire', 'sacked', 'theft_proved', 'founded_empire',
    'fund_opened', 'struck_off', 'rank_case', 'rank_passed', 'ceo', 'resigned', 'counter_offer',
    'promoted', 'poached', 'apprentice', 'contract', 'opinion', 'deal', 'deal_fee', 'rescue'));
