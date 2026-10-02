-- Stage 4, Part A, slice 3: a player's watchlist, with price alerts.
-- A player picks companies to keep an eye on and may set a price above or below
-- which they want to be told. Nobody else sees it.
CREATE TABLE watchlist (
    player_id    uuid NOT NULL REFERENCES players (id),
    company_id   uuid NOT NULL REFERENCES market_instruments (company_id),
    alert_above  bigint CHECK (alert_above > 0),      -- kobo a share: tell me when the price reaches this or more
    alert_below  bigint CHECK (alert_below > 0),      -- kobo a share: tell me when the price falls to this or less
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, company_id),
    CHECK (alert_above IS NULL OR alert_below IS NULL OR alert_above > alert_below)
);
