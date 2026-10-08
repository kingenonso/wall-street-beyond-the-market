-- Private equity stage, part 2B: the deal-making around buying and selling companies.
--
--   firms players found   audit firms, small banks, risk consultancies and advisory firms, each run by
--                         its founder from their seat in an empire (fees split 60/40 with the empire)
--   outside work          an empire sends one of its checks on a deal to a firm, for a fee
--   audits                a seller's accounts and assets audited before a sale; the auditor may refuse to sign
--   mandates              an advisory firm runs a sale for the seller: the pitch book, the price, a success fee
--   underwriting          an advisory firm stands behind a listing and buys what the public does not
--   restructuring         a banker's plan to put a failing company's loans on terms it can bear
--   takeover offers       an empire offers for a listed company's shares; others may counter-offer
--   stake building        buying a listed company's shares a little at each bell, up to a target
--   block trades          a block of listed shares sold from one empire to another, off the order book
--   truces, mergers, spin-offs between empires
--   theft inside an owned company, found by audits

ALTER TABLE ledger_accounts DROP CONSTRAINT ledger_accounts_kind_check;
ALTER TABLE ledger_accounts ADD CONSTRAINT ledger_accounts_kind_check CHECK (kind IN (
    'central_bank', 'government', 'prize_pool', 'npc_public', 'npc_investors', 'company', 'player', 'exchange', 'empire', 'fund',
    'escrow', 'firm'));

CREATE TABLE pro_firms (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('audit', 'bank', 'risk', 'advisory')),
    name        text NOT NULL UNIQUE CHECK (length(name) BETWEEN 3 AND 60),
    founder_id  uuid NOT NULL REFERENCES players (id),
    account_id  uuid NOT NULL UNIQUE REFERENCES ledger_accounts (id),   -- a bank's capital and loans; others hold nothing
    capital     bigint NOT NULL DEFAULT 0 CHECK (capital >= 0),        -- what the founder put in (a bank)
    reputation  integer NOT NULL DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),
    jobs_done   integer NOT NULL DEFAULT 0,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    founded_period integer NOT NULL,
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX pro_firms_one_each ON pro_firms (founder_id) WHERE status = 'open';

CREATE TABLE firm_jobs (                      -- work a firm does for a fee
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    firm_id     bigint NOT NULL REFERENCES pro_firms (id),
    kind        text NOT NULL CHECK (kind IN ('deal_check', 'audit', 'site_visit', 'mandate', 'restructuring')),
    client_account uuid NOT NULL REFERENCES ledger_accounts (id),       -- who pays
    client_empire_id bigint REFERENCES empires (id),
    company_id  uuid REFERENCES companies (id),
    process_id  bigint REFERENCES sale_processes (id),
    step_id     bigint REFERENCES deal_steps (id),
    fee         bigint NOT NULL CHECK (fee >= 0),                       -- fixed, or (a mandate) in hundredths of a percent of the price
    terms       jsonb,                                                  -- what it asks; `_truth` never leaves the server
    answers     jsonb,
    score       smallint,
    opinion     text CHECK (opinion IN ('clean', 'refused')),          -- an audit: signed clean, or the auditor refused to sign
    words       text,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'lapsed', 'cancelled')),
    period      integer NOT NULL,
    at          timestamptz NOT NULL,
    done_at     timestamptz
);
CREATE INDEX firm_jobs_by_firm ON firm_jobs (firm_id, status);
CREATE UNIQUE INDEX firm_jobs_one_step ON firm_jobs (step_id) WHERE status IN ('open', 'done');

ALTER TABLE deal_steps ADD COLUMN firm_id bigint REFERENCES pro_firms (id);          -- sent to an outside firm
ALTER TABLE sale_processes ADD COLUMN adviser_firm_id bigint REFERENCES pro_firms (id);
ALTER TABLE sale_processes ADD COLUMN pitch_bps integer NOT NULL DEFAULT 0;           -- a well-made pitch book lifts the computer-run bids

ALTER TABLE share_offers ADD COLUMN underwriter_firm_id bigint REFERENCES pro_firms (id);
ALTER TABLE share_offers ADD COLUMN underwriting_fee_bps integer NOT NULL DEFAULT 0;

ALTER TABLE takeovers ALTER COLUMN bidder_company_id DROP NOT NULL;
ALTER TABLE takeovers ADD COLUMN bidder_empire_id bigint REFERENCES empires (id);
ALTER TABLE takeovers ADD CONSTRAINT takeovers_one_bidder CHECK ((bidder_company_id IS NULL) <> (bidder_empire_id IS NULL));

CREATE TABLE stake_programmes (               -- an empire buying a listed company's shares a little at each bell
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id   bigint NOT NULL REFERENCES empires (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    target_bps  integer NOT NULL CHECK (target_bps BETWEEN 100 AND 2900),
    most_price  bigint NOT NULL CHECK (most_price > 0),
    set_by      uuid REFERENCES players (id),
    status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'stopped')),
    disclosed_bps integer NOT NULL DEFAULT 0,                           -- the last holding made public
    at          timestamptz NOT NULL
);
CREATE UNIQUE INDEX stake_programmes_one ON stake_programmes (empire_id, company_id) WHERE status = 'running';

