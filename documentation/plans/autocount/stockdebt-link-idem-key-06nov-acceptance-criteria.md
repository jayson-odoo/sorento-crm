# UAC: STOCKDEBT-LINK-IDEM-KEY

- U1 Link refused by AutoCount, then pressed again with the same lines: a new Idempotency-Key is sent
  and a `done` answer is applied.
- U2 Every further refusal moves the next press to another new key.
- U3 Timeout, `pending_verification`, `needs_attention`, `vendor_error`, `IDEMPOTENCY_IN_PROGRESS`,
  `IDEMPOTENCY_CONFLICT`: the next press sends the same key (replay, never a second split).
- U4 A refusal of one intent (qty 120) does not change another intent's key (qty 100).
- U5 Unlink and Move (relink) behave like U1.
- U6 Redis down: the write still goes, on the plain intent key.
- U7 A `VENDOR_UNSUPPORTED` stored before this lane (SS replays it on the first key) is asked again
  in the same press on the next attempt; a `done` answer is applied. A live one is asked again only
  once per press. Other refusals are never sent twice in one press.
- U8 Every SS write of one press carries the same `X-Request-ID`; the next press carries another.
- U9 (B12) Whole-row link, change link, unlink and split, each with the ingest push landing before
  AND after the answer: the PO has exactly one CRM line per AutoCount row, open, not removed,
  refs unique; the line that was replaced keeps its CRM id and is never released as removed.
- U10 (B12) Redis down, ingest first: still one line, same id, the ingest's claim moved onto it
  (its OI links released by the ingest are the documented loss).
- U11 (B12) No hint, two candidates, or another qty / SO link: ingest does not pair (removal +
  create, as before). A refused replace drops its hint.
- U12 (B13) An unlink answered with `FromSODtlKey 0` clears the CRM line's `from_so_line_ref`. A PO
  ingest push naming SO DtlKey 0 (`db:doc:0`) clears it like `null`; an absent field keeps it.
  SS still omits an empty link from its push (lane SS-PO-LINK-NULL), so an unlink made in
  AutoCount itself stays stale in the CRM until that SS lane lands.
