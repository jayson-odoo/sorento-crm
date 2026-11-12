-- QUOTE-LINE-NOTE-REMARK (#2378) hand-test fixture. Runs AFTER 2339-non-cancellable.sql.
-- Puts line notes on proposal ZZT-NC-Q2 (signed and sent) so its PDF, Excel and sign link show
-- the REMARK column with a note. Fake text only. Idempotent: plain UPDATEs by fixed id.
-- ZZT-NC-TUB-A (Non-cancellable): a two-line note.
UPDATE projects.quotation_lines
   SET notes = E'Lead time 6 weeks\nDeliver to site store',
       updated_at = now()
 WHERE id = 'f1c70000-0000-4000-8000-000000000114'::UUID;
-- ZZT-NC-TAP-B (not flagged): a long note, to show it wraps and is never cut.
UPDATE projects.quotation_lines
   SET notes = 'Colour matt black. Fixture note for the hand test: this sentence is long on purpose so that it has to wrap over several lines in the REMARK cell, and the last words END OF NOTE must still be visible.',
       updated_at = now()
 WHERE id = 'f1c70000-0000-4000-8000-000000000115'::UUID;
