-- Floor extras, slice 3 (owner, 17 November 2026: "Ok go ahead"): the wealth desk.
--
-- Rich computer clients come to the Floor looking for someone to look after their money. Each has a sum, a goal and
-- limits. Asset managers pitch a fee; the client picks on fee and record. The money sits in the client's own account,
-- which the manager trades. Breaking the client's limits is recorded; at each quarter's close the client reviews the
-- manager: it pays the fees and then stays, adds money, warns, or leaves with its money.

CREATE TABLE wealth_clients (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name             text NOT NULL,
    kind             text NOT NULL,                          -- which profile in WEALTH_CLIENT_KINDS
    goal             text NOT NULL,
    account_id       uuid REFERENCES ledger_accounts (id),   -- made when a manager is chosen
    amount           bigint NOT NULL CHECK (amount > 0),
    most_shares_bps  integer NOT NULL CHECK (most_shares_bps BETWEEN 0 AND 10000),
    least_cash_bps   integer NOT NULL CHECK (least_cash_bps BETWEEN 0 AND 10000),
    most_drop_bps    integer NOT NULL CHECK (most_drop_bps BETWEEN 1 AND 10000),
    goal_bps         integer NOT NULL CHECK (goal_bps >= 0),  -- the yearly return it hopes for
    banned           text[] NOT NULL DEFAULT '{}',            -- industries it will not hold
    arrived_at       timestamptz NOT NULL,
    pitches_until    timestamptz NOT NULL,
    status           text NOT NULL DEFAULT 'seeking' CHECK (status IN ('seeking', 'managed', 'left', 'went_elsewhere')),
    manager_id       uuid REFERENCES players (id),
    fee_bps          integer CHECK (fee_bps BETWEEN 0 AND 10000),       -- a yearly fee on the money looked after
    perf_bps         integer CHECK (perf_bps BETWEEN 0 AND 10000),      -- a share of the gain above the goal
    started_at       timestamptz,
    started_period   integer,
    review_value     bigint,                                  -- what it was worth at the start of the quarter being judged
    review_index     integer,                                 -- the share index then
    high_value       bigint,                                  -- its highest worth since the last review
    checked_at       timestamptz,                             -- when its limits were last looked at
    satisfaction_bps integer NOT NULL DEFAULT 6000 CHECK (satisfaction_bps BETWEEN 0 AND 10000),
    left_at          timestamptz,
    left_why         text
);
CREATE INDEX wealth_clients_status ON wealth_clients (status);
CREATE INDEX wealth_clients_manager ON wealth_clients (manager_id);

CREATE TABLE wealth_pitches (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id  integer NOT NULL REFERENCES wealth_clients (id),
    manager_id uuid NOT NULL REFERENCES players (id),
    fee_bps    integer NOT NULL CHECK (fee_bps BETWEEN 0 AND 10000),
    perf_bps   integer NOT NULL CHECK (perf_bps BETWEEN 0 AND 10000),
    at         timestamptz NOT NULL,
    status     text NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'won', 'lost')),
    UNIQUE (client_id, manager_id)
);

CREATE TABLE wealth_breaches (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id  integer NOT NULL REFERENCES wealth_clients (id),
    manager_id uuid NOT NULL REFERENCES players (id),
    period     integer NOT NULL,
    day        date NOT NULL,                                 -- the trading day it was seen
    kind       text NOT NULL CHECK (kind IN ('shares', 'cash', 'drop')),
    words      text NOT NULL,
    at         timestamptz NOT NULL,
    UNIQUE (client_id, day, kind)
);

CREATE TABLE wealth_reviews (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id        integer NOT NULL REFERENCES wealth_clients (id),
    manager_id       uuid NOT NULL REFERENCES players (id),
    period           integer NOT NULL,
    start_value      bigint NOT NULL,
    end_value        bigint NOT NULL,
    return_bps       integer NOT NULL,
    benchmark_bps    integer NOT NULL,
    breaches         integer NOT NULL,
    fee              bigint NOT NULL,
    perf_fee         bigint NOT NULL,
    satisfaction_bps integer NOT NULL,
    verdict          text NOT NULL CHECK (verdict IN ('adds', 'stays', 'warns', 'leaves')),
    words            text NOT NULL,
    at               timestamptz NOT NULL,
    UNIQUE (client_id, period)
);
CREATE INDEX wealth_reviews_manager ON wealth_reviews (manager_id);

ALTER TABLE floor_notes DROP CONSTRAINT floor_notes_kind_check;
ALTER TABLE floor_notes ADD CONSTRAINT floor_notes_kind_check CHECK (kind IN ('nudge', 'drop', 'hour', 'storm', 'risk', 'loan', 'wealth'));
