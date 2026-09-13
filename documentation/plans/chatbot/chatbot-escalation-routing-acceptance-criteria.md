# UAC - Chatbot escalation routing

Plan: `PLAN-chatbot-escalation-routing.md`. Numbering: AC-11xx. Each criterion names its
evidence (pytest / replay / console). "Contact" = a Respond.io contact through
`/api/v1/external/chat/turn`; "family word" = a team word that names several catalogue teams
("marketing" -> marketing_product, marketing_promotion, marketing_form).

## Journey

Actor: a dealer's purchaser on WhatsApp, a Sorento-company contact. She types short, capitalised,
sometimes misspelt messages, and expects "escalate to marketing" to reach a marketing person
who handles the brand she is asking about.

1. She types `ESCALTE TO MARKETING BIDET SEAT COVER FOR SRTWC60630-SH` while the bot still has
   yesterday's suggestion list open. The bot treats it as an escalation, not a pick. The code
   does not exist, so the bot offers did-you-mean rows first.
2. She picks `1`. The bot now knows the product and its brand, and asks which marketing team,
   with three numbered buttons.
3. She picks `1`. The bot routes to Marketing Product; the roster is her company's, the
   member is one tagged with the product's brand (or untagged). She sees the usual "routed to
   the PIC from Marketing Product team" message.
4. Another day she asks for a photo of `MWC7625-SH-S10` (a Mocha-brand product under the
   Sorento company), then types `ESCALATE TO MARKETING`. No question: the photo turn already
   sat on Marketing Product, so the bot routes there with brand mocha carried. Kia Yee or
   Charissa gets it, never Zhi Yang.
5. If that photo had been missing, the bot had offered "route this to the Marketing Product
   team?". `yes` and `ESCALATE TO MARKETING` both route there, brand mocha.
6. She checks stock of a code, then types `ESCALATE TO MARKETING`. Stock is a warehouse turn,
   so nothing carries: the bot asks which marketing team, then routes with the whole tier-1
   pool.
7. She types `MARKETING SRTWC6030-SH` with no escalate word. She gets the product answer, as
   today (D4).

Told automatically: the assignee, the SLA clock, and the PIC comment, which names the raw code
she typed and the code she picked.

## Verb (D1, D7)

- AC-1101 A `request_for_help` turn whose parser output names a team (verbatim word, family or
  catalogue) is routed to the escalation lane whatever open question or offer the previous
  turn left (suggest offer, member offer, product picker). pytest over `head/output_exchange`
  with the 11 Sep 12:55 turn's exact parser output and previous state; replay of that turn.
- AC-1102 A `request_for_help` turn that names NO team keeps today's head behaviour (the 8 Sep
  retype rules). pytest: the existing `test_pass4_item5_no_team_named_keeps_default_routing.py`
  stays green unchanged.
- AC-1103 `escalation.is_escalation_confirmation: true` from the parser is ignored when no offer
  is open. pytest with the 11 Sep 12:56 turn: `pending` null, flag true, word `marketing` ->
  the lane asks which marketing team.
- AC-1104 The same flag with an open one-team offer still confirms it (unchanged). pytest.

## Team (D2)

- AC-1111 A word naming exactly one catalogue team ("warehouse", "marketing product",
  "certification") assigns that team with no question. pytest.
- AC-1112 A family word with no open offer and a previous turn on a team outside the family
  (purchasing, warehouse, customer_service, none) asks a `team_pick` over the family's members
  only, numbered, with quick replies. pytest; replay of the 11 Sep 12:56 turn.
- AC-1113 A family word while a one-team offer for a member of that family is open assigns
  that team with no question (journey step 5). pytest.
- AC-1114 A family word when the previous turn's routing team is a member of that family
  assigns that team with no question (journey step 4). pytest.
- AC-1115 A family word while an offer for a team OUTSIDE the family is open (warehouse offer,
  "escalate to marketing") asks over the family. pytest.
- AC-1116 The team-word check runs before the confirmation-flag check: a named team beats
  `is_escalation_confirmation`. pytest with both set.
