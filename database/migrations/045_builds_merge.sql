-- It lands with the code that writes three build names (simulation/world_data.py EMPIRE_BUILDS and
-- simulation/careers.py), so it is safe to run with the rest of the migrations.
--
-- The builds are merged from six into three, in the database.
--
-- simulation/careers.py was changed to describe three builds — Asset Manager, Risk Manager and
-- Investment Banker — with the Accountant's work folded into the Asset Manager, and the Legal
-- Counsel's and Financial Journalist's into the Investment Banker. Every table that has ever
-- held one of the three retired names still holds it, and every screen that looks a build up by
-- name now fails. This change moves the names.
--
-- Two rules, so that nothing that is a record of the past is rewritten:
--
--   * LIVE state is renamed: a player's build, a career, a job, work in hand, an open rank case,
--     a seat, a member who has not left, a duty not yet due, an opinion not yet answered.
--   * RECORDS are left exactly as they were written: a payslip, a career event, a desk's score
--     for a quarter, a judged rank case, a membership that has ended. Those say what happened at
--     the time, and the word that was true then is the honest word now. Each player whose career
--     moves gets one new event in their history saying why.
--
-- The accountancy, law and journalism a player had reached is not lost: where a player already
-- held the build their retired one becomes, the further of the two records is kept.
--
-- An empire goes from thirteen seats to seven: a head, and two for each of the three builds.
-- A player sitting in a retired seat moves to the same build's seat in the same empire where one
-- is free; where an empire is left with no one in a seat, computer-run staff hold it, as they do
-- in a newly opened empire, so that no empire loses a duty it used to have.

-- ---------------------------------------------------------------------------
-- The three names, and the build each becomes.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE build_merge (old text PRIMARY KEY, new text NOT NULL) ON COMMIT DROP;
INSERT INTO build_merge (old, new) VALUES
    ('accountant', 'asset_manager'),
    ('lawyer',     'investment_banker'),
    ('journalist', 'investment_banker');

-- ---------------------------------------------------------------------------
-- The player and their careers.
-- ---------------------------------------------------------------------------
UPDATE players p SET build = m.new
FROM build_merge m
WHERE p.build = m.old;

-- Where a player already holds the build a retired career becomes, the two records are folded
-- into one: the greater experience, the higher rank, the earlier start. Nothing is added up, so
-- nobody is carried two levels for holding two careers.
CREATE TEMP TABLE career_folds AS
SELECT c.player_id, m.new AS build,
       max(c.experience) AS experience, max(c.rank) AS rank, min(c.started_at) AS started_at
FROM careers c JOIN build_merge m ON m.old = c.build
GROUP BY c.player_id, m.new;

-- One line of history for every career that moves, before anything is folded away. The old name
-- is kept in the words, because that is the name the player chose and worked under.
INSERT INTO career_events (player_id, build, kind, words, at)
SELECT c.player_id, m.new, 'build_chosen',
       'The builds were merged: the ' || replace(c.build, '_', ' ') || ' build became part of the '
       || replace(m.new, '_', ' ') || ' build. The level, experience and rank cases already earned were kept.',
       now()
FROM careers c JOIN build_merge m ON m.old = c.build;

-- A player who held none of the merged build already gets one row to fold into; then every such
-- row takes the furthest of the records that fold into it.
INSERT INTO careers (player_id, build, experience, rank, started_at)
SELECT f.player_id, f.build, f.experience, f.rank, f.started_at
FROM career_folds f
WHERE NOT EXISTS (SELECT 1 FROM careers t WHERE t.player_id = f.player_id AND t.build = f.build);

UPDATE careers t SET experience = greatest(t.experience, f.experience),
                     rank       = greatest(t.rank, f.rank),
                     started_at = least(t.started_at, f.started_at)
FROM career_folds f
WHERE t.player_id = f.player_id AND t.build = f.build;

