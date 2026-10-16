-- The gap stage, Part 1: the clearing house for options and futures.
--
-- Players' orders are matched with each other (and with the market makers' standing quotes) by the order-matching
-- engine. The clearing house stands between the two sides: every settlement passes through it, and a default fund paid
-- for by a slice of the trading fees covers anyone who cannot pay. The market makers' own side of every trade is now
-- recorded as a position too, so the two sides of every contract always add up to nothing.

-- Orders waiting in a contract's book. Cash for the order (its price, or its margin, and its fee) is held while it waits.
CREATE TABLE derivative_orders (
    id            bigserial PRIMARY KEY,
    account       uuid NOT NULL REFERENCES ledger_accounts (id),
    series_id     bigint NOT NULL REFERENCES derivative_series (id),
    side          text NOT NULL CHECK (side IN ('buy', 'sell')),
    limit_price   bigint NOT NULL CHECK (limit_price > 0),      -- a contract's price, in kobo
    contracts     integer NOT NULL CHECK (contracts > 0),
    remaining     integer NOT NULL CHECK (remaining >= 0),
    per_contract  bigint NOT NULL CHECK (per_contract >= 0),    -- cash held for each contract still waiting
    reserved      bigint NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'filled', 'cancelled', 'expired')),
    placed_by     uuid REFERENCES players (id),
    purpose       text,
    at            timestamptz NOT NULL,
    closed_at     timestamptz
);
CREATE INDEX derivative_orders_book ON derivative_orders (series_id, side, limit_price) WHERE status = 'open';
CREATE INDEX derivative_orders_account ON derivative_orders (account) WHERE status = 'open';

-- Every matched trade. The price is public; who traded is kept for the record and never sent.
CREATE TABLE derivative_trades (
    id         bigserial PRIMARY KEY,
    series_id  bigint NOT NULL REFERENCES derivative_series (id),
    price      bigint NOT NULL,
    contracts  integer NOT NULL CHECK (contracts > 0),
    buyer      uuid NOT NULL REFERENCES ledger_accounts (id),
    seller     uuid NOT NULL REFERENCES ledger_accounts (id),
    with_makers boolean NOT NULL,
    at         timestamptz NOT NULL
);
CREATE INDEX derivative_trades_series ON derivative_trades (series_id, id DESC);

-- What a position has made or lost so far in cash (premiums, settlements, variation), so a position closed in pieces
-- is still scored as a whole.
ALTER TABLE derivative_positions ADD COLUMN realised bigint NOT NULL DEFAULT 0;
ALTER TABLE derivative_positions ADD COLUMN by_makers boolean NOT NULL DEFAULT false;
-- Settled in cash every night with no margin held: the market makers' side, and companies hedging (on their banks' credit).
ALTER TABLE derivative_positions ADD COLUMN cash_settled boolean NOT NULL DEFAULT false;
-- A future's settlement price: every open position in the series is marked to it (set at the first trade, then nightly).
ALTER TABLE derivative_series ADD COLUMN mark bigint;

-- The default fund's own record: fees in, cover paid out (who was covered is kept, never sent).
CREATE TABLE clearing_fund_events (
    id        bigserial PRIMARY KEY,
    kind      text NOT NULL CHECK (kind IN ('fee', 'cover', 'repaid')),
    amount    bigint NOT NULL CHECK (amount > 0),
    account   uuid REFERENCES ledger_accounts (id),
    words     text NOT NULL,
    at        timestamptz NOT NULL
);

-- Short sales stopped by the Securities Regulator (a rule-based stand-in until the Government stage).
CREATE TABLE short_bans (
    id          bigserial PRIMARY KEY,
    company_id  uuid REFERENCES companies (id),          -- none: the whole market
    from_day    date NOT NULL,
    until_day   date NOT NULL,                           -- the last day the ban applies
    reason      text NOT NULL,
    at          timestamptz NOT NULL
);
CREATE INDEX short_bans_days ON short_bans (until_day);

-- Positions opened before this change were dealt with the market makers without recording their side. Record it now,
-- so every open contract has its two sides.
INSERT INTO derivative_positions (account, series_id, side, contracts, entry_price, mark, margin, purpose, opened_by, status,
                                  opened_at, realised, by_makers, cash_settled)
SELECT (SELECT id FROM ledger_accounts WHERE code = 'investors:institutions'), p.series_id,
       CASE p.side WHEN 'long' THEN 'short' ELSE 'long' END, p.contracts, p.entry_price, p.mark, 0, NULL, NULL, 'open',
       p.opened_at,
       CASE WHEN s.kind = 'future' THEN 0 WHEN p.side = 'long' THEN p.entry_price * p.contracts ELSE -p.entry_price * p.contracts END,
       true, true
FROM derivative_positions p JOIN derivative_series s ON s.id = p.series_id
WHERE p.status = 'open';
UPDATE derivative_positions p SET realised = CASE WHEN s.kind = 'future' THEN 0 WHEN p.side = 'long' THEN -p.entry_price * p.contracts
                                                  ELSE p.entry_price * p.contracts END
FROM derivative_series s WHERE s.id = p.series_id AND p.status = 'open' AND NOT p.by_makers;
