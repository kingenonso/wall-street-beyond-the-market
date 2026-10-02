-- Stage 2: the ledger.
--
-- The ledger is the permanent record of everything of value that moves in the
-- game: money (naira) and, from this stage, shares. Design document, sections
-- 10, 13 and 19.
--
-- Five rules are enforced here, inside the database itself, so that no part of
-- the game's code can break them, even by mistake:
--
--   1. Every movement has a payer and a receiver: the entries of one
--      transaction always add up to exactly zero.
--   2. Records are added, never edited or deleted.
--   3. Nobody can spend what they do not have. Only the issuer of an asset
--      (the Central Bank for naira, a company for its own shares) may hold a
--      negative balance in it. That negative balance IS the amount in existence.
--   4. A finished transaction is closed. Nothing can be added to it later.
--   5. Running balances can only be changed by adding a ledger entry.

-- ---------------------------------------------------------------------------
-- Accounts: who can hold things.
-- ---------------------------------------------------------------------------
CREATE TABLE ledger_accounts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind        text NOT NULL CHECK (kind IN (
                    'central_bank', 'government', 'prize_pool',
                    'npc_public', 'npc_investors', 'company', 'player')),
    name        text NOT NULL,
    -- A fixed handle for accounts the game itself looks up, e.g. 'treasury'.
    code        text UNIQUE,
    player_id   uuid UNIQUE REFERENCES players (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK ((kind = 'player') = (player_id IS NOT NULL))
);

-- ---------------------------------------------------------------------------
-- Assets: what can be held. Naira (counted in kobo) and each company's shares.
-- ---------------------------------------------------------------------------
CREATE TABLE assets (
    code               text PRIMARY KEY,
    kind               text NOT NULL CHECK (kind IN ('currency', 'share')),
    name               text NOT NULL,
    -- The smallest unit an amount is counted in. Naira is stored as whole kobo
    -- (1 naira = 100 kobo), so there are never any rounding errors.
    unit               text NOT NULL CHECK (unit IN ('kobo', 'share')),
    issuer_account_id  uuid NOT NULL REFERENCES ledger_accounts (id)
);

-- ---------------------------------------------------------------------------
-- Transactions and entries.
-- A transaction is one event ("Ikenga Bank pays tax"). Its entries say which
-- accounts changed: a negative amount is the payer, a positive one the receiver.
-- ---------------------------------------------------------------------------
CREATE TABLE ledger_transactions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind             text NOT NULL CHECK (kind <> ''),      -- the reason, as a short code
    memo             text NOT NULL CHECK (memo <> ''),      -- the reason, in plain words
    reference        text,                                  -- what it relates to, e.g. a loan
    period           integer CHECK (period >= 0),           -- the game quarter it belongs to
    -- Something that must happen only once carries a key. A second attempt with
    -- the same key is refused, so a reward can never be paid twice.
    idempotency_key  text UNIQUE,
    created_txid     bigint NOT NULL DEFAULT txid_current(),
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger_entries (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id  uuid NOT NULL REFERENCES ledger_transactions (id),
    account_id      uuid NOT NULL REFERENCES ledger_accounts (id),
    asset           text NOT NULL REFERENCES assets (code),
    amount          bigint NOT NULL CHECK (amount <> 0)
);
CREATE INDEX ledger_entries_by_transaction ON ledger_entries (transaction_id);
CREATE INDEX ledger_entries_by_account ON ledger_entries (account_id, id);

-- The running balance of each account in each asset. Kept in step with the
-- entries by the trigger below; a test proves the two always agree.
CREATE TABLE ledger_balances (
    account_id  uuid NOT NULL REFERENCES ledger_accounts (id),
    asset       text NOT NULL REFERENCES assets (code),
    balance     bigint NOT NULL,
    PRIMARY KEY (account_id, asset)
);

-- ---------------------------------------------------------------------------
-- Rule 2: records are added, never edited or deleted.
-- ---------------------------------------------------------------------------
CREATE FUNCTION ledger_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'The ledger is permanent: % on % is not allowed.', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_is_permanent';
END;
$$;

