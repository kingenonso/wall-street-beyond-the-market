-- The tribunal's juries, part 2 (owner, 17 November 2026: "go on"): challenges, appeals and jury tampering.
--
-- Challenges: the two sides see who is on the jury and may each strike out one juror who has not voted, early in the
-- sitting; another is drawn. Appeals: a jury's verdict waits a day before it takes effect; the side that lost may pay a
-- fee to have a fresh jury (none of the first) hear the case, and the second verdict is final. Tampering: a side may
-- offer a juror money. The juror takes it or reports it. Reported, or told later, it is a crime the tribunal hears.

ALTER TABLE court_cases DROP CONSTRAINT court_cases_status_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_status_check
    CHECK (status IN ('open', 'jury', 'verdict', 'appeal', 'settled', 'judged', 'withdrawn'));
ALTER TABLE court_cases
    ADD COLUMN appeal_until   timestamptz,                         -- the first verdict waits until then
    ADD COLUMN appealed_by    text CHECK (appealed_by IN ('defendant', 'claimant')),
    ADD COLUMN appeal_fee     bigint CHECK (appeal_fee > 0),
    ADD COLUMN first_proved_bps integer,                           -- the first jury's verdict, kept when appealed
    ADD COLUMN first_penalty  text;

ALTER TABLE jurors DROP CONSTRAINT jurors_seat_check;
ALTER TABLE jurors ADD CONSTRAINT jurors_seat_check CHECK (seat BETWEEN 1 AND 30);
ALTER TABLE jurors
    ADD COLUMN round      integer NOT NULL DEFAULT 1 CHECK (round IN (1, 2)),
    ADD COLUMN struck_by  text CHECK (struck_by IN ('defendant', 'claimant'));

CREATE TABLE jury_offers (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id     bigint NOT NULL REFERENCES court_cases (id),
    round       integer NOT NULL,
    briber_id   uuid NOT NULL REFERENCES players (id),
    juror_id    uuid NOT NULL REFERENCES players (id),
    amount      bigint NOT NULL CHECK (amount > 0),
    wants       text NOT NULL CHECK (wants IN ('acquit', 'convict')),
    status      text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'taken', 'reported', 'lapsed')),
    tell_bps    integer NOT NULL CHECK (tell_bps BETWEEN 0 AND 10000),
    exposed_how text CHECK (exposed_how IN ('reported', 'told')),
    exposed_at  timestamptz,
    at          timestamptz NOT NULL,
    UNIQUE (case_id, round, briber_id, juror_id)
);

ALTER TABLE court_cases DROP CONSTRAINT court_cases_kind_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_kind_check
    CHECK (kind IN ('insider', 'manipulation', 'undisclosed_stake', 'naked_short', 'insurance_fraud', 'front_running', 'order_leak',
                    'collusion', 'union_bribery', 'jury_tampering'));
