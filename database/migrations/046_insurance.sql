-- DO NOT APPLY THIS ON ITS OWN.
--
-- Insurance system: policies, claims, pool, and no-claims record.
-- Run after the builds merge (045) and before lending rate updates (next stage).
--
-- ---------------------------------------------------------------------------
-- Policy table: one row per player-per-policy, tracking cover in force.
-- ---------------------------------------------------------------------------
CREATE TABLE insurance_policies (
    player_id        uuid NOT NULL REFERENCES players (id),
    kind             text NOT NULL,               -- 'property' | 'directors' | 'income' | 'umbrella'
    "limit"            bigint NOT NULL DEFAULT 0, -- sum insured in kobo
    excess           bigint NOT NULL DEFAULT 0, -- excess in kobo
    premium_bps      integer NOT NULL DEFAULT 0,-- premium basis points per quarter
    started          integer NOT NULL,          -- quarter when policy started
    ends             integer,                   -- quarter when policy ends (NULL = active)
    state            text NOT NULL DEFAULT 'active', -- 'active' | 'claimed' | 'refused' | 'expired'
    no_claims_years  integer NOT NULL DEFAULT 0,-- full years without a claim
    PRIMARY KEY (player_id, kind)
);

-- ---------------------------------------------------------------------------
-- Claims table: one row per claim, always paid from the pool.
-- ---------------------------------------------------------------------------
CREATE TABLE insurance_claims (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_player_id uuid NOT NULL REFERENCES players (id),
    policy_kind      text NOT NULL,
    loss_kind        text NOT NULL,               -- 'property' | 'directors' | 'income' | 'umbrella'
    loss_amount      bigint NOT NULL,             -- amount of loss in kobo
    evidence         text NOT NULL,               -- description of the loss event
    excess_applied   bigint NOT NULL DEFAULT 0, -- excess deducted
    payable          bigint NOT NULL,             -- amount paid from pool
    state            text NOT NULL DEFAULT 'open', -- 'open' | 'investigated' | 'paid' | 'refused'
    refused_reason   text,                        -- why refused (if refused)
    at               timestamptz NOT NULL DEFAULT now(),
    refused_at       timestamptz,
    -- A second attempt on the same policy permanently ends cover
    UNIQUE (policy_player_id, policy_kind, state)
);

-- ---------------------------------------------------------------------------
-- Refusals table: records that a second claim attempt permanently ends cover.
-- ---------------------------------------------------------------------------
CREATE TABLE insurance_refusals (
    player_id        uuid NOT NULL REFERENCES players (id),
    kind             text NOT NULL,               -- same kind as the refused policy
    at               timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, kind)
);

-- ---------------------------------------------------------------------------
-- Indexes for performance
-- ---------------------------------------------------------------------------
CREATE INDEX idx_insurance_claims_policy ON insurance_claims (policy_player_id, policy_kind);
CREATE INDEX idx_insurance_claims_state ON insurance_claims (state);
CREATE INDEX idx_insurance_policies_state ON insurance_policies (player_id, kind, state);