-- Only now, with every retired career folded into a row that survives, are the retired rows let
-- go. A review left open on one of them is dropped with it: the review belongs to work done under
-- a build that no longer exists.
DELETE FROM careers WHERE build IN (SELECT old FROM build_merge);

-- A job held under a retired build is the same job, done by the merged build.
UPDATE employments e SET build = m.new FROM build_merge m WHERE e.build = m.old;

-- ---------------------------------------------------------------------------
-- Work, past and in hand. Every piece of work belongs to the build it becomes, judged or not, so
-- that the syllabus and the mastery map are read from one list of three and not from a mix.
-- ---------------------------------------------------------------------------
-- Work is guarded as a permanent record (migration 015): its build cannot change once it is taken on. This is the one
-- time the game itself moves it, so the guard is lifted for this statement only and put back at once. The track (the
-- syllabus map the work counts towards) moves with it, or the work done would stop counting.
ALTER TABLE objectives DISABLE TRIGGER objectives_guarded;
UPDATE objectives o SET build = m.new FROM build_merge m WHERE o.build = m.old;
UPDATE objectives o SET track = m.new FROM build_merge m WHERE o.track = m.old;
ALTER TABLE objectives ENABLE TRIGGER objectives_guarded;

-- An open rank case moves to the merged track and is sat as it was, fee paid and all. A judged
-- case is a record.
UPDATE rank_cases r SET track = m.new
FROM build_merge m
WHERE r.track = m.old AND r.state = 'active';

-- ---------------------------------------------------------------------------
-- The empire: members who have not left, applications still waiting, steps in hand, titles,
-- apprentices and poaching offers.
-- ---------------------------------------------------------------------------
-- empire_members is NOT touched. Its guard forbids any change to a membership's build, open or
-- ended, and it is right to: the column records which build a player joined under, and nothing in
-- the game reads it back. Leaving it says what happened, which is what the table is for.

UPDATE empire_applications a SET build = m.new
FROM build_merge m
WHERE a.build = m.old AND a.status = 'waiting';

UPDATE empire_task_steps s SET build = m.new FROM build_merge m WHERE s.build = m.old;
UPDATE empire_apprentices a SET build = m.new FROM build_merge m WHERE a.build = m.old;
UPDATE poach_offers p SET build = m.new FROM build_merge m WHERE p.build = m.old;
UPDATE deal_steps d SET build = m.new FROM build_merge m WHERE d.build = m.old;

-- A title belongs to a desk, so two leads folding into one build are one lead too many. The
-- appointment already on the merged build keeps the title; failing that, the earliest does.
DELETE FROM empire_titles t
USING build_merge m
WHERE t.build = m.old AND t.title = 'lead'
  AND EXISTS (SELECT 1 FROM empire_titles other
              WHERE other.empire_id = t.empire_id AND other.title = 'lead' AND other.build = m.new);

WITH competing AS (
    SELECT t.empire_id, t.title, t.player_id,
           row_number() OVER (PARTITION BY t.empire_id, t.title, m.new ORDER BY t.since, t.player_id) AS place
    FROM empire_titles t JOIN build_merge m ON m.old = t.build
    WHERE t.title = 'lead'
)
DELETE FROM empire_titles t
USING competing c
WHERE t.empire_id = c.empire_id AND t.title = c.title AND t.player_id = c.player_id
  AND t.build IN (SELECT old FROM build_merge) AND c.place > 1;

UPDATE empire_titles t SET build = m.new FROM build_merge m WHERE t.build = m.old;

-- A duty not yet due, and an opinion not yet answered, are live; both guards allow this.
UPDATE desk_duties d SET build = m.new FROM build_merge m WHERE d.build = m.old AND d.status = 'due';
UPDATE signed_opinions s SET build = m.new FROM build_merge m WHERE s.build = m.old AND s.outcome IS NULL;

