-- Insurance: four policies a player can buy under Money (owner, 9 November 2026).
--
-- Every naira moves through the ledger: premiums go from the player into the policy account at `insurance:pool`, and
-- claims come out of it. These tables only say what was bought, what was claimed and what the insurer decided.
--
-- A policy row is one purchase. It is not rewritten when the cover ends: it gets an end, and the next purchase is a new
-- row, so the record says what cover was in force on any day. At most one policy of each kind is in force for a player.
--
-- The no-claims record is kept per player and per kind, apart from the policies, so cancelling and buying again does
-- not wipe a claim off it. A claim is made against a loss the game recorded (a building's wear, a dismissal, a
-- tribunal judgment), named by that record, so the same loss cannot be claimed twice.
--
-- The tribunal hears a fifth kind of case: insurance fraud, a claim on a loss the claimant caused.

CREATE TABLE insurance_policies (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id      uuid NOT NULL REFERENCES players (id),
    kind           text NOT NULL CHECK (kind IN ('property', 'directors', 'income', 'umbrella')),
    cover          bigint NOT NULL CHECK (cover > 0),            -- the most one claim is paid, in kobo
    excess         bigint NOT NULL CHECK (excess >= 0),          -- the part of each loss the policyholder bears
    premium        bigint NOT NULL CHECK (premium > 0),          -- the last quarter's premium charged
    started_period integer NOT NULL,
    started_at     timestamptz NOT NULL,
    paid_through   integer NOT NULL,                            -- the last quarter whose premium has been paid
    ended_period   integer,
    ended_at       timestamptz,
    ended_reason   text CHECK (ended_reason IN ('cancelled', 'lapsed', 'barred')),
    CHECK ((ended_at IS NULL) = (ended_reason IS NULL))
);
CREATE UNIQUE INDEX insurance_one_in_force ON insurance_policies (player_id, kind) WHERE ended_at IS NULL;
CREATE INDEX insurance_policies_by_player ON insurance_policies (player_id, id DESC);

CREATE TABLE insurance_records (
    player_id      uuid NOT NULL REFERENCES players (id),
    kind           text NOT NULL CHECK (kind IN ('property', 'directors', 'income', 'umbrella')),
    clean_quarters integer NOT NULL DEFAULT 0 CHECK (clean_quarters >= 0),   -- quarters paid for in a row with no claim
    counted_period integer NOT NULL DEFAULT 0,                              -- the last quarter added to it
    PRIMARY KEY (player_id, kind)
);

CREATE TABLE insurance_claims (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id      uuid NOT NULL REFERENCES players (id),
    policy_id      bigint REFERENCES insurance_policies (id),   -- null: no policy was in force when the loss happened
    kind           text NOT NULL CHECK (kind IN ('property', 'directors', 'income')),
    loss_key       text NOT NULL,                               -- the record the loss is read from
    loss           bigint NOT NULL CHECK (loss >= 0),
    excess         bigint NOT NULL DEFAULT 0 CHECK (excess >= 0),
    payable        bigint NOT NULL DEFAULT 0 CHECK (payable >= 0),   -- what the policies owe on it, umbrella included
    umbrella       bigint NOT NULL DEFAULT 0 CHECK (umbrella >= 0),  -- the part of it the umbrella pays
    paid           bigint NOT NULL DEFAULT 0 CHECK (paid >= 0),      -- what the pool has paid so far
    instalments    integer NOT NULL DEFAULT 0 CHECK (instalments >= 0),   -- income protection: quarters still to pay
    decision       text NOT NULL CHECK (decision IN ('paid', 'paying', 'declined', 'refused')),
    reason         text NOT NULL,
    case_id        bigint REFERENCES court_cases (id),          -- the fraud case a refusal opened, if any
    period         integer NOT NULL,
    at             timestamptz NOT NULL,
    CHECK (paid <= payable)
);
-- A loss is claimed once and paid once. A claim refused or declined stays on the record and blocks another.
CREATE UNIQUE INDEX insurance_one_claim_per_loss ON insurance_claims (player_id, loss_key);
CREATE INDEX insurance_claims_paying ON insurance_claims (decision) WHERE decision = 'paying';

-- After two claims refused because the claimant caused the loss, no insurer writes for that player again.
CREATE TABLE insurance_bars (
    player_id      uuid PRIMARY KEY REFERENCES players (id),
    at             timestamptz NOT NULL
);

ALTER TABLE court_cases DROP CONSTRAINT court_cases_kind_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_kind_check
    CHECK (kind IN ('insider', 'manipulation', 'undisclosed_stake', 'naked_short', 'insurance_fraud'));
