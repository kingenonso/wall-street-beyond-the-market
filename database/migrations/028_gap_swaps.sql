-- The gap stage, Part 1: swaps. Private contracts between two parties (players, empires, or a bank), paid at each
-- quarter's close. Nobody holds collateral: if one side cannot pay, the other is owed what is missing.

CREATE TABLE swaps (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL CHECK (kind IN ('rate', 'oil')),
    fixed_payer     uuid REFERENCES ledger_accounts (id),          -- pays the fixed leg, receives the floating one
    float_payer     uuid REFERENCES ledger_accounts (id),          -- pays the floating leg, receives the fixed one
    proposer        uuid NOT NULL REFERENCES ledger_accounts (id),
    proposer_side   text NOT NULL CHECK (proposer_side IN ('pay_fixed', 'receive_fixed')),
    counterparty    uuid NOT NULL REFERENCES ledger_accounts (id),
    bank_company_id uuid REFERENCES companies (id),                -- a bank as the other side (it accepts at once, at its own price)
    notional        bigint CHECK (notional > 0),                    -- a rate swap: the sum the interest is worked out on (kobo)
    barrels         bigint CHECK (barrels > 0),                     -- an oil swap: barrels a quarter
    fixed_bps       integer,                                       -- a rate swap's fixed rate, a year
    fixed_price     bigint,                                        -- an oil swap's fixed price, kobo a barrel
    quarters        integer NOT NULL CHECK (quarters BETWEEN 1 AND 8),
    first_period    integer,                                       -- payments at the closes of first_period to last_period
    last_period     integer,
    status          text NOT NULL DEFAULT 'signing' CHECK (status IN ('signing', 'proposed', 'countersigning', 'active', 'ended',
                                                                       'declined', 'cancelled')),
    proposed_by     uuid REFERENCES players (id),
    accepted_by     uuid REFERENCES players (id),
    contract        text,                                          -- the terms as Legal Counsel drafted them
    at              timestamptz NOT NULL,
    active_at       timestamptz,
    CHECK ((kind = 'rate') = (notional IS NOT NULL AND fixed_bps IS NOT NULL)),
    CHECK ((kind = 'oil') = (barrels IS NOT NULL AND fixed_price IS NOT NULL))
);
CREATE INDEX swaps_by_party ON swaps (proposer);
CREATE INDEX swaps_by_counterparty ON swaps (counterparty);
CREATE INDEX swaps_active ON swaps (status) WHERE status = 'active';

-- Each quarter's payment: the floating level that applied, who paid whom, and what is still owed.
CREATE TABLE swap_payments (
    swap_id    bigint NOT NULL REFERENCES swaps (id),
    period     integer NOT NULL,
    floating   bigint NOT NULL,                                  -- the rate (bps) or the oil price (kobo a barrel) that applied
    amount     bigint NOT NULL,                                  -- what moved, before any shortfall
    payer      uuid REFERENCES ledger_accounts (id),
    receiver   uuid REFERENCES ledger_accounts (id),
    paid       bigint NOT NULL DEFAULT 0,
    at         timestamptz NOT NULL,
    PRIMARY KEY (swap_id, period)
);
