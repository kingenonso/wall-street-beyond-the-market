-- The tribunal's juries, part 1 (owner, 17 November 2026: "build tribunal first").
--
-- A defendant who fights a case may ask for a jury of players instead of the judge. Five players with no tie to either
-- side are summoned. Each reads the case file (the claim, the lines of the record, both sides' statements) and votes two
-- things: how much of the claim the record proves (all of it, three quarters, half, a quarter, or none), and the penalty
-- (lenient, standard, harsh). The middle vote of each decides. Jurors are paid a fee for each vote, and a fair-verdict
-- record shows how often a juror's vote matched the verdict. With fewer than three votes by the deadline, the judge decides.

ALTER TABLE court_cases DROP CONSTRAINT court_cases_status_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_status_check CHECK (status IN ('open', 'jury', 'settled', 'judged', 'withdrawn'));
ALTER TABLE court_cases DROP CONSTRAINT court_cases_outcome_check;
ALTER TABLE court_cases ADD CONSTRAINT court_cases_outcome_check CHECK (outcome IN ('settled', 'judged', 'withdrawn', 'acquitted'));
ALTER TABLE court_cases
    ADD COLUMN jury_until   timestamptz,                                    -- when the jury's votes close
    ADD COLUMN decided_by   text CHECK (decided_by IN ('judge', 'jury')),
    ADD COLUMN proved_bps   integer CHECK (proved_bps BETWEEN 0 AND 10000), -- how much of the claim was found proved
    ADD COLUMN penalty      text CHECK (penalty IN ('lenient', 'standard', 'harsh')),
    ADD COLUMN defence      text CHECK (length(defence) <= 600),            -- the defendant's statement to the jury
    ADD COLUMN claim_note   text CHECK (length(claim_note) <= 600);         -- the claimant's statement (a player claimant)

CREATE TABLE jurors (
    case_id      bigint NOT NULL REFERENCES court_cases (id),
    player_id    uuid NOT NULL REFERENCES players (id),
    seat         integer NOT NULL CHECK (seat BETWEEN 1 AND 9),
    summoned_at  timestamptz NOT NULL,
    proved_bps   integer CHECK (proved_bps IN (0, 2500, 5000, 7500, 10000)),
    penalty      text CHECK (penalty IN ('lenient', 'standard', 'harsh')),
    reason       text CHECK (length(reason) <= 300),
    voted_at     timestamptz,
    fee          bigint NOT NULL DEFAULT 0 CHECK (fee >= 0),
    agreed       boolean,                                               -- set at the verdict: did the vote match it?
    PRIMARY KEY (case_id, player_id),
    UNIQUE (case_id, seat),
    CHECK ((proved_bps IS NULL) = (voted_at IS NULL))
);
CREATE INDEX jurors_by_player ON jurors (player_id, case_id DESC);
