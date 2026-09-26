# UAC: escalation resolves the brand from the focus product (#865)

Plan: `PLAN-chatbot-escalation-brand-from-focus.md`.

- **AC-865-1** A SORENTO product answered, then "escalate to marketing" with no offer open: next-assignee receives `brand_code: sorento` and draws the sorento-tagged member. (`test_24sep_replay_spec_hit_then_escalate_to_marketing_draws_the_sorento_member`)
- **AC-865-2** The escalation trace's `looked_up` facts record `routing`: `team_code`, `brand_code`, `routing_source` (`focus_product`), `cursor_key` (`~b:sorento`), and the assignee. (`test_24sep_replay_the_trace_records_the_next_assignee_body_and_cursor_key`)
- **AC-865-3** The proven path is unchanged: an offer minted with a stamped brand, accepted with "yes", draws that brand's member. (`test_photo_miss_offer_accepted_with_a_stamped_brand_still_draws_the_brand_member`)
- **AC-865-4** "eta" after a settled product: the minted offer carries the focus product's brand, and "yes" draws that brand's member. (`test_eta_after_a_settled_product_mints_the_offer_with_the_focus_products_brand`)
- **AC-865-5** A fanned-out miss after a settled product: every team option `_team_pick_question` mints carries the brand. (`test_a_fanned_out_miss_after_a_settled_product_stamps_every_team_option_with_its_brand`)
- **AC-865-6** A topic reset escalation carries no brand. (`test_a_topic_reset_escalation_carries_no_brand`)
- **AC-865-7** A newer product replaces the focus, and its brand is the one drawn. (`test_a_newer_product_replaces_the_focus_and_its_brand_is_the_one_drawn`)
- **AC-865-8** The session is exactly the five keys, with no brand on focus products (contract 129). (`test_the_session_written_by_both_turns_is_exactly_the_five_keys_with_no_brand_on_focus`)
- **AC-865-9** The roster arms keep their own brand. A missing brand, a missing seam, or a failed read leaves the item unchanged. Products that disagree on a brand name none. (`TestApplyFocusBrand`, `TestFocusProductBrandRead`)
- **AC-865-10** A brand the customer states on the escalation turn outranks the focus product: a SORENTO spec answer, then "I need the Mocha catalogue, escalate to marketing", draws the mocha member with `routing_source: stated_brand`. (`test_a_mocha_catalogue_escalation_after_a_sorento_spec_answer_draws_the_mocha_member`, `TestApplyFocusBrand::test_a_brand_the_customer_stated_this_turn_keeps_its_own_brand`)
- **AC-865-11** A console dry run of the 24 Sep journey previews the same draw as the live turn: preview body `brand_code: sorento`, Tay Zhi Yang, trace `routing_source: focus_product`, no SLA row. (`test_24sep_replay_as_a_console_dry_run_previews_the_sorento_member`)
- **AC-865-12** A settled focus entry finds its row by `uuid` alone, with no `canonical_code` and a `raw` that is not the code. (`TestFocusProductBrandRead::test_a_settled_entry_matches_by_its_uuid_alone`)
- **AC-865-13** The products x brands read runs only when an offer is minted: a hit over a settled focus product reads it zero times, a fanned-out miss once. (`TestTheFocusBrandIsReadOnlyWhenAnOfferIsMinted`)