- AC-1117 A bare "escalate" (no team, no offer) keeps the carried team, then the default (8 Sep
  ruling). pytest: existing tests stay green.
- AC-1118 The answer to a `team_pick` (number or label) lands on the escalation lane and
  assigns the picked team (existing R-b behaviour, re-asserted on the stacked branch). pytest.

## Brand and company (D3, D6, D7)

- AC-1121 When the turn names a product that resolves to one row, the next-assignee body
  carries `brand_code` = that row's brand. pytest with `SRTWB8004` (brand SORENTO) and
  `MWC7625-SH-S10` (brand MOCHA); both against the same company roster.
- AC-1122 The lane never sets `company_id` from the product. The body's `company_id` is absent
  (or the carried routing company when one is persisted); next-assignee resolves the contact's
  company. pytest asserting the body.
- AC-1123 A contact in two companies gets the existing `company_pick` question. pytest: the
  existing S5 clarify tests stay green.
- AC-1124 When the turn names a product that does not resolve, the reply is the business
  lane's did-you-mean rows, armed as a `product_pick` whose payload records the deferred
  escalation (team word, offer team if any). No assignment, no SLA row, no comment on that
  turn. pytest asserting the open question and zero actions.
- AC-1125 A pick on that question resolves the product and brand and continues the team ladder
  in the same turn: family word -> `team_pick` (or direct when AC-1113 / AC-1114 apply);
  catalogue word -> assignment. pytest, two turns.
- AC-1126 A new ask instead of a pick clears the question; no escalation happens; the ask is
  answered. pytest.
- AC-1127 No product named this turn, previous turn's team == the team the ladder lands on:
  the previous product and brand are in the body. pytest (photo turn then "escalate to
  marketing").
- AC-1128 No product named this turn, previous turn's team != the landed team: `brand_code`
  null in the body. pytest (stock turn then "escalate to marketing" then pick Marketing
  Product). This same-team gate does NOT apply when this turn resumed the lane's own
  `team_pick` question (D10): the product that turn's escalation request named carries to
  the landing regardless of the previous turn's team, because the question was the lane's
  own deferral of that same request. pytest, live and dry (SRTWB8004 named, family word
  asked, team picked).
- AC-1129 The body's `team_code` is the team the ladder landed on and `agent_code` is that
  team's agent from the domain table, never the inherited pair. pytest with inherited
  purchasing/general_enquiries and landed marketing_product.
- AC-1130 The PIC comment names the raw code the customer typed and, after a pick, the code
  picked. pytest on the `add_comment` action payload.

## Seams and safety

- AC-1141 A dry run reaches no WRITING seam: no next-assignee, no SLA, no send. It DOES call
  the resolver and the assignee preview (D9), so the brand, the did-you-mean arm and the
  " handling <brand>" copy are previewable, for every shape above (H37). pytest parametrised
  over the shapes.
- AC-1142 The lane's resolve call uses the production bundle's resolver with the request's
  company scope; a resolver error degrades to "not found" (did-you-mean or brand none), never
  a failed turn. pytest with a raising resolver.
- AC-1143 The strict xfail tests for H26 and H27 in `test_s5_escalation_lane.py` become
  passing tests; their "no resolve call on live lane" counterparts are retired with a note.
- AC-1144 Replay: no real n8n capture exists for the 11 Sep or 21 Aug turns (console-only),
  and hand-written corpus fixtures never gate `test_replay.py`, so the evidence is the chained
  head-to-lane tests in `tests/chatbot/test_escalation_routing_seams.py` built from
  `documentation/plans/chatbot/evidence/escalation-routing-real-turns.json` (turn 1, 3, 4 and a
  Mocha-brand turn); `test_replay.py` stays green at its current count; any registered
  divergence carries its reason in `divergences.py`. (Reviewer S4, captain's amendment 13 Sep
  2026.)
- AC-1145 The console (chat turn page) shows the lane stages for these turns with the landed
  team, brand and question kind visible in the technical details. Owner console pass on the
  lane stack.
- AC-1146 No new session key, no new open-question kind, no migration, no parser prompt version.
  Reviewer checks the diff.
