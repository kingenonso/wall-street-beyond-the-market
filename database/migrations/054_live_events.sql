-- Live events, part 1 (owner, 16 November 2026): three times a week, at 20:00 Lagos time on Monday, Wednesday and
-- Friday, something happens in the shared world at once for everybody, and for thirty minutes every empire competes on
-- how it reads and handles it.
--
-- Five kinds, each a real thing in the world with a real effect: a fraud uncovered at a listed company, an oil price
-- spike, a run on a bank, an emergency move by the Central Bank, and a takeover bid. Which kind, and whom it strikes, is
-- decided at the bell from the world's secret, so nobody can know it in advance.
--
-- Empires are scored on how far their prediction of the featured share's move came from what happened, and on what the
-- event did to their money (the shares it touched, held and traded, against what the empire was worth at the bell).
-- Points go to the league. An empire's head may leave a standing plan beforehand for members who cannot be there.

CREATE TABLE live_events (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at            timestamptz NOT NULL UNIQUE,         -- the bell: one event for each slot
    ends_at              timestamptz NOT NULL,
    predict_until        timestamptz NOT NULL,                -- predictions are sealed and close a few minutes in
    kind                 text NOT NULL CHECK (kind IN ('fraud', 'oil_spike', 'bank_run', 'rate_move', 'takeover')),
    period               integer NOT NULL,
    day                  integer NOT NULL,
    featured_company_id  uuid NOT NULL REFERENCES companies (id),
    start_price          bigint NOT NULL CHECK (start_price > 0),     -- the featured share at the bell, before the news
    end_price            bigint,                                      -- ...and when the event ends
    rate_bps             integer NOT NULL DEFAULT 0,          -- rate_move: added to the Central Bank's next decision
    world_event_id       bigint REFERENCES events (id),       -- the event in the world's quarter, where there is one
    takeover_id          bigint REFERENCES takeovers (id),
    headline             text NOT NULL,
    story                text NOT NULL,
    touched              jsonb NOT NULL,                      -- [{company_id, ticker, name, bps}]: the shares it moves
    status               text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'scored')),
    scored_at            timestamptz,
    CHECK (ends_at > starts_at AND predict_until > starts_at AND predict_until <= ends_at)
);

-- What the event adds to how investors value each share it touches: in full for those who read the news at once, a
-- day later for the institutions, fading over a few trading days. Never money: only how investors price.
CREATE TABLE live_event_shocks (
    event_id      bigint NOT NULL REFERENCES live_events (id),
    company_id    uuid NOT NULL REFERENCES companies (id),
    bps           integer NOT NULL CHECK (bps BETWEEN -1000 AND 1000),
    session_date  date NOT NULL,
    days          integer NOT NULL CHECK (days BETWEEN 1 AND 10),
    PRIMARY KEY (event_id, company_id)
);

-- Every empire in the field at the bell, and how it came out.
CREATE TABLE live_event_entries (
    event_id           bigint NOT NULL REFERENCES live_events (id),
    empire_id          bigint NOT NULL REFERENCES empires (id),
    run_by_players     boolean NOT NULL,
    worth_at_bell      bigint NOT NULL,
    held_at_bell       jsonb NOT NULL,                        -- {company_id: shares} of the shares the event touches
    prediction_bps     integer,                               -- the featured share's move from the bell, as predicted
    predicted_by       uuid REFERENCES players (id),
    predicted_at       timestamptz,
    result_kobo        bigint,                                -- at the end: what the event did to its money
    result_bps         integer,                               -- ...as a share of its worth at the bell
    miss_bps           integer,
    points             integer NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, empire_id)
);

CREATE FUNCTION live_prediction_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'An entry in a live event is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.prediction_bps IS NOT NULL AND (NEW.prediction_bps IS DISTINCT FROM OLD.prediction_bps
                                           OR NEW.predicted_by IS DISTINCT FROM OLD.predicted_by) THEN
        RAISE EXCEPTION 'A prediction cannot be changed once it is in.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.worth_at_bell <> OLD.worth_at_bell OR NEW.held_at_bell <> OLD.held_at_bell THEN
        RAISE EXCEPTION 'What an empire held at the bell cannot be changed.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER live_event_entries_sealed BEFORE UPDATE OR DELETE ON live_event_entries
    FOR EACH ROW EXECUTE FUNCTION live_prediction_sealed();

-- A head's standing plan, for when nobody from the empire can be there: carried out at the bell, by the head's own
-- authority and inside every limit an order from the head would meet.
CREATE TABLE live_event_plans (
    empire_id    bigint PRIMARY KEY REFERENCES empires (id),
    plan         text NOT NULL CHECK (plan IN ('hold', 'cut', 'buy_the_fall', 'ride')),
    budget       bigint NOT NULL DEFAULT 0 CHECK (budget >= 0),
    set_by       uuid NOT NULL REFERENCES players (id),
    at           timestamptz NOT NULL
);

-- What each standing plan did at the bell (or why it could not).
CREATE TABLE live_event_actions (
    event_id    bigint NOT NULL REFERENCES live_events (id),
    empire_id   bigint NOT NULL REFERENCES empires (id),
    what        text NOT NULL,
    done        boolean NOT NULL,
    at          timestamptz NOT NULL
);
CREATE INDEX live_event_actions_by_event ON live_event_actions (event_id);
