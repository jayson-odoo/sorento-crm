# PLAN: escalation resolves the brand from the focus product (#865)

Status: IN REVIEW (fix round 2 folded in: S1, S2, N1, N2, N3 of the reviewer pass at df577453), small fix track (backend only, under ~300 changed app lines, no migration, no auth/RBAC change, no new ingest surface). PR #1300, branch `fix/chatbot-escalation-brand-from-focus`.

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

## From #866's plan

D7 ("brand is the resolved product's") is what this builds. D1, D2 and D6 (the verb, team and did-you-mean ladder) do not fit option 1. They stay with #866's remaining rows, which are not revived here.

## Tests

`sorento_crm_backend/tests/chatbot/test_escalation_brand_from_focus.py`. Each UAC maps to one test.