CREATE TRIGGER ledger_accounts_permanent BEFORE UPDATE OR DELETE ON ledger_accounts
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER ledger_accounts_no_truncate BEFORE TRUNCATE ON ledger_accounts
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER assets_permanent BEFORE UPDATE OR DELETE ON assets
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER assets_no_truncate BEFORE TRUNCATE ON assets
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER ledger_transactions_permanent BEFORE UPDATE OR DELETE ON ledger_transactions
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER ledger_transactions_no_truncate BEFORE TRUNCATE ON ledger_transactions
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER ledger_entries_permanent BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_change();
CREATE TRIGGER ledger_entries_no_truncate BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_forbid_change();

-- ---------------------------------------------------------------------------
-- Rule 4 (first half): the time and the database transaction that created a
-- ledger transaction are stamped by the database, never by the caller.
-- ---------------------------------------------------------------------------
CREATE FUNCTION ledger_stamp_transaction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.created_txid := txid_current();
    NEW.created_at := now();
    RETURN NEW;
END;
$$;
CREATE TRIGGER ledger_transactions_stamp BEFORE INSERT ON ledger_transactions
    FOR EACH ROW EXECUTE FUNCTION ledger_stamp_transaction();

-- ---------------------------------------------------------------------------
-- Rules 3, 4 and 5: applied as each entry is added.
-- ---------------------------------------------------------------------------
CREATE FUNCTION ledger_apply_entry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    opened_in    bigint;
    new_balance  bigint;
    issuer       uuid;
BEGIN
    -- Rule 4: entries can only join a transaction that is still being written.
    SELECT created_txid INTO opened_in FROM ledger_transactions WHERE id = NEW.transaction_id;
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
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER ledger_entries_apply AFTER INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_apply_entry();

-- Rule 5 (second half): balances cannot be written directly. The only writer
-- allowed is the trigger above, which runs one level deeper than a plain statement.
CREATE FUNCTION ledger_guard_balances() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'Balances change only when a ledger entry is added.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_balances_are_derived';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Balances are never deleted.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'ledger_balances_are_derived';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ledger_balances_guard BEFORE INSERT OR UPDATE OR DELETE ON ledger_balances
    FOR EACH ROW EXECUTE FUNCTION ledger_guard_balances();
CREATE TRIGGER ledger_balances_no_truncate BEFORE TRUNCATE ON ledger_balances
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_forbid_change();

-- ---------------------------------------------------------------------------
-- Rule 1: checked when the work is saved. If any transaction does not add up
-- to zero in every asset, or has no entries, the whole piece of work is refused.
-- ---------------------------------------------------------------------------
CREATE FUNCTION ledger_check_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    tx uuid;
BEGIN
    IF TG_TABLE_NAME = 'ledger_entries' THEN tx := NEW.transaction_id; ELSE tx := NEW.id; END IF;

    IF NOT EXISTS (SELECT 1 FROM ledger_entries WHERE transaction_id = tx) THEN
        RAISE EXCEPTION 'A ledger transaction must have entries.'
            USING ERRCODE = 'integrity_constraint_violation', CONSTRAINT = 'ledger_transaction_balanced';
    END IF;
    IF EXISTS (
        SELECT 1 FROM ledger_entries WHERE transaction_id = tx
        GROUP BY asset HAVING sum(amount) <> 0
    ) THEN
        RAISE EXCEPTION 'A ledger transaction must add up to zero: every amount paid must be received by someone.'
            USING ERRCODE = 'integrity_constraint_violation', CONSTRAINT = 'ledger_transaction_balanced';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ledger_entries_balanced AFTER INSERT ON ledger_entries
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_balanced();
CREATE CONSTRAINT TRIGGER ledger_transactions_balanced AFTER INSERT ON ledger_transactions
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_check_balanced();

-- ---------------------------------------------------------------------------
-- Players.
-- The Stage 1 stand-in for cash is removed: a player's money now lives in the
-- ledger, and their starting cash is paid to them by a named payer.
-- ---------------------------------------------------------------------------
ALTER TABLE players DROP COLUMN opening_cash_kobo;
ALTER TABLE players DROP COLUMN currency;

-- The standard profile picture a player chose. Empty until they choose one.
ALTER TABLE players ADD COLUMN profile_icon text CHECK (profile_icon IN ('male', 'female'));
