-- Stage 6: all builds, and empires.

-- ---------------------------------------------------------------------------
-- The other four builds a player may choose. (CEO is earned, never chosen.)
-- ---------------------------------------------------------------------------
ALTER TABLE players DROP CONSTRAINT players_build_check;
ALTER TABLE players ADD CONSTRAINT players_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
ALTER TABLE careers DROP CONSTRAINT careers_build_check;
ALTER TABLE careers ADD CONSTRAINT careers_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
ALTER TABLE employments DROP CONSTRAINT employments_build_check;
ALTER TABLE employments ADD CONSTRAINT employments_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
ALTER TABLE objectives DROP CONSTRAINT objectives_build_check;
ALTER TABLE objectives ADD CONSTRAINT objectives_build_check CHECK (build IN
    ('asset_manager', 'accountant', 'investment_banker', 'risk_manager', 'lawyer', 'journalist'));
