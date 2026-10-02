-- Stage 4, Part B: companies and the Government using the market (design document, section 11).
-- Bonds and Government bills, share offers (a first sale to the public, a later sale, a
-- rights issue), share splits, shareholder votes, takeovers and what follows them, and
-- the starting grant paid in parts.

-- ---------------------------------------------------------------------------
-- Bonds are a third kind of asset beside naira and shares. One unit is one bond.
-- ---------------------------------------------------------------------------
ALTER TABLE assets DROP CONSTRAINT assets_code_check;
ALTER TABLE assets ADD CONSTRAINT assets_code_check CHECK (code ~ '^([A-Z]{3}|SHR-[A-Z]{3}|BND-[A-Z0-9]{3,12})$');
ALTER TABLE assets DROP CONSTRAINT assets_kind_check;
ALTER TABLE assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('currency', 'share', 'bond'));
ALTER TABLE assets DROP CONSTRAINT assets_unit_check;
ALTER TABLE assets ADD CONSTRAINT assets_unit_check CHECK (unit IN ('kobo', 'share', 'bond'));

-- What may come into existence, and why. As before, with two additions:
--   * a bond issue: only for bonds, never for money or shares;
--   * a share split: only for shares.
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
            OR (reason = 'central_bank_lending' AND asset_kind = 'currency')
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

CREATE TABLE bonds (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset              text NOT NULL UNIQUE REFERENCES assets (code),
    name               text NOT NULL,
    issuer             text NOT NULL CHECK (issuer IN ('government', 'company')),
    company_id         uuid REFERENCES companies (id),
    debt_id            uuid UNIQUE REFERENCES company_debts (id),     -- a company's bond is one of its debts
    kind               text NOT NULL CHECK (kind IN ('bill', 'fixed', 'floating', 'inflation_linked', 'convertible', 'project')),
    face               bigint NOT NULL CHECK (face > 0),               -- kobo repaid for each bond at the end
    -- Yearly interest, in hundredths of a percent of the face value. For a floating-rate
    -- bond it is what is paid on top of the Central Bank's rate; for an inflation-linked
    -- bond it is paid on a face value that rises with prices; a bill pays none.
    coupon_bps         integer NOT NULL CHECK (coupon_bps >= 0),
    issued_period      integer NOT NULL CHECK (issued_period >= 0),
    maturity_period    integer NOT NULL,
    issue_index_bps    bigint,                                          -- the price index when an inflation-linked bond was issued
    conversion_shares  integer CHECK (conversion_shares > 0),           -- shares given for each convertible bond
    project            text,                                            -- what a project bond pays for
    green              boolean NOT NULL DEFAULT false,
    high_yield         boolean NOT NULL DEFAULT false,                  -- issued by a company rated below BBB
    redeemed_period    integer,                                         -- set once it has been repaid in full
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK ((issuer = 'company') = (company_id IS NOT NULL)),
    CHECK (maturity_period > issued_period),
    CHECK ((kind = 'convertible') = (conversion_shares IS NOT NULL))
);
CREATE INDEX bonds_by_company ON bonds (company_id);

-- Every purchase and sale at the bond desk. Permanent.
CREATE TABLE bond_trades (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bond_id             uuid NOT NULL REFERENCES bonds (id),
    account_id          uuid NOT NULL REFERENCES ledger_accounts (id),
    side                text NOT NULL CHECK (side IN ('buy', 'sell')),
    units               bigint NOT NULL CHECK (units > 0),
    price               bigint NOT NULL CHECK (price > 0),             -- kobo for each bond
    counterparty        uuid NOT NULL REFERENCES ledger_accounts (id),
    session_date        date NOT NULL,
    ledger_transaction  uuid NOT NULL REFERENCES ledger_transactions (id),
    traded_at           timestamptz NOT NULL
);
CREATE INDEX bond_trades_by_bond ON bond_trades (bond_id, session_date);
CREATE INDEX bond_trades_by_account ON bond_trades (account_id, id);
CREATE TRIGGER bond_trades_permanent BEFORE UPDATE OR DELETE ON bond_trades
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER bond_trades_no_truncate BEFORE TRUNCATE ON bond_trades
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- A holder's request to swap convertible bonds for shares. The bonds are held from the
-- moment of asking; the swap is made when the quarter closes.
CREATE TABLE bond_conversions (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bond_id       uuid NOT NULL REFERENCES bonds (id),
    account_id    uuid NOT NULL REFERENCES ledger_accounts (id),
    units         bigint NOT NULL CHECK (units > 0),
    status        text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'done', 'cancelled')),
    period        integer,                    -- the quarter whose close made the swap
    shares        bigint,
    face_value    bigint,                     -- kobo of debt that became shares
    requested_at  timestamptz NOT NULL,
    closed_at     timestamptz
);
CREATE INDEX bond_conversions_waiting ON bond_conversions (bond_id) WHERE status = 'waiting';

