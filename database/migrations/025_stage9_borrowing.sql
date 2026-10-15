-- Stage 9, Part A: the stochastic engine's record, "What could happen?", personal and margin loans, short selling.

-- The quarter's common forces (economy, energy, building, farming, money). Kept for checking; never sent to players.
CREATE TABLE stochastic_factors (
    period  integer NOT NULL,
    name    text NOT NULL,
    value   double precision NOT NULL,
    PRIMARY KEY (period, name)
);

-- "What could happen?": each run a player asks for, so the free run a day can be counted.
CREATE TABLE monte_carlo_runs (
    id         bigserial PRIMARY KEY,
    player_id  uuid NOT NULL REFERENCES players (id),
    session_date date NOT NULL,
    what       text NOT NULL,
    fee        bigint NOT NULL DEFAULT 0,
    at         timestamptz NOT NULL
);
CREATE INDEX monte_carlo_runs_by_player ON monte_carlo_runs (player_id, session_date);

-- Loans to players and empires: a personal loan (against salary) or a loan against shares and bonds.
CREATE TABLE player_loans (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL CHECK (kind IN ('personal', 'margin')),
    borrower        uuid NOT NULL REFERENCES ledger_accounts (id),
    bank_company_id uuid NOT NULL REFERENCES companies (id),
    principal       bigint NOT NULL CHECK (principal > 0),
    outstanding     bigint NOT NULL CHECK (outstanding >= 0),
    rate_bps        integer NOT NULL,
    taken_period    integer NOT NULL,
    term_quarters   integer,                         -- a personal loan is repaid evenly; a margin loan whenever the borrower likes
    missed          integer NOT NULL DEFAULT 0,
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaid', 'default')),
    call_since      date,                            -- a margin call stands since this Closing Bell
    at              timestamptz NOT NULL
);
CREATE INDEX player_loans_open ON player_loans (borrower) WHERE status <> 'repaid';
CREATE UNIQUE INDEX player_loans_one_margin ON player_loans (borrower, bank_company_id) WHERE kind = 'margin' AND status <> 'repaid';

-- Short selling: shares borrowed from a pension fund, and the cash held as collateral.
CREATE TABLE short_positions (
    id            bigserial PRIMARY KEY,
    borrower      uuid NOT NULL REFERENCES ledger_accounts (id),
    lender        uuid NOT NULL REFERENCES ledger_accounts (id),
    company_id    uuid NOT NULL REFERENCES companies (id),
    shares        bigint NOT NULL CHECK (shares > 0),
    collateral    bigint NOT NULL CHECK (collateral >= 0),
    opened_price  bigint NOT NULL,
    opened_period integer NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'returned', 'bought_in')),
    call_since    date,                              -- a margin call stands since this Closing Bell
    recalled_period integer,                         -- the lender wants its shares back by the next close
    fees_paid     bigint NOT NULL DEFAULT 0,
    closed_price  bigint,
    at            timestamptz NOT NULL,
    closed_at     timestamptz
);
CREATE INDEX short_positions_open ON short_positions (company_id) WHERE status = 'open';
CREATE INDEX short_positions_borrower ON short_positions (borrower) WHERE status = 'open';

-- What happened to a loan or a short at the Closing Bell: calls, forced sales, buy-ins. The borrower's own record.
CREATE TABLE lending_events (
    id        bigserial PRIMARY KEY,
    account   uuid NOT NULL REFERENCES ledger_accounts (id),
    loan_id   bigint REFERENCES player_loans (id),
    short_id  bigint REFERENCES short_positions (id),
    kind      text NOT NULL,
    words     text NOT NULL,
    at        timestamptz NOT NULL
);
CREATE INDEX lending_events_by_account ON lending_events (account, at DESC);
