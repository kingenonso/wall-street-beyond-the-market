-- Stage 1: the players table.
-- One row per person. A player has one identity for life (design document, section 6).

CREATE TABLE players (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email               text NOT NULL,
    display_name        text NOT NULL,
    password_hash       text NOT NULL,

    -- The game is for adults aged 18 and above. We check the date of birth at
    -- sign-up and keep only the moment the check passed, not the birthday itself.
    adult_confirmed_at  timestamptz NOT NULL,

    -- Everyone starts at 50 out of 100.
    reputation          integer NOT NULL DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),

    -- TEMPORARY STAND-IN (replaced in Stage 2 by the ledger, which will own all money).
    -- Money is stored in kobo (1 naira = 100 kobo) as a whole number, so no rounding
    -- errors can creep in. The currency is stored beside every amount from day one.
    opening_cash_kobo   bigint NOT NULL DEFAULT 50000000 CHECK (opening_cash_kobo >= 0),
    currency            char(3) NOT NULL DEFAULT 'NGN',

    created_at          timestamptz NOT NULL DEFAULT now()
);

-- No two players may share an email or a display name, ignoring capital letters.
CREATE UNIQUE INDEX players_email_unique ON players (lower(email));
CREATE UNIQUE INDEX players_display_name_unique ON players (lower(display_name));
