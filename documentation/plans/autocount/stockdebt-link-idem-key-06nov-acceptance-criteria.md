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
