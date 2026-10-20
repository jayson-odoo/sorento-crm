# PLAN: kind pick keeps the hinted kind on an exact hit and asks only typed tokens

Status: Build, small fix track (no migration, no auth change, expected diff under 300 lines). Owner: CHAT-CODE-LOOKUP
(crew brief 20 Oct ~22:30; owner OK: code only, no paid runs without a crew cap). Branch `crew/ccl-kind-pick`,
stacked on `crew/chat-state-r2` (#1772) because the fix needs #1772's `exact` whole-token map in
`turn/reconcile.py::apply_reconciliation` and its call site `turn/apply.py:1816`, which #1761 (based on main) lacks.

## Problem

Owner exploratory run 20 Oct (evidence local only: crew/state/eval/cp0/explore1020/owner-run-1020.md section (b)):
`apply_reconciliation` arms a "did you mean X (promotion) / X (product)" kind pick on any token with hits in more
than one kind, and keeps the parser's own kind only for order / PO reference hints (REFERENCE_NARROW). T15: a typed
product code that is also linked to a promotion asked instead of settling. T8: the token was a held product a seam
injected with `current_message` true; the customer never typed it.

## Design

- When the parser hinted a kind and that kind is the ONLY kind with an exact whole-token hit (`exact`; with
  exact=None every hit counts as exact), that kind wins: no kind pick. Two exact kinds still ask (REF-PROBES AC-13
  purchase_order vs customer_po_ref, the F1b "Sorento" customer / transporter pick); REFERENCE_NARROW is unchanged.
  Measured: a promotion is never an exact whole-token hit (entity_resolver.py's promotion probes are prefix,
  substring, trgm and and matches), so a typed product code linked to a promotion settles (T15).
- The kind pick offers only tokens typed THIS message: `apply_reconciliation(..., typed=...)` receives the folded
  own text (`turn.state.token_key` of the customer's own lines up to the `reply to:` block, plus the codes read from
  the turn's media), built once per turn by `engine._typed_text(user_turn)` and threaded engine -> `apply` ->
  `_reconcile_step`; a token is typed when its folded raw is inside it; a held or carried token is never asked
  about. `typed=None` keeps today's behaviour.

ARCHITECTURE: layer = reconcile (code after the parser, before the fetch). Shared mechanism: the hinted-kind rule
reads the exact map for every kind, and the pick reads the message's own words instead of a seam-settable flag.
Other classes it fixes (UNVERIFIED until measured): any seam-injected token (held_family, carried subject rows)
that hits two kinds; any product code linked to a promotion or an attachment type. Removes: the reference-only
special case in favour of one rule for every hinted kind.

## Gate

Red-first unit tests from the owner shapes (codes / ids only), kill proof, reviewer. $0 delta: parser gold is
unchanged by construction (reconcile runs after the parser); L1 replay base `crew/chat-state-r2` vs head.
