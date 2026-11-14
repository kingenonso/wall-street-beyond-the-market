-- One audit of the books a quarter for each auditor. The rule matched audits named 'accountant'; the three builds renamed
-- them 'asset_manager' (045), so it no longer held and an Asset Manager could audit again and again in one quarter.
-- Audits already made stay as they are (the record is never rewritten): the rule holds for every audit from now on.
DROP INDEX IF EXISTS empire_audits_one_each_quarter;
DO $$
BEGIN
    EXECUTE format('CREATE UNIQUE INDEX empire_audits_one_each_quarter ON empire_audits (empire_id, auditor_id, period)'
                   ' WHERE kind = ''asset_manager'' AND id > %s', (SELECT coalesce(max(id), 0) FROM empire_audits));
END $$;
