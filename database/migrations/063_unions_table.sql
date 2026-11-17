-- Unions and strikes, part 2: the empire at the table (owner, 17 November 2026: "go on").
--
-- At a company an empire run by players controls, the empire's head answers the union's demand: agree, offer less, or
-- refuse. The head may ask once for more time, and may hire an outside mediator for a fee. Silence by the deadline is a
-- refusal. Members of the empire may put their advice on record for the head. Private companies' staff now have unions
-- too: their pay against the going rate and their morale feed the anger, and the union, not chance, calls a walkout.

ALTER TABLE union_disputes
    ADD COLUMN empire_id     bigint REFERENCES empires (id),     -- the player-run empire whose head answers, if any
    ADD COLUMN answer        text CHECK (answer IN ('agree', 'offer', 'refuse', 'none', 'board')),
    ADD COLUMN answered_by   uuid REFERENCES players (id),
    ADD COLUMN decided_day   integer CHECK (decided_day BETWEEN 1 AND 90),
    ADD COLUMN more_time     text CHECK (more_time IN ('granted', 'refused')),
    ADD COLUMN mediator_fee  bigint CHECK (mediator_fee > 0),
    ADD COLUMN mediator_worked boolean,
    ADD COLUMN told          boolean NOT NULL DEFAULT false;     -- the empire has been told the demand has arrived

CREATE TABLE union_advice (
    dispute_id  integer NOT NULL REFERENCES union_disputes (id),
    player_id   uuid NOT NULL REFERENCES players (id),
    build       text NOT NULL,
    advice      text NOT NULL CHECK (advice IN ('agree', 'offer', 'refuse')),
    offer_bps   integer CHECK (offer_bps > 0),
    note        text CHECK (length(note) <= 300),
    at          timestamptz NOT NULL,
    PRIMARY KEY (dispute_id, player_id),
    CHECK ((advice = 'offer') = (offer_bps IS NOT NULL))
);