-- An audit done by the seat that signs the accounts now says so: the old word is dropped from the
-- list first, since adding the new one while the old list stood would be refused.
ALTER TABLE empire_audits DROP CONSTRAINT empire_audits_kind_check;
ALTER TABLE empire_audits ADD CONSTRAINT empire_audits_kind_check CHECK (kind IN ('asset_manager', 'staff', 'ai', 'report', 'firm'));
UPDATE empire_audits a SET kind = 'asset_manager' WHERE a.kind = 'accountant';

-- ---------------------------------------------------------------------------
-- Seven seats: a head, and two for each of the three builds.
-- ---------------------------------------------------------------------------
-- Every player in a retired seat moves to the same build's seat in the same empire, taken in
-- order so that two movers in one empire cannot be sent to the same place.
WITH movers AS (
    SELECT s.id, s.empire_id, s.player_id, m.new AS build,
           row_number() OVER (PARTITION BY s.empire_id, m.new ORDER BY s.slot, s.id) AS place
    FROM empire_seats s JOIN build_merge m ON m.old = s.build
    WHERE s.player_id IS NOT NULL
), free_seats AS (
    SELECT t.id, t.empire_id, t.build,
           row_number() OVER (PARTITION BY t.empire_id, t.build ORDER BY t.staffed, t.slot) AS place
    FROM empire_seats t
    WHERE t.player_id IS NULL
      AND t.build NOT IN (SELECT old FROM build_merge)
)
UPDATE empire_seats seat SET player_id = mv.player_id, signing_limit = NULL, since = now()
FROM movers mv
JOIN free_seats f ON f.empire_id = mv.empire_id AND f.build = mv.build AND f.place = mv.place
WHERE seat.id = f.id;

-- The retired seats go. A player who could not be placed keeps their membership — the empire is
-- still theirs — and simply sits in no seat, which the game already allows.
DELETE FROM empire_seats WHERE build IN (SELECT old FROM build_merge);

-- No empire loses a duty: where neither seat for a build is held by a player, computer-run staff
-- take the first.
UPDATE empire_seats seat SET staffed = true
WHERE seat.slot = 1 AND seat.player_id IS NULL AND NOT seat.staffed
  AND NOT EXISTS (SELECT 1 FROM empire_seats other
                  WHERE other.empire_id = seat.empire_id AND other.build = seat.build AND other.player_id IS NOT NULL);

-- Each empire says what happened to it, in its own log.
INSERT INTO empire_events (empire_id, words, at)
SELECT id, 'The builds were merged: an empire is now a head and two seats each for the asset manager, '
           'the risk manager and the investment banker. A seat for a build that no longer exists '
           'moved to the build it became.', now()
FROM empires WHERE status = 'active' AND kind <> 'pension';

-- ---------------------------------------------------------------------------
-- Three builds, and the database says so in one place.
-- ---------------------------------------------------------------------------
ALTER TABLE players DROP CONSTRAINT players_build_check;
ALTER TABLE players ADD CONSTRAINT players_build_check CHECK (build IN
    ('asset_manager', 'investment_banker', 'risk_manager'));

ALTER TABLE careers DROP CONSTRAINT careers_build_check;
ALTER TABLE careers ADD CONSTRAINT careers_build_check CHECK (build IN
    ('asset_manager', 'investment_banker', 'risk_manager'));

ALTER TABLE employments DROP CONSTRAINT employments_build_check;
ALTER TABLE employments ADD CONSTRAINT employments_build_check CHECK (build IN
    ('asset_manager', 'investment_banker', 'risk_manager'));

ALTER TABLE objectives DROP CONSTRAINT objectives_build_check;
ALTER TABLE objectives ADD CONSTRAINT objectives_build_check CHECK (build IN
    ('asset_manager', 'investment_banker', 'risk_manager'));

ALTER TABLE empire_seats DROP CONSTRAINT empire_seats_build_check;
ALTER TABLE empire_seats ADD CONSTRAINT empire_seats_build_check CHECK (build IN
    ('asset_manager', 'investment_banker', 'risk_manager'));
