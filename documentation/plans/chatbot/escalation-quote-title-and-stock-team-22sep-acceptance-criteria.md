# UAC: escalation quote fallback, SLA comment timestamps, stock team

Plan: `PLAN-escalation-quote-title-and-stock-team-22sep.md`

## Quoted message in `source_message_text`

- AC-EQ-1 Customer message "Yes" quoting a message with `text` "Would you like me to escalate?" → `source_message_text` is `Yes reply to: Would you like me to escalate?`.
- AC-EQ-2 Same, quoted message carries only `title` (quick-reply shape) → `Yes reply to: <title>`.
- AC-EQ-3 Quoted message has neither text nor title (image with no caption) → `source_message_text` is exactly `Yes`; the string `undefined` never appears.

## Internal SLA comment

- AC-EQ-4 `_sla_create` given a tracking row whose `initiated_at` / `due_at` / `due_at_resolution` are `datetime` values → the comment reads `routed to you at 2026-09-22 14:34:00` (Asia/Kuala_Lumpur), and `[object Object]` never appears in any of the three lines.

## Suggested team for a stock question (domain_hint = inventory)

- AC-EQ-5 Stock row(s) qty 0 at every location, incoming empty, PO placed → offer sentence says `escalate to warehouse team?` and `parser["routing"]["suggested_team"] == "warehouse"`; `block["team"] == "warehouse"`.
- AC-EQ-6 No stock, no incoming, PO placed → same as AC-EQ-5.
- AC-EQ-7 No stock, incoming found, no PO → warehouse (unchanged behaviour, pinned).
- AC-EQ-8 No stock, no incoming, no PO → warehouse (unchanged, pinned).
- AC-EQ-9 Incoming-origin ask (domain_hint = incoming) that climbs to the PO rung → still `purchasing` (regression guard: the fix must not touch incoming-origin routing).
- AC-EQ-10 The PO "placed" line is still rendered when the PO rung answers (only the team word changes).
- AC-EQ-11 The pending offer's carried `team` (what a later bare "yes" routes to) is warehouse for a stock-origin ask, including after a did-you-mean product pick that climbs the full ladder to the PO rung.

## Suggested team when the parser names none (`routing.suggested_team = None`)

Reviewer fix round 1, B2: captured traffic shows the LLM parser names no team on a
real fraction of inventory turns (214/218, measured) - the MISS branch (no PO-rung
involved at all) must not fall through to the generic "customer_service" literal for
those. Owner ruling 22 Sep 2026, R6: deterministic post-LLM fill from the domain's own
`escalation_team_code` (`turn/policy_rows.py`), filled by `turn_runtime.
lane_parse_output` before any composer reads `routing.suggested_team`.

- AC-EQ-12 `domain_hint = inventory`, `routing.suggested_team = None`, no stock, no
  incoming, PO placed → `escalate to warehouse team?`.
- AC-EQ-13 Same, but nothing on any rung either → `escalate to warehouse team?`.
- AC-EQ-14 `domain_hint = incoming`, `routing.suggested_team = None`, PO placed →
  `escalate to purchasing team?`.

## AC-EQ-15 First-turn default table for a null `routing.suggested_team` (owner signed 23 Sep 2026)

Fix round 2, precedence signed off in fix round 3 (R7, below). The table is the full
set of first-turn defaults (no prior session, no accepted offer, no pending) - what
`lane_parse_output` falls back to when the verdict itself named no team, read off
`turn/policy_rows.py`'s `escalation_team_code` per domain, current as of fix round 3.
Not implemented differently by domain, this is `policy.domain(domain_hint).
escalation_team_code` for every row already:

| `domain_hint` | team |
| --- | --- |
| `inventory` | `warehouse` |
| `incoming` | `purchasing` |
| `master_products` | `purchasing` |
| `product_attachment` | `marketing_product` (a resolved CERTIFICATE attachment type still overrides to `purchasing_certification` via the existing `answer_parse_output` special-case - unaffected, unchanged) |
| `promotion` | `marketing_promotion` |
| `forms` | `marketing_form` |
| `purchase_order` | `purchasing` |
| `purchase_cost` | `purchasing` |
| `order` | `customer_service` (unchanged) |
| everything else / unknown / `None` (`portal_link`, `resource_attachment`, `goods_receive`, `spo_allocation`, `ideate` - each has `escalation_team_code: None` on its own row - or a `domain_hint` `policy.domain()` cannot resolve at all) | `customer_service` (unchanged) |

