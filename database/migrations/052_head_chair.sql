-- The head's own chair (the owner's seven places: two seats for each of the three builds, and the head above them).
-- A founder sat in one of the two seats of their own build, so an empire headed by an Asset Manager had room for only
-- one more. The founder's chair is slot 0 now; slots 1 and 2 of every build are for the members.
ALTER TABLE empire_seats DROP CONSTRAINT IF EXISTS empire_seats_slot_check;
ALTER TABLE empire_seats ADD CONSTRAINT empire_seats_slot_check CHECK (slot BETWEEN 0 AND 6);

DO $$
DECLARE s record;
BEGIN
    FOR s IN SELECT es.* FROM empire_seats es JOIN empires e ON e.id = es.empire_id
             WHERE e.kind = 'player' AND es.player_id = e.head_player_id AND es.slot BETWEEN 1 AND 2
    LOOP
        UPDATE empire_seats SET player_id = NULL, since = NULL, signing_limit = NULL WHERE id = s.id;
        INSERT INTO empire_seats (empire_id, build, slot, player_id, staffed, since, signing_limit)
        VALUES (s.empire_id, s.build, 0, s.player_id, false, s.since, s.signing_limit);
    END LOOP;
END $$;