CREATE TABLE block_trades (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    seller_empire_id bigint NOT NULL REFERENCES empires (id),
    buyer_empire_id bigint NOT NULL REFERENCES empires (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    shares      bigint NOT NULL CHECK (shares > 0),
    price       bigint NOT NULL CHECK (price > 0),                      -- kobo a share
    status      text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'done', 'refused', 'lapsed', 'withdrawn')),
    offered_by  uuid REFERENCES players (id),
    answered_by uuid REFERENCES players (id),
    at          timestamptz NOT NULL,
    done_at     timestamptz,
    CHECK (seller_empire_id <> buyer_empire_id)
);

CREATE TABLE empire_combinations (            -- a merger of two empires, or a spin-off of one into two
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('merger', 'spinoff')),
    empire_id   bigint NOT NULL REFERENCES empires (id),                -- a merger: the one that continues; a spin-off: the one splitting
    other_empire_id bigint REFERENCES empires (id),                     -- a merger: the one that joins it; a spin-off: the new one
    company_id  uuid REFERENCES companies (id),                         -- a spin-off: the company that goes
    new_name    text,
    new_head    uuid REFERENCES players (id),
    status      text NOT NULL DEFAULT 'voting' CHECK (status IN ('voting', 'done', 'refused', 'lapsed')),
    resolution_ids bigint[] NOT NULL DEFAULT '{}',
    words       text,
    period      integer NOT NULL,
    at          timestamptz NOT NULL
);

ALTER TABLE empires DROP CONSTRAINT IF EXISTS empires_status_check;
ALTER TABLE empires ADD CONSTRAINT empires_status_check CHECK (status IN ('forming', 'active', 'closed', 'merged'));

ALTER TABLE career_events DROP CONSTRAINT career_events_kind_check;
ALTER TABLE career_events ADD CONSTRAINT career_events_kind_check CHECK (kind IN (
    'build_chosen', 'hired', 'left_job', 'bank_chosen', 'level_up', 'review_opened', 'review_closed', 'demoted', 'fund_chosen',
    'saving_changed', 'retired', 'early_withdrawal', 'joined_empire', 'left_empire', 'sacked', 'theft_proved', 'founded_empire',
    'fund_opened', 'struck_off', 'rank_case', 'rank_passed', 'ceo', 'resigned', 'counter_offer',
    'promoted', 'poached', 'apprentice', 'contract', 'opinion', 'deal', 'deal_fee', 'rescue', 'firm'));

ALTER TABLE empire_audits DROP CONSTRAINT empire_audits_kind_check;
ALTER TABLE empire_audits ADD CONSTRAINT empire_audits_kind_check CHECK (kind IN ('accountant', 'staff', 'ai', 'report', 'firm'));
ALTER TABLE firm_jobs DROP CONSTRAINT firm_jobs_kind_check;
ALTER TABLE firm_jobs ADD CONSTRAINT firm_jobs_kind_check CHECK (kind IN ('deal_check', 'audit', 'mandate', 'restructuring', 'underwriting'));

CREATE TABLE bank_loan_offers (               -- a small bank's offer of a loan to an empire
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    firm_id     bigint NOT NULL REFERENCES pro_firms (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    amount      bigint NOT NULL CHECK (amount > 0),
    rate_bps    integer NOT NULL CHECK (rate_bps BETWEEN 1 AND 6000),
    quarters    integer NOT NULL CHECK (quarters BETWEEN 1 AND 20),
    status      text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'taken', 'refused', 'lapsed')),
    period      integer NOT NULL,
    at          timestamptz NOT NULL
);
CREATE INDEX bank_loan_offers_waiting ON bank_loan_offers (empire_id) WHERE status = 'offered';

CREATE TABLE stake_disclosures (              -- the last holding of a listed company each empire has made public (every 5%)
    empire_id   bigint NOT NULL REFERENCES empires (id),
    company_id  uuid NOT NULL REFERENCES companies (id),
    bps         integer NOT NULL,
    at          timestamptz NOT NULL,
    PRIMARY KEY (empire_id, company_id)
);

-- A takeover's defence: the Investment Banker of an empire holding part of the target writes it; if it holds up,
-- the board publishes what the company is worth and owners weigh the offer against it.
ALTER TABLE takeovers ADD COLUMN defence_empire_id bigint REFERENCES empires (id);
ALTER TABLE takeovers ADD COLUMN defence_by uuid REFERENCES players (id);
ALTER TABLE takeovers ADD COLUMN defence_terms jsonb;              -- `_truth` never leaves the server
ALTER TABLE takeovers ADD COLUMN defence_value bigint;             -- per share, once a defence holds up
ALTER TABLE takeovers ADD COLUMN topped bigint REFERENCES takeovers (id);   -- the offer this one beat

ALTER TABLE empire_books ADD COLUMN company_id uuid REFERENCES companies (id);   -- money taken out of a company the empire owns

ALTER TABLE holding_events DROP CONSTRAINT holding_events_kind_check;
ALTER TABLE holding_events ADD CONSTRAINT holding_events_kind_check CHECK (kind IN ('offer', 'conversion', 'takeover', 'block'));

ALTER TABLE empire_combinations ADD COLUMN worth_moved bigint NOT NULL DEFAULT 0;   -- what passed between the empires: not growth, in the league
