-- Companies have good times and bad times (design document, section 11).
--
-- Each company has its own steadiness: how far a single quarter can swing above
-- or below its usual. 300 = up to 3% either way.
ALTER TABLE companies ADD COLUMN volatility_bps integer NOT NULL DEFAULT 0
    CHECK (volatility_bps BETWEEN 0 AND 5000);

-- The world's own secret, chosen at random when the world is created. Each
-- quarter's good and bad fortune is worked out from it, so nobody outside the
-- server can work out next quarter's results in advance, yet the same quarter
-- always gives the same answer if it is ever re-checked.
ALTER TABLE world_state ADD COLUMN fortune_seed text;
-- A world that already exists is given a random secret now. (A world with no
-- secret would have fortunes anybody could work out from the game's code.)
UPDATE world_state SET fortune_seed = replace(gen_random_uuid()::text, '-', '');
ALTER TABLE world_state ALTER COLUMN fortune_seed SET NOT NULL;
ALTER TABLE world_state ADD CONSTRAINT world_secret_is_long CHECK (length(fortune_seed) >= 32);

-- The secret, like the start date, can never be changed once the world exists.
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
    RETURN NEW;
END;
$$;
