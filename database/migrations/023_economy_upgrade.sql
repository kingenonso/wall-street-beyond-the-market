-- The economy upgrade (owner, 12 October 2026).
--
--   consumer_groups    1,000 groups of households. Each lives in one location, earns at one of five
--                      income levels, thinks in one of the ten mindsets, and has its own savings, debts
--                      and taste for each kind of good. The money itself stays in each location's
--                      household account: a group's savings and debts are its share of them.
--                      Private to the simulation: no player ever sees one group.
--   consumer_results   each quarter, the groups added up by location, income level and mindset.
--   consumer_moves     how many groups moved from one location to another each quarter.
--   abroad_results     the rest of the world, quarter by quarter: the oil price, the naira's
--                      exchange rate, what was bought and sold abroad, and the foreign investors.
--                      A row is written when a quarter closes and holds the figures for the NEXT
--                      quarter's oil price and exchange rate, which are public from that moment.

CREATE TABLE consumer_groups (
    id           integer PRIMARY KEY CHECK (id >= 1),
    location     text NOT NULL REFERENCES locations (name),
    band         text NOT NULL CHECK (band IN ('low', 'lower_middle', 'middle', 'upper_middle', 'high')),
    mindset      text NOT NULL,
    earns_bps    integer NOT NULL CHECK (earns_bps > 0),
    tastes       jsonb NOT NULL,             -- sector -> how much more or less it spends there (10000 = average)
    cash         bigint NOT NULL CHECK (cash >= 0),
    debt         bigint NOT NULL CHECK (debt >= 0),
    income       bigint NOT NULL DEFAULT 0,  -- last quarter
    spending     bigint NOT NULL DEFAULT 0,  -- last quarter
    moved_period integer
);
CREATE INDEX consumer_groups_by_location ON consumer_groups (location);

CREATE TABLE consumer_results (
    period    integer NOT NULL CHECK (period >= 0),
    location  text NOT NULL REFERENCES locations (name),
    band      text NOT NULL,
    mindset   text NOT NULL,
    groups    integer NOT NULL,
    income    bigint NOT NULL,
    spending  bigint NOT NULL,
    cash      bigint NOT NULL,
    debt      bigint NOT NULL,
    PRIMARY KEY (period, location, band, mindset)
);
CREATE TRIGGER consumer_results_permanent BEFORE UPDATE OR DELETE ON consumer_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE consumer_moves (
    period        integer NOT NULL CHECK (period >= 1),
    from_location text NOT NULL REFERENCES locations (name),
    to_location   text NOT NULL REFERENCES locations (name),
    groups        integer NOT NULL CHECK (groups > 0),
    PRIMARY KEY (period, from_location, to_location)
);
CREATE TRIGGER consumer_moves_permanent BEFORE UPDATE OR DELETE ON consumer_moves
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

CREATE TABLE abroad_results (
    period          integer PRIMARY KEY CHECK (period >= 0),
    oil_cents       integer NOT NULL CHECK (oil_cents > 0),     -- next quarter's oil price, US cents a barrel
    fx              integer NOT NULL CHECK (fx > 0),            -- next quarter's naira to one US dollar, in hundredths
    exports         bigint NOT NULL DEFAULT 0,                  -- what the rest of the world bought this quarter
    oil_exports     bigint NOT NULL DEFAULT 0,
    imports         bigint NOT NULL DEFAULT 0,                  -- what companies bought from abroad this quarter
    oil_royalty     bigint NOT NULL DEFAULT 0,
    reserve         bigint NOT NULL DEFAULT 0,                  -- naira the rest of the world holds at the close
    foreign_inflow  bigint NOT NULL DEFAULT 0,                  -- sent in by foreign investors (negative: taken out)
    foreign_cash    bigint NOT NULL DEFAULT 0,
    foreign_shares  bigint NOT NULL DEFAULT 0,                  -- what their shares were worth at the close
    foreign_bought  bigint NOT NULL DEFAULT 0,                  -- shares bought on the exchange during the quarter
    foreign_sold    bigint NOT NULL DEFAULT 0,
    tilt_bps        integer NOT NULL DEFAULT 0,                 -- how keen they are next quarter (+ to buy, - to sell)
    last_trade_id   bigint NOT NULL DEFAULT 0,                  -- the exchange's last trade at the close
    export_base     bigint NOT NULL,                            -- what the world bought in an opening quarter, at opening prices
    reason          text NOT NULL DEFAULT ''
);
CREATE TRIGGER abroad_results_permanent BEFORE UPDATE OR DELETE ON abroad_results
    FOR EACH ROW EXECUTE FUNCTION records_forbid_change();

-- The rest of the world has an account of its own.
ALTER TABLE ledger_accounts DROP CONSTRAINT ledger_accounts_kind_check;
ALTER TABLE ledger_accounts ADD CONSTRAINT ledger_accounts_kind_check CHECK (kind IN (
    'central_bank', 'government', 'prize_pool', 'npc_public', 'npc_investors', 'company', 'player', 'exchange', 'empire', 'fund',
    'escrow', 'firm', 'rest_of_world'));
