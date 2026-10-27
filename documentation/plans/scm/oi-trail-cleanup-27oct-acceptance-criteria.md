# UAC: OI trail cleanup (lane OI-TRAIL-CLEANUP)

- AC-TC-01: after the migration, a sheet-migrated line's decision trail shows no "Reconfirmed"
  event that the 20 Sep upload's shifted stamp produced, and its rows' acknowledged time equals
  the real import time (8 h earlier than before).
- AC-TC-02: a genuine reconfirm (any time not equal to an affected upload's stamp, by anyone)
  is kept, including one by the uploader hours after the import.
- AC-TC-03: rows stamped with an affected upload's exact value in `actioned_at` / `changed_at`
  move back 8 h too; a row one microsecond off does not move.
- AC-TC-04: a second run changes nothing, and rerunning 523's `backfill_raises` writes nothing.
- AC-TC-05: the migration logs its counts; the downgrade is documented as a no-op with the
  pre-migrate dump as the real rollback.
- AC-TC-06: dry run on a throwaway copy of sorento_prod_1020 reports counts in line with the
  crew measurement (649 + 50 reconfirm rows, about 9,201 acknowledged rows) and SO400884's trail
  loses its "Reconfirmed" entry.
- AC-TC-07: rows from an upload that left no fake reconfirm move back 8 h too when that
  upload's own `order_inquiry_import` job ties them (job window holds the stamp minus 8 h and
  the row's birth, same uploader); the same shape with no job behind it does not move.
