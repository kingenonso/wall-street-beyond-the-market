-- The gap stage, Part 1: mezzanine debt and earn-outs in private-company deals; sale-and-leaseback of property.

-- Mezzanine: a dearer loan from the pension funds, repaid after the bank, with warrants for part of the company
-- (used at once: the lender takes that part of the shares when the purchase completes).
ALTER TABLE deal_bids ADD COLUMN mezzanine bigint NOT NULL DEFAULT 0 CHECK (mezzanine >= 0);
ALTER TABLE deal_bids ADD COLUMN mezz_rate_bps integer;
-- An earn-out: part of the price is paid later, and only if the company's sales hold up.
ALTER TABLE deal_bids ADD COLUMN earnout bigint NOT NULL DEFAULT 0 CHECK (earnout >= 0);
ALTER TABLE empire_debts DROP CONSTRAINT empire_debts_kind_check;
ALTER TABLE empire_debts ADD CONSTRAINT empire_debts_kind_check CHECK (kind IN ('loan', 'bond', 'buyout', 'mezzanine'));

CREATE TABLE deal_earnouts (
    id             bigserial PRIMARY KEY,
    deal_id        bigint NOT NULL REFERENCES deals (id),
    empire_id      bigint NOT NULL REFERENCES empires (id),
    seller_account uuid NOT NULL REFERENCES ledger_accounts (id),
    amount         bigint NOT NULL CHECK (amount > 0),
    target_sales   bigint NOT NULL,                  -- the company's sales over the earn-out quarters must reach this
    from_period    integer NOT NULL,
    due_period     integer NOT NULL,                 -- judged and paid (or not) as this quarter closes
    status         text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'paid', 'part', 'missed', 'short')),
    paid           bigint NOT NULL DEFAULT 0,
    at             timestamptz NOT NULL
);

-- Sale-and-leaseback: the owner sells a building and rents it back for a term, keeping the use of it.
CREATE TABLE property_leases (
    id            bigserial PRIMARY KEY,
    property_id   integer NOT NULL REFERENCES properties (id),
    tenant        uuid NOT NULL REFERENCES ledger_accounts (id),
    landlord      uuid NOT NULL REFERENCES ledger_accounts (id),
    rent          bigint NOT NULL CHECK (rent > 0),          -- a quarter
    first_period  integer NOT NULL,
    last_period   integer NOT NULL,
    status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ended', 'broken')),
    missed        integer NOT NULL DEFAULT 0,
    at            timestamptz NOT NULL
);
CREATE INDEX property_leases_running ON property_leases (property_id) WHERE status = 'running';
