-- The newsroom's work is its own syllabus map, open to every build (owner, 14 November 2026: "approve the tasks").
--
-- Journalism was the Financial Journalist's, then (when six builds became three) the Investment Banker's. It is now a
-- track of its own: anyone with a build can take it, and the experience goes to their own build. Work already done in
-- it moves to the newsroom's map, so nobody loses what they have learned there. Nothing else about the work changes:
-- who did it, for whom, what it paid, and how it was judged all stay as they were written.
ALTER TABLE objectives DISABLE TRIGGER objectives_guarded;
UPDATE objectives SET track = 'newsroom' WHERE root LIKE 'jn\_%' OR root LIKE 'jr\_%';
ALTER TABLE objectives ENABLE TRIGGER objectives_guarded;
