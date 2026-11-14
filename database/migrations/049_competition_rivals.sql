-- Competition, part 2 (owner, 14 November 2026): work aimed at rival empires, and the league as the scoreboard.
--
-- Calls on rivals. An empire's Asset Manager (or head) can call a rival empire's company overvalued: its share price
-- will fall by a tenth within two quarters. An empire's Risk Manager (or head) can call a rival empire's bank weak: its
-- credit rating will be cut within two quarters. A rival's company or bank is one in which another empire holds at
-- least a twentieth of the shares. A call is public from the moment it is made, so the rival sees it coming. The record
-- judges it: right, and the caller's empire gains points and the rival's loses some; wrong, and the caller's loses.
--
-- Defence mandates. When a company is the target of a hostile takeover bid, it invites every empire to pitch to defend
-- it, as a company selling shares does (part 1). The winner is paid its fee only if the bid fails.

CREATE TABLE rival_calls (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text NOT NULL CHECK (kind IN ('overvalued', 'weak_bank')),
    empire_id        bigint NOT NULL REFERENCES empires (id),
    player_id        uuid NOT NULL REFERENCES players (id),
    company_id       uuid NOT NULL REFERENCES companies (id),
    rival_id         bigint NOT NULL REFERENCES empires (id),     -- the empire whose company or bank it is
    rival_stake_bps  integer NOT NULL,
    period           integer NOT NULL,                            -- made in this quarter...
    ends_period      integer NOT NULL,                            -- ...and judged when this one closes
    from_price       bigint,                                      -- overvalued: the share price when the call was made
    from_rating      text,                                        -- weak_bank: the rating when the call was made
    status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'right', 'wrong', 'void')),
    outcome          text,
    at               timestamptz NOT NULL,
    CHECK (empire_id <> rival_id),
    CHECK (ends_period >= period)
);
CREATE UNIQUE INDEX rival_calls_one_open ON rival_calls (empire_id, company_id) WHERE status = 'open';
CREATE INDEX rival_calls_due ON rival_calls (ends_period) WHERE status = 'open';

CREATE FUNCTION rival_call_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'A call is a permanent record.' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.kind <> OLD.kind OR NEW.company_id <> OLD.company_id OR NEW.empire_id <> OLD.empire_id
       OR NEW.from_price IS DISTINCT FROM OLD.from_price OR NEW.from_rating IS DISTINCT FROM OLD.from_rating
       OR NEW.ends_period <> OLD.ends_period OR NEW.at <> OLD.at THEN
        RAISE EXCEPTION 'A call cannot be changed once it is made.' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER rival_calls_sealed BEFORE UPDATE OR DELETE ON rival_calls FOR EACH ROW EXECUTE FUNCTION rival_call_sealed();

-- A mandate is now for a sale of shares or for defending against a takeover.
ALTER TABLE mandates ALTER COLUMN offer_id DROP NOT NULL;
ALTER TABLE mandates ADD COLUMN takeover_id bigint UNIQUE REFERENCES takeovers (id);
ALTER TABLE mandates ADD COLUMN kind text NOT NULL DEFAULT 'sale' CHECK (kind IN ('sale', 'defence'));
ALTER TABLE mandates ADD CONSTRAINT mandates_one_subject
    CHECK ((kind = 'sale' AND offer_id IS NOT NULL AND takeover_id IS NULL)
           OR (kind = 'defence' AND takeover_id IS NOT NULL AND offer_id IS NULL));
