-- PLAN-BATCH-HELD-CANCEL hand-test cleanup: LOCAL dev copy sorento_prod_1020 ONLY.
-- Removes the 12 seeded drafts if the hand test did not press Confirm (a Confirm deletes them
-- itself, project_supply_service.py cancel_lines -> delete_drafts_for_lines).
-- A pressed Confirm is NOT undone here: SO394881's batch rows, its 12 lines (Cancel SO) and its
-- order inquiry rows changed on purpose. Re-copy the database to get that state back.
BEGIN;
DELETE FROM projects.so_supply_decision_drafts
WHERE decision->>'reason' = 'AutoCount Cancel SO ZZT-HANDTEST-1817';
COMMIT;
