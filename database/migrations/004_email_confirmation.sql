-- One real, confirmed email address per account.
--
-- Two protections against one person opening many accounts to collect the
-- ₦500,000 starting grant many times:
--
--   1. Every address is reduced to its "key": the mailbox it really delivers to.
--      ada@gmail.com, Ada@Gmail.com, a.d.a@gmail.com and ada+second@gmail.com
--      all reach the same mailbox, so they share one key and only one of them
--      can hold an account.
--   2. An account, and its starting grant, only come into existence after the
--      person proves they can read mail sent to that address, by typing in a
--      code that was emailed to them.

ALTER TABLE players ADD COLUMN email_key text;
UPDATE players SET email_key = lower(email);
ALTER TABLE players ALTER COLUMN email_key SET NOT NULL;
CREATE UNIQUE INDEX players_email_key_unique ON players (email_key);

-- A sign-up that is waiting for its code. Nothing here is a player yet: no
-- account, no money. A row disappears when it is confirmed, replaced or expires.
CREATE TABLE pending_signups (
    email_key         text PRIMARY KEY,
    email             text NOT NULL,
    display_name      text NOT NULL,
    display_name_key  text NOT NULL,
    password_hash     text NOT NULL,
    profile_icon      text NOT NULL CHECK (profile_icon IN ('male', 'female')),
    -- The code itself is never stored, only a scrambled form of it.
    code_hash         text NOT NULL,
    wrong_guesses     integer NOT NULL DEFAULT 0,
    expires_at        timestamptz NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
