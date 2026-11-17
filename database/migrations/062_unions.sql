-- Unions and strikes, part 1 (owner, 16 November 2026: "build"; leaders are computer-run).
--
-- One union for each industry, with a named leader. At each quarter's close every listed company's staff weigh up how
-- they are treated (pay against prices, profits against pay, jobs cut); an angry enough workforce lodges a pay demand
-- for the coming quarter. On the deadline the company's board answers: it agrees, offers less, or refuses. An offer the
-- union will not take, or a refusal, is a strike: real days of lost sales, recorded as the quarter's event, until a
-- settlement. A pay deal raises the company's wage bill above the going rate, and the going rate catches up in time.

CREATE TABLE unions (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sector      text NOT NULL UNIQUE REFERENCES sectors (code),
    name        text NOT NULL UNIQUE,
    leader      text NOT NULL,
    -- How ready the leader is to call a strike, from 0 (never) to 10000 (at the first excuse).
    militancy_bps integer NOT NULL CHECK (militancy_bps BETWEEN 0 AND 10000),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE union_disputes (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    union_id      integer NOT NULL REFERENCES unions (id),
    company_id    uuid NOT NULL REFERENCES companies (id),
    period        integer NOT NULL CHECK (period >= 1),
    opened_day    integer NOT NULL CHECK (opened_day BETWEEN 1 AND 90),
    deadline_day  integer NOT NULL CHECK (deadline_day BETWEEN 1 AND 90),
    anger_bps     integer NOT NULL CHECK (anger_bps >= 0),
    reasons       jsonb NOT NULL DEFAULT '[]',
    demand_bps    integer NOT NULL CHECK (demand_bps > 0),          -- the pay rise asked for
    offer_bps     integer CHECK (offer_bps >= 0),                   -- what the board offered
    settled_bps   integer CHECK (settled_bps >= 0),                 -- the rise finally agreed
    strike_days   integer CHECK (strike_days BETWEEN 1 AND 90),
    ends_day      integer CHECK (ends_day BETWEEN 1 AND 90),
    event_id      bigint REFERENCES events (id),
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'agreed', 'struck', 'ended')),
    decided_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, period),
    CHECK (deadline_day > opened_day)
);
CREATE INDEX union_disputes_open ON union_disputes (period, status);

-- A pay deal: how far above the going rate the company now pays. It shrinks each quarter as the going rate catches up.
ALTER TABLE companies ADD COLUMN union_pay_bps integer NOT NULL DEFAULT 0 CHECK (union_pay_bps BETWEEN 0 AND 4000);
