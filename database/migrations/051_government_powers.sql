-- Government, part 2 (owner: "build part 2", 14 November 2026): the leader's other powers, and lobbying.
--
-- A decree: the leader may set next quarter's Central Bank rate, within three points of what the Central Bank's own
-- rule would set. It costs: prices rise faster that quarter and confidence falls (decided 3 October 2026: "the leader
-- may override the Central Bank by decree, at a cost to prices and trust").
-- A levy: the leader may ask the Assembly to take up to two per cent of one empire's cash for the Treasury. Targeting an
-- empire needs an Assembly vote (decided 3 October 2026).
-- Lobbying: the head of an empire may pay the Treasury, in the open, to win one computer-run member's vote on a budget
-- or a motion. Every naira and every member lobbied is public.
-- The leader is paid a salary by the Treasury each quarter in office.

CREATE TABLE decrees (
    period           integer PRIMARY KEY,                      -- the quarter in which it was made; it sets the rate after it
    leader_id        uuid NOT NULL REFERENCES players (id),
    rate_bps         integer NOT NULL CHECK (rate_bps BETWEEN 0 AND 5000),
    applied_bps      integer,                                  -- what it set, once the close has applied the limits
    rule_bps         integer,                                  -- what the Central Bank's rule would have set
    at               timestamptz NOT NULL
);

ALTER TABLE motions DROP CONSTRAINT motions_kind_check;
ALTER TABLE motions ADD CONSTRAINT motions_kind_check CHECK (kind IN ('no_confidence', 'levy'));
ALTER TABLE motions ADD COLUMN payload jsonb;                  -- a levy: {"empire_id": .., "bps": .., "reason": ..}
ALTER TABLE motions ADD COLUMN collected bigint;               -- a levy passed: what was taken

CREATE TABLE lobbying (
    subject          text NOT NULL,                            -- 'budget:<id>' or 'motion:<id>'
    seat             integer NOT NULL,                         -- the computer-run member
    empire_id        bigint NOT NULL REFERENCES empires (id),
    vote             boolean NOT NULL,                         -- how the member will now vote: as the empire's head voted
    paid             bigint NOT NULL CHECK (paid > 0),
    at               timestamptz NOT NULL,
    PRIMARY KEY (subject, seat)                                -- a member is won over once on each vote
);
CREATE TRIGGER lobbying_sealed BEFORE UPDATE OR DELETE ON lobbying FOR EACH ROW EXECUTE FUNCTION government_sealed();
