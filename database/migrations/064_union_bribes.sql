-- Unions and strikes, part 3: union crimes (owner, 17 November 2026: "go on").
--
-- The head of an empire run by players may pay a union leader in secret: to make trouble at a rival empire's company
-- (the leader turns hard: only the full demand will do, and if no demand is open one is lodged), or to settle at a
-- company of their own (the leader takes half the demand). It is paid as a "consultancy fee" and is a crime. Some
-- leaders refuse and tell at once. The others may tell later: the chance starts low and rises with every bribe the
-- empire has paid before. A journalist can dig it out. Once it is out, the tribunal can hear it.

CREATE TABLE union_bribes (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empire_id     bigint NOT NULL REFERENCES empires (id),
    payer_id      uuid NOT NULL REFERENCES players (id),
    union_id      integer NOT NULL REFERENCES unions (id),
    company_id    uuid NOT NULL REFERENCES companies (id),
    victim_empire_id bigint REFERENCES empires (id),          -- whose company was hit, for a bribe to make trouble
    kind          text NOT NULL CHECK (kind IN ('strike', 'calm')),
    amount        bigint NOT NULL CHECK (amount > 0),
    period        integer NOT NULL,
    dispute_id    integer REFERENCES union_disputes (id),
    refused       boolean NOT NULL DEFAULT false,             -- the leader would not take it (the money never left)
    tell_bps      integer NOT NULL CHECK (tell_bps BETWEEN 0 AND 10000),   -- the chance the leader tells, fixed when paid
    exposed_how   text CHECK (exposed_how IN ('refused', 'leader', 'journalist')),
    exposed_at    timestamptz,
    at            timestamptz NOT NULL
);
CREATE INDEX union_bribes_by_empire ON union_bribes (empire_id);
CREATE UNIQUE INDEX union_bribes_once_a_quarter ON union_bribes (empire_id, company_id, period) WHERE NOT refused;

ALTER TABLE union_disputes
    ADD COLUMN hardline boolean NOT NULL DEFAULT false,         -- a rival paid the leader: only the full demand will do
    ADD COLUMN softened boolean NOT NULL DEFAULT false;         -- the owner paid the leader: half the demand will do

ALTER TABLE court_cases DROP CONSTRAINT court_cases_kind_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_kind_check
    CHECK (kind IN ('insider', 'manipulation', 'undisclosed_stake', 'naked_short', 'insurance_fraud', 'front_running', 'order_leak',
                    'collusion', 'union_bribery'));
