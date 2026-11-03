-- The talent and funds stage, Part 4c: six new industries.
-- Medicines and healthcare, groceries and retail, technology and payments, film and entertainment,
-- solid minerals and mining, and fertilisers and agro-chemicals: twenty-four companies, six baskets
-- on the exchange, and eight new kinds of event with their own news and pop-ups.
--
-- Only one thing in the database had to change. Sectors are written from the catalogue when a world
-- is made, the companies come with them, and the six baskets are written from the index list, so
-- none of those needs a change here. But the table of events names every kind of event it may hold,
-- in a check made when the table was first written (008_macro.sql). A world holding this stage's
-- events would have been stopped by the database the first time a drug shortage or a mine accident
-- happened: not a lost headline, a failed quarter. So the list is rewritten with the eight added.
--
-- The six new sectors are added to that same list only through `sectors`, which takes any code, so
-- a world made before this stage keeps its own rows and picks the new ones up when it is remade.

ALTER TABLE events DROP CONSTRAINT IF EXISTS events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    -- The world as it first stood (008_macro.sql).
    'flood', 'power_failure', 'security_incident', 'port_disruption', 'pipeline_incident', 'drought',
    'local_boom', 'sector_strike', 'sector_demand_surge', 'good_harvest', 'network_outage',
    'new_competition', 'company_strike', 'scandal', 'contract_win', 'factory_fire', 'product_recall',
    'new_product', 'energy_price_jump', 'energy_price_fall', 'metals_price_jump', 'metals_price_fall',
    'materials_shortage',
    -- Part 4c: the six new industries.
    'drug_shortage', 'payments_outage', 'bumper_harvest',
    'bad_batch', 'mine_accident', 'seam_runs_out', 'film_flops', 'film_hit'));

-- The news wire already takes any kind of story (news_items.kind has no list to keep up to date),
-- and a story's industries are held as text, so nothing there needed changing either.
