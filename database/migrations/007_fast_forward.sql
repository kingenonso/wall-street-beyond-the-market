-- A fast-forward for testing (owner, 2 October 2026).
--
-- On a test world, the owner can move the calendar ahead by whole weeks, so
-- that quarters can be watched without waiting a real week for each. On a
-- live world nobody can move the calendar, not even the owner: the database
-- itself refuses.
--
-- Whether a world is a test world is decided once, when it is created, and
-- can never be changed afterwards.
ALTER TABLE world_state ADD COLUMN test_world boolean NOT NULL DEFAULT false;
ALTER TABLE world_state ADD COLUMN weeks_ahead integer NOT NULL DEFAULT 0 CHECK (weeks_ahead >= 0);

CREATE OR REPLACE FUNCTION world_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RAISE EXCEPTION 'The world cannot be removed.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'world_is_permanent';
    END IF;
    IF NEW.world_start <> OLD.world_start OR NEW.created_at <> OLD.created_at
       OR NEW.fortune_seed <> OLD.fortune_seed
       OR NEW.last_closed_period NOT IN (OLD.last_closed_period, OLD.last_closed_period + 1) THEN
        RAISE EXCEPTION 'The calendar only moves forward, one quarter at a time.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'world_is_permanent';
    END IF;
    IF NEW.test_world <> OLD.test_world THEN
        RAISE EXCEPTION 'A world is a test world or a live world for good.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'world_is_permanent';
    END IF;
    IF NEW.weeks_ahead <> OLD.weeks_ahead AND (NOT OLD.test_world OR NEW.weeks_ahead < OLD.weeks_ahead) THEN
        RAISE EXCEPTION 'Time can be moved forward on a test world only, and never back.'
            USING ERRCODE = 'restrict_violation', CONSTRAINT = 'live_calendar_is_fixed';
    END IF;
    RETURN NEW;
END;
$$;
