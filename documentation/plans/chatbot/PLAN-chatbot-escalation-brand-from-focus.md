# PLAN: escalation resolves the brand from the focus product (#865)

Status: IN REVIEW (fix round 4 folded in: the owner's retest of round 3, 27 Sep 21:19 MYT; round 3 the owner's console retest of 27 Sep; round 2's S1, S2, N1, N2, N3 before it), small fix track (backend only, under ~300 changed app lines, no migration, no auth/RBAC change, no new ingest surface). PR #1300, branch `fix/chatbot-escalation-brand-from-focus`.

Source: the root-cause report on #865 ("Root cause: null brand on escalation after a spec answer (backup of 25 Sep)") and the owner ruling of 27 Sep 00:20 MYT authorising its fix option 1. UAC: `chatbot-escalation-brand-from-focus-acceptance-criteria.md`.

## Cause

The escalation lane never looked up a brand (H26, `escalation_services._not_live("resolve_and_gate")`). The five-key session keeps the focus product and not its brand. The only thing that carried a brand into an escalation was a question some earlier turn happened to mint, with the brand stamped on its payload (#1108 `carried_brand`). So a product turn that FAILED carried the brand, and a product turn that succeeded dropped it. On 24 Sep (contact 503641482) a SORENTO spec answer followed by "Please esculate to Marketing" drew the mocha-only member.

## Fix (option 1)

1. `lanes/escalation.py::_apply_focus_brand`: the brand of the product the escalation is about, read off the product row through a new `product_brand` seam. The product is `item["focus_products"]`, THIS turn's applied focus: this turn's named product, else the product in focus. It outranks `carried_brand` (the offer carry) and `none`. It never outranks `stated_brand`, the brand the customer named on THIS turn (fix round 2, S1: "I need the Mocha catalogue, escalate to marketing" after a SORENTO spec answer is a Mocha escalation, as on main), and never the roster arms (`picked_member`, `company_pick`, `prior_state*`, `multi_company_unpicked`). The console dry run (`_preview_routing`) applies the same rung as the live draw.
2. The carry ends where the focus rules already end it (`turn/apply.py::_focus_rules`): on a topic reset or a newer product. D3's same-team gate on #866's plan is re-ruled by the owner as this fix.
3. `lanes/escalation_services.py::focus_product_brand`: one read, `products` joined to `brands`, inside a savepoint. It returns one brand, or none when the products disagree.
4. The sibling case ("eta" after a product turn): a SETTLED focus product (one carrying its row `uuid`) is never re-resolved, so no resolver runs and no gate exists. `engine._focus_brand_payload` then gives the bridge's miss arm (the incoming miss) the focus product's brand, and `TurnContext.focus_brand` gives it to `_team_pick_question`. Both reads are lazy (fix round 2, N2): the bridge reads it only when `answer_bridge.answers_a_miss` says the miss arm will answer, and compose calls the thunk only when it mints a `team_pick`, so a hit pays for no products x brands query. An unsettled focus product is re-resolved and the gate already carries its brand (guarded by a test). Not built: a fill for a turn whose resolver ran and resolved no brand. The kill test found no path that reaches it. Trigger to build it: a live offer minted with a null brand on a turn whose resolver ran while the focus held a branded product.
5. Observability: `looked_up` facts carry `routing` (next-assignee `team_code`, `brand_code`, `routing_source`, `cursor_key`, assignee, `brand_matched`). `/external/next-assignee` echoes `cursor_key` (additive).

No migration, no new session key: contract 129's five-key wire shape is unchanged (option 3 was rejected).

## Fix round 3: the owner's console retest (27 Sep)

The owner sent "check spec srtwc286", then "please escalate to marketing team", in the console (dry run). The draw went out with `brand_code: null`, `routing_source: none`, to the mocha-only member.

- **Diagnosis.** Hypothesis 1 (the console forgets between dry runs) does not hold: a dry run writes no session, but the console already carries its own. The engine returns the turn's `session_patch` on a dry run, `console_service._next_state` hands it back as `session_vars`, and `useChatbotConsole` sends it as `previous_conversation_state` on the next turn. Turn 2's `remembered_keys: 1` is that focus. (`recalled_frames` is opt-in topic recall and unrelated.) Hypothesis 2 holds one layer down. "check spec srtwc286" leaves the focus entry UNSETTLED (`raw`/`canonical_code` "srtwc286", no `uuid`), because master_products does not narrow on product, so `turn/apply.py`'s `focus_settles_product` never runs. The live path writes the same entry. The brand read matched an unsettled code by EXACT `product_code`, so "SRTWC286" never found "SRTWC286-SH". The 24 Sep script passed only because "SRTKS8650A" is the full code. This was a live defect as well, not only a console one.
- **Fix.** `focus_product_brand` finds an unsettled code's rows by the resolver's own code tiers, `entity_resolver._probe_product` (exact) and then `_prefix_probe_product` (prefix, then substring). These are the rows the answer showed. One brand among them is the brand, and several brands name none, as before.
- **R2, the console carry.** No change was needed; it is the console's own per-session carry (the `session_patch` round trip above), not a dry-run memory write. It is now pinned: the `session_vars` a console turn returns carry the same focus the live turn writes.
- **R3, where it went.** `lanes/escalation.routing_line` renders the draw as one line: `Routing: team <code>, brand <code|none>, source <rung>, assignee <name|none>`. The escalation's `looked_up` stage summary carries it (trace screen), `ConsoleTurnResponse.trace_summary.routing_line` carries it, and the console shows it under the turn's first bubble. The reply the customer sees is unchanged.

## Fix round 4: the owner's retest of round 3 (27 Sep 21:19 MYT)

Three escalations in one console conversation. 1 ("check spec srtwc286", then "pelase esclate to marekting team") and 3 ("please esclate to marketin team MWCY8610") drew right. 2 ("pelase escalate to marketing team MWC-SC8609-PP") went to purchasing with no brand. Owner's rule: every Mocha company item, and every Mocha-brand product in Sorento, goes to the Mocha brand member of Marketing Product, whichever company the customer is talking to.

- **Diagnosis.** The parser returned `suggested_team: purchasing` for 2: the prompt's routing table fills the team from the domain, and a product code reads as master_products (team purchasing). `lanes/escalation._person_routing` took the parser's team whenever it named a single catalogue team, so the customer's "marketing team" lost. Separately, the brand read ran on the turn's session, scoped to the contact's Sorento company, and MWC-SC8609-PP exists only in the Mocha company, so no row and no brand.
- **R1.** `_named_teams` reads the team the customer named off the parser's `user_goal` (its reading of the message, spelling fixed; never the raw text, D11), and it beats the parser's team. "marketing" about a product in focus is Marketing Product; without one it asks over the three. The draw is made from that team, live and in the dry-run preview. No prompt change (that would be a published prompt version).
- **R2.** `escalation_services.focus_product_origin`: a code the contact's own company does not hold is looked for across companies, for the brand read only. A row's brand is its brand row, else the brand its company stands for (Mocha company: mocha; the multi-brand Sorento company: none). A code in no company names no brand and the escalation still goes out. The session's scope is restored after the read.
- **R3.** `routing_line` adds `found in <company>`, or `product <code> not found in any company`.

## From #866's plan

D7 ("brand is the resolved product's") is what this builds. D1, D2 and D6 (the verb, team and did-you-mean ladder) do not fit option 1. They stay with #866's remaining rows, which are not revived here.

## Tests

`sorento_crm_backend/tests/chatbot/test_escalation_brand_from_focus.py`. Each UAC maps to one test.
