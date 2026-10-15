-- Stage 9, Part B: options and futures (dealt with the market makers' desk), the hedging desk and the crash fund.

-- What can be traded: each option and future, on what, at what strike, to which quarter's close.
CREATE TABLE derivative_series (
    id            bigserial PRIMARY KEY,
    kind          text NOT NULL CHECK (kind IN ('call', 'put', 'future')),
    underlying    text NOT NULL,                     -- a company's ticker, or BSX50, OIL, NAIRA, FARM, METALS, MATERIALS
    company_id    uuid REFERENCES companies (id),
    strike        bigint,                            -- options: in the underlying's own unit (kobo a share, index hundredths...)
    expiry_period integer NOT NULL,                  -- settled at this quarter's close
    listed_period integer NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'settled')),
    settled_spot  bigint
);
-- (A future has no strike: the index counts a missing strike as one value, so each is listed once.)
CREATE UNIQUE INDEX derivative_series_once ON derivative_series (kind, underlying, coalesce(strike, -1), expiry_period);
CREATE INDEX derivative_series_open ON derivative_series (expiry_period) WHERE status = 'open';

-- Positions: bought (long) or written/sold (short) against the desk.
CREATE TABLE derivative_positions (
    id          bigserial PRIMARY KEY,
    account     uuid NOT NULL REFERENCES ledger_accounts (id),
    series_id   bigint NOT NULL REFERENCES derivative_series (id),
    side        text NOT NULL CHECK (side IN ('long', 'short')),
    contracts   integer NOT NULL CHECK (contracts > 0),
    entry_price bigint NOT NULL,                     -- a contract's price when opened (kobo)
    mark        bigint NOT NULL,                     -- futures: the price it was last settled at
    margin      bigint NOT NULL DEFAULT 0 CHECK (margin >= 0),   -- held by the exchange for it
    purpose     text,                                -- an empire's hedge: what it protects
    opened_by   uuid REFERENCES players (id),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'expired', 'closed_by_force')),
    call_since  date,
    result      bigint,                              -- what the position made or lost in all, once it is over
    opened_at   timestamptz NOT NULL,
    closed_at   timestamptz
);
CREATE INDEX derivative_positions_open ON derivative_positions (series_id) WHERE status = 'open';
CREATE INDEX derivative_positions_account ON derivative_positions (account) WHERE status = 'open';

-- The crash fund: empires pay in each quarter for cover that pays out when the BSX 50 falls hard in a quarter.
CREATE TABLE crash_fund_members (
    empire_id   bigint PRIMARY KEY REFERENCES empires (id),
    cover       bigint NOT NULL CHECK (cover >= 0),
    since       timestamptz NOT NULL,
    paid_in     bigint NOT NULL DEFAULT 0,
    paid_out    bigint NOT NULL DEFAULT 0,
    covered_period integer,                          -- the quarter its last premium paid for: only that quarter's crash pays it
    paid_cover  bigint NOT NULL DEFAULT 0,           -- the cover that premium bought
    active      boolean NOT NULL DEFAULT true
);
CREATE TABLE crash_fund_quarters (
    period      integer PRIMARY KEY,
    index_start bigint NOT NULL,
    index_end   bigint NOT NULL,
    triggered   boolean NOT NULL,
    premiums    bigint NOT NULL,
    paid_out    bigint NOT NULL
);