-- ---------------------------------------------------------------------------
-- A company's accounts: shares it owns in other companies, after a takeover.
-- ---------------------------------------------------------------------------
ALTER TABLE company_results ADD COLUMN investments bigint NOT NULL DEFAULT 0 CHECK (investments >= 0);
ALTER TABLE company_results DROP CONSTRAINT company_results_check;
ALTER TABLE company_results ADD CONSTRAINT company_results_check
    CHECK (total_assets = cash + customer_loans + loans_to_companies + fixed_assets + investments);

-- ---------------------------------------------------------------------------
-- Shareholder votes. Votes follow shares held when the vote is counted.
-- ---------------------------------------------------------------------------
CREATE TABLE company_votes (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id     uuid NOT NULL REFERENCES companies (id),
    subject        text NOT NULL CHECK (subject IN ('rights_issue', 'share_offer', 'share_split', 'takeover')),
    question       text NOT NULL CHECK (question <> ''),
    explanation    text NOT NULL,
    board          text NOT NULL CHECK (board IN ('for', 'against')),      -- what the board recommends
    detail         jsonb NOT NULL DEFAULT '{}',
    opens_period   integer NOT NULL,          -- announced as this quarter closed
    closes_period  integer NOT NULL,          -- counted as this quarter closes
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'passed', 'failed')),
    votes_for      bigint,
    votes_against  bigint,
    tally          jsonb,                     -- how each kind of owner voted, once counted
    created_at     timestamptz NOT NULL DEFAULT now(),
    closed_at      timestamptz,
    CHECK (closes_period > opens_period)
);
CREATE INDEX company_votes_open ON company_votes (company_id) WHERE status = 'open';

CREATE TABLE vote_ballots (
    vote_id     bigint NOT NULL REFERENCES company_votes (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    choice      text NOT NULL CHECK (choice IN ('for', 'against')),
    cast_at     timestamptz NOT NULL,
    PRIMARY KEY (vote_id, account_id)
);

-- ---------------------------------------------------------------------------
-- Share offers: a company selling new shares.
--   ipo      its first sale to the public; the share is then listed on the exchange
--   public   a later sale to anybody
--   rights   offered to existing owners first, in proportion to what they hold
-- ---------------------------------------------------------------------------
CREATE TABLE share_offers (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id     uuid NOT NULL REFERENCES companies (id),
    kind           text NOT NULL CHECK (kind IN ('ipo', 'public', 'rights')),
    price          bigint NOT NULL CHECK (price > 0),          -- kobo for each new share
    shares         bigint NOT NULL CHECK (shares > 0),         -- new shares on offer
    rights_new     integer CHECK (rights_new > 0),             -- a rights issue: this many new shares...
    rights_held    integer CHECK (rights_held > 0),            -- ...for every this many held
    reason         text NOT NULL,
    opens_period   integer NOT NULL,
    closes_period  integer NOT NULL,
    vote_id        bigint REFERENCES company_votes (id),       -- it goes ahead only if this vote passes
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'withdrawn')),
    shares_sold    bigint,
    raised         bigint,                                     -- kobo
    outcome        text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    closed_at      timestamptz,
    CHECK ((kind = 'rights') = (rights_new IS NOT NULL AND rights_held IS NOT NULL)),
    CHECK (closes_period > opens_period)
);
CREATE UNIQUE INDEX share_offers_one_open ON share_offers (company_id) WHERE status = 'open';

-- What each account has asked for. The cash is held from the moment of asking.
CREATE TABLE offer_subscriptions (
    offer_id    bigint NOT NULL REFERENCES share_offers (id),
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    shares      bigint NOT NULL CHECK (shares >= 0),           -- how many it asked for
    held        bigint NOT NULL CHECK (held >= 0),             -- kobo held for them
    allotted    bigint,                                        -- how many it was given, once the offer closed
    updated_at  timestamptz NOT NULL,
    PRIMARY KEY (offer_id, account_id)
);

-- ---------------------------------------------------------------------------
-- Takeovers: one company offering to buy another's shares from their owners.
-- ---------------------------------------------------------------------------
CREATE TABLE takeovers (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bidder_company_id  uuid NOT NULL REFERENCES companies (id),
    target_company_id  uuid NOT NULL REFERENCES companies (id),
    price              bigint NOT NULL CHECK (price > 0),       -- kobo offered for each share
    shares_sought      bigint NOT NULL CHECK (shares_sought > 0),
    hostile            boolean NOT NULL,                        -- the target's board rejected it
    premium_bps        integer NOT NULL,
    reserved           bigint NOT NULL CHECK (reserved >= 0),   -- the bidder's cash, held until the offer closes
    opens_period       integer NOT NULL,
    closes_period      integer NOT NULL,
    vote_id            bigint REFERENCES company_votes (id),    -- the bidder's own shareholders, for a large purchase
    status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'won', 'failed')),
    accepted           bigint,                                  -- shares whose owners accepted
    bought             bigint,
    paid               bigint,
    outcome            text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    closed_at          timestamptz,
    CHECK (bidder_company_id <> target_company_id),
    CHECK (closes_period > opens_period)
);
CREATE UNIQUE INDEX takeovers_one_open_per_target ON takeovers (target_company_id) WHERE status = 'open';