- AC-EQ-15a `domain_hint = master_products`, `routing.suggested_team = None`, no
  prior session, no accepted offer → the domain fallback names `purchasing`.

## Precedence when a prior turn ALSO carried a team (owner ruling 23 Sep 2026, R7)

R7 = option (a): THIS turn's own domain team (the AC-EQ-15 table above) now
outranks a PREVIOUS turn's carried team (`_prior_suggested_team`) - a turn that named
a real domain is a fresher fact than a stale carried session.

- AC-EQ-16 Prior turn carried `purchasing` (e.g. an incoming ask); current turn
  `domain_hint = inventory`, `routing.suggested_team = None`, no pending offer →
  `warehouse` (the domain wins over the stale carry).
- AC-EQ-17 Prior `warehouse`, current `domain_hint = incoming`, routing null, no
  open offer → `purchasing` (the mirror of AC-EQ-16). A direct unit shape only - NOT
  `replay_turns/console/case-025-d7-...`'s own recorded shape: that case's
  `prior_session` is `None` throughout (R7 never engages there at all); its turn 1
  is an OPEN-OFFER shape, AC-EQ-20's, not this one.
- AC-EQ-19 Prior `purchasing`, current turn `domain_hint = None`/unknown, routing
  null → `purchasing` (the carry still applies when this turn names no resolvable
  domain at all).

## Open-offer precedence for a FRESH question (owner ruling 23 Sep 2026, R9)

R9 = option (i): an OPEN offer's own carried team wins ONLY when THIS turn is
actually ANSWERING it - a bare "yes" (`is_affirmative`), an explicit escalation
confirmation (`escalation.is_escalation_confirmation`), or a numbered pick landing
on one of the offer's own options. A FRESH question in another domain - not an
acceptance - gets its OWN domain team instead, never a silent inheritance of
whatever was last offered.

**S10 (fix round 6, "simplest thing that works"):** `lane_parse_output` has no
separate open-offer arm at all - `turn/apply.py::_answer_pending` already makes
EXACTLY this acceptance judgement and stamps it onto `trace.team`, which
`engine.py` passes in as `accepted_team` (the chain's first read, above R9's own
rung). A `pending.team` arm judging the same fact a second time, off `pending`
directly, was reviewer-kill-tested and deleted - the full suite stays green with
only `accepted_team` (never a bare `pending=`) as the acceptance path. Full chain:
accepted team (satisfies R9) > named team (this turn's own) > THIS turn's domain
team > prior-turn carried team > the hard default (`customer_service`).

`replay_turns/console/case-025-d7-...` turn 1 (D7's own climb, an incoming ask
following turn 0's stock offer) is the recorded example of the NEGATIVE case: it is
NOT an acceptance of turn 0's offer, so `apply()` passes no `accepted_team` and it
renders `escalate to purchasing team?` - the domain fill, and exactly the recorded
value. Turn 0 itself stays stale (warehouse, per R6/R7) - see
`PENDING-LIVE-RERUN.md`'s own note.

- AC-EQ-18 **Folded into AC-EQ-20** (fix round 6): a stock-domain version of the
  same fresh-question shape (`purchasing` team_pick open, current turn inventory,
  not an acceptance → `warehouse`) is byte-identical to AC-EQ-20 once there is no
  open-offer arm left to distinguish domain from kind - no longer a separate test.
- AC-EQ-20 `pending` passed (an open `team_pick`, team `warehouse`, from a stock
  offer) but NO `accepted_team` - current turn `domain_hint = incoming`, routing
  null (a fresh question, case-025 turn 1's own shape, the production caller never
  sets `accepted_team` for a turn `apply()` did not call an acceptance) →
  `purchasing`, THIS turn's own domain.
- AC-EQ-21 `accepted_team` IS set (the production shape: `apply()` called this
  turn an acceptance and stamped `trace.team`) → that team wins whatever THIS
  turn's own `domain_hint` is (checked against `incoming` and `None`).
- AC-EQ-22 A NUMBERED pick landing on one of a multi-team offer's own OPTIONS can
  name a team different from the pending's own blanket `team`
  (`option_payload.get("team") or pending.team`, contract 108) - `accepted_team`
  carries that OPTION's own team, and it wins over both the pending's blanket team
  and this turn's own domain.
