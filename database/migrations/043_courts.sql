-- Stage 11: the courts, as a docket.
--
-- The court's subject is money, its evidence is the ledger, and its remedy is money moving. It is not a
-- place where guilt is decided: it is a place where a number is proved and paid. So a case is a claim
-- with an amount, the evidence that proves the amount, and a remedy that moves money.
--
-- Four kinds of case in this stage, all against the market:
--   insider            dealing on confidential information (recorded since Stage 10B)
--   manipulation       ramping and wash trading (market_trades.same_owner has recorded it since Stage 4)
--   undisclosed_stake  a holding past 5% that was never made public (stake_disclosures has the last one)
--   naked_short        borrowed shares that had to be bought in (short_positions has the buy-in)
--
-- The regulator's budget and the compensation fund are ledger accounts, not tables: every naira moves
-- through the ledger (working rule 7). What the regulator spends is the ledger transaction.

CREATE TABLE court_cases (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind           text NOT NULL CHECK (kind IN ('insider', 'manipulation', 'undisclosed_stake', 'naked_short')),
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'settled', 'judged', 'withdrawn')),
    defendant_id   uuid NOT NULL REFERENCES players (id),
    claimant_id    uuid REFERENCES players (id),          -- null: the regulator brought it
    company_id     uuid REFERENCES companies (id),
    amount         bigint NOT NULL CHECK (amount >= 0),   -- the number the claim is worth, in kobo
    bond           bigint NOT NULL DEFAULT 0 CHECK (bond >= 0),   -- what a player claimant posted
    evidence       jsonb NOT NULL,                        -- the lines that prove the number
    words          text NOT NULL,                         -- the claim in plain words
    opened_period  integer NOT NULL,
    opened_at      timestamptz NOT NULL,
    decided_at     timestamptz,
    outcome        text CHECK (outcome IN ('settled', 'judged', 'withdrawn')),
    disgorgement   bigint NOT NULL DEFAULT 0 CHECK (disgorgement >= 0),
    damages        bigint NOT NULL DEFAULT 0 CHECK (damages >= 0),
    fine           bigint NOT NULL DEFAULT 0 CHECK (fine >= 0),
    costs          bigint NOT NULL DEFAULT 0 CHECK (costs >= 0),   -- what the loser pays the winner
    paid           bigint NOT NULL DEFAULT 0 CHECK (paid >= 0),    -- what has been paid so far
    ban_quarters   integer NOT NULL DEFAULT 0 CHECK (ban_quarters >= 0)
);
CREATE INDEX court_cases_open ON court_cases (status) WHERE status = 'open';
CREATE INDEX court_cases_by_defendant ON court_cases (defendant_id, id DESC);
CREATE INDEX court_cases_by_claimant ON court_cases (claimant_id, id DESC) WHERE claimant_id IS NOT NULL;

-- A case, once opened, is not rewritten. Its claim and its evidence stay as they were: what changes is
-- its status and what it ordered. (Records are added, never edited: working rule 3.)
CREATE FUNCTION court_cases_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.kind <> OLD.kind
       OR NEW.defendant_id <> OLD.defendant_id
       OR NEW.claimant_id IS DISTINCT FROM OLD.claimant_id
       OR NEW.company_id IS DISTINCT FROM OLD.company_id
       OR NEW.amount <> OLD.amount
       OR NEW.evidence <> OLD.evidence
       OR NEW.opened_at <> OLD.opened_at
       OR NEW.opened_period <> OLD.opened_period THEN
        RAISE EXCEPTION 'A case, once opened, is not rewritten. Its claim and its evidence stay as they were.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'court_case_rewritten';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER court_cases_guarded BEFORE UPDATE ON court_cases FOR EACH ROW EXECUTE FUNCTION court_cases_guard();

-- What has been paid against a case, one payment at a time. Restitution is paid down over quarters, so
-- a case can be judged and still be owed.
CREATE TABLE court_payments (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id  bigint NOT NULL REFERENCES court_cases (id),
    amount   bigint NOT NULL CHECK (amount > 0),
    at       timestamptz NOT NULL
);
CREATE INDEX court_payments_by_case ON court_payments (case_id, id);
CREATE TRIGGER court_payments_permanent BEFORE UPDATE OR DELETE ON court_payments FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- A trading ban: no trading until the quarter named. A financial penalty, because you cannot earn.
CREATE TABLE court_bans (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id    uuid NOT NULL REFERENCES players (id),
    case_id      bigint NOT NULL REFERENCES court_cases (id),
    until_period integer NOT NULL,
    at           timestamptz NOT NULL
);
CREATE INDEX court_bans_by_player ON court_bans (player_id, until_period DESC);
CREATE TRIGGER court_bans_permanent BEFORE UPDATE OR DELETE ON court_bans FOR EACH ROW EXECUTE FUNCTION records_forbid_change();
