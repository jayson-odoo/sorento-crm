# UAC: AutoCount-removed lines stay Cancelled

- AC-KC-1: a PO line with a DtlKey that a push no longer carries, with nothing pointing at
  it, ends Cancelled and still exists.
- AC-KC-2: a line already Cancelled and absent again on a later push still exists and stays
  Cancelled.
- AC-KC-3: push 1 removes a linked PO line (links/claims released), push 2 of the same
  reduced PO: the line still exists, Cancelled, with no links.
- AC-KC-4: the same holds for an SO line.
- AC-KC-5: a ref-less (xlsx-era) leftover nothing points at is still deleted (unchanged).
- AC-KC-6: the recovery script, given a snapshot holding a line the live DB lost, lists it
  in dry run and writes nothing; with `--apply` it re-inserts it Cancelled. A line whose
  document is gone, or whose ref is live, is not restored.