-- Shares a player has offered to the bidder. They are held from the moment of offering.
CREATE TABLE takeover_tenders (
    takeover_id  bigint NOT NULL REFERENCES takeovers (id),
    account_id   uuid NOT NULL REFERENCES ledger_accounts (id),
    shares       bigint NOT NULL CHECK (shares >= 0),
    updated_at   timestamptz NOT NULL,
    PRIMARY KEY (takeover_id, account_id)
);

-- After a takeover the two businesses are joined up. The planned savings can succeed or
-- fail; what happened each quarter is kept here.
CREATE TABLE integrations (
    takeover_id        bigint PRIMARY KEY REFERENCES takeovers (id),
    bidder_company_id  uuid NOT NULL REFERENCES companies (id),
    target_company_id  uuid NOT NULL REFERENCES companies (id),
    start_period       integer NOT NULL,          -- the first quarter it affects
    quarters           integer NOT NULL CHECK (quarters > 0),
    planned_saving_bps integer NOT NULL CHECK (planned_saving_bps >= 0)   -- of the target's sales, a quarter, once complete
);
CREATE TABLE integration_results (
    takeover_id  bigint NOT NULL REFERENCES integrations (takeover_id),
    period       integer NOT NULL,
    cost_bps     integer NOT NULL,                -- change in the target's costs, as a share of its sales (below zero: a saving)
    pull_bps     integer NOT NULL,                -- change in its hold on its customers
    notes        jsonb NOT NULL,
    PRIMARY KEY (takeover_id, period)
);
CREATE TRIGGER integration_results_permanent BEFORE UPDATE OR DELETE ON integration_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER integration_results_no_truncate BEFORE TRUNCATE ON integration_results
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- Notices from the exchange: every offer, vote, split, bond issue and takeover, as it
-- is announced and as it ends. Permanent.
-- ---------------------------------------------------------------------------
CREATE TABLE market_notices (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period      integer NOT NULL,              -- the quarter that had just closed when it was posted
    company_id  uuid REFERENCES companies (id),
    kind        text NOT NULL CHECK (kind <> ''),
    title       text NOT NULL CHECK (title <> ''),
    body        text NOT NULL,
    posted_at   timestamptz NOT NULL
);
CREATE INDEX market_notices_by_company ON market_notices (company_id, id DESC);
CREATE TRIGGER market_notices_permanent BEFORE UPDATE OR DELETE ON market_notices
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
CREATE TRIGGER market_notices_no_truncate BEFORE TRUNCATE ON market_notices
    FOR EACH STATEMENT EXECUTE FUNCTION records_forbid_change();

-- ---------------------------------------------------------------------------
-- The starting grant is paid in parts: some on joining, the rest as the player does
-- real things. One row for each part a player has earned.
-- ---------------------------------------------------------------------------
CREATE TABLE grant_steps (
    player_id  uuid NOT NULL REFERENCES players (id),
    step       text NOT NULL CHECK (step IN ('first_trade', 'held_through_results', 'lent_to_government', 'took_part')),
    earned_at  timestamptz NOT NULL,
    paid_at    timestamptz,
    PRIMARY KEY (player_id, step)
);
-- The database itself allows each part to be paid once to each account, whatever the server does.
CREATE UNIQUE INDEX ledger_one_grant_step ON ledger_transactions (reference) WHERE kind = 'grant_step';

-- Who owns each company's shares, counting shares the exchange is holding as their
-- owner's: shares waiting in a sell order, and shares offered to a bidder in a takeover.
CREATE VIEW share_owners AS
SELECT company_id, account_id, sum(shares)::bigint AS shares FROM (
    SELECT c.id AS company_id, b.account_id, b.balance AS shares
      FROM companies c JOIN ledger_balances b ON b.asset = c.share_asset JOIN ledger_accounts a ON a.id = b.account_id
     WHERE b.balance > 0 AND a.kind <> 'exchange'
    UNION ALL
    SELECT o.company_id, o.account_id, o.remaining FROM market_orders o
     WHERE o.side = 'sell' AND o.status = 'open' AND o.remaining > 0
    UNION ALL
    SELECT t.target_company_id, d.account_id, d.shares FROM takeover_tenders d JOIN takeovers t ON t.id = d.takeover_id
     WHERE t.status = 'open' AND d.shares > 0
) owned GROUP BY company_id, account_id;
