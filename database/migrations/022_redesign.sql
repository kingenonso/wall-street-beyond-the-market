-- The front-end redesign (owner, 12 October 2026).
--
--   theme          dark (the starting look) or light, the player's own choice
--   sound          on at a low volume by default; only for the player's own events
--   tour_done      the first-time walkthrough of a piece of work is shown once, on whichever device

ALTER TABLE players ADD COLUMN theme text NOT NULL DEFAULT 'dark' CHECK (theme IN ('dark', 'light'));
ALTER TABLE players ADD COLUMN sound_on boolean NOT NULL DEFAULT true;
ALTER TABLE players ADD COLUMN sound_volume smallint NOT NULL DEFAULT 30 CHECK (sound_volume BETWEEN 0 AND 100);
ALTER TABLE players ADD COLUMN tour_done boolean NOT NULL DEFAULT false;

-- The small trend lines beside prices read only the market's last few trading days.
CREATE INDEX market_trades_by_day ON market_trades (session_date);
