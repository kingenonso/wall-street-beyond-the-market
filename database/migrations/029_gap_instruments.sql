-- The gap stage, Part 1: preferred shares and warrants (the owner's suggestion 14, 8 October 2026).

ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_code_check;
ALTER TABLE assets ADD CONSTRAINT assets_code_check CHECK (code ~ '^([A-Z]{3}|SHR-[A-Z]{3}|BND-[A-Z0-9]{3,12}|PRF-[A-Z]{3}|WRT-[A-Z]{3}[0-9]{1,4})$');
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_kind_check;
ALTER TABLE assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('currency', 'share', 'bond', 'preferred', 'warrant'));
ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_unit_check;
ALTER TABLE assets ADD CONSTRAINT assets_unit_check CHECK (unit IN ('kobo', 'share', 'bond', 'preferred', 'warrant'));

-- New preferred shares and warrants may be brought into existence only by their issue.
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

-- A preferred share pays a fixed dividend before the ordinary shares are paid anything, carries no vote, and is
-- dealt at the pension funds' desk. A warrant is the right to buy new shares from the company at a set price until
-- a quarter's close; it comes with some rights issues and some high-yield bonds, and is dealt at the same desk.
CREATE TABLE instruments (
    id             bigserial PRIMARY KEY,
    asset          text NOT NULL UNIQUE REFERENCES assets (code),
    kind           text NOT NULL CHECK (kind IN ('preferred', 'warrant')),
    company_id     uuid NOT NULL REFERENCES companies (id),
    name           text NOT NULL,
    par            bigint,                       -- preferred: kobo each
    dividend_bps   integer,                      -- preferred: a year, on par, paid each quarter if the company made a profit
    strike         bigint,                       -- warrant: kobo for each new share
    shares_per     integer,                      -- warrant: new shares for each warrant
    expiry_period  integer,                      -- warrant: can be used until this quarter's close
    issued_period  integer NOT NULL,
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'expired')),
    why            text NOT NULL,
    at             timestamptz NOT NULL,
    CHECK ((kind = 'preferred') = (par IS NOT NULL AND dividend_bps IS NOT NULL)),
    CHECK ((kind = 'warrant') = (strike IS NOT NULL AND shares_per IS NOT NULL AND expiry_period IS NOT NULL))
);
CREATE INDEX instruments_by_company ON instruments (company_id);

CREATE TABLE instrument_trades (
    id          bigserial PRIMARY KEY,
    instrument_id bigint NOT NULL REFERENCES instruments (id),
    account     uuid NOT NULL REFERENCES ledger_accounts (id),
    side        text NOT NULL CHECK (side IN ('buy', 'sell')),
    units       bigint NOT NULL CHECK (units > 0),
    price       bigint NOT NULL CHECK (price > 0),
    at          timestamptz NOT NULL
);

-- Warrants handed in to be used: the warrants and the cash are held, and the new shares issued at the quarter's close.
CREATE TABLE warrant_exercises (
    id            bigserial PRIMARY KEY,
    instrument_id bigint NOT NULL REFERENCES instruments (id),
    account       uuid NOT NULL REFERENCES ledger_accounts (id),
    units         bigint NOT NULL CHECK (units > 0),
    cash          bigint NOT NULL CHECK (cash > 0),
    status        text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'done', 'cancelled')),
    period        integer,
    at            timestamptz NOT NULL
);
