# UAC: sample request v2, slice 1 (lane SAMPLE-REQUEST-V2)

Card: `CARD-sample-request-v2-11nov.md`. Plan: `PLAN-sample-request-v2-11nov.md`. Evidence: `evidence-sample-request-v2/`.

| # | Acceptance | Test |
|---|---|---|
| U1 | Customer must be an AutoCount debtor on a staff submit; a typed name is not kept by the staff form | `test_staff_submit_needs_a_debtor_not_a_typed_customer`; vitest "rule 1: the customer is an AutoCount debtor" |
| U2 | Ship to is a party: picking one fills its name and address, else the project's site address; a typed address wins | `test_picking_a_party_of_the_project_fills_name_and_address`, `test_a_party_without_address_takes_the_project_site_address`, `test_a_typed_address_wins_over_the_party_address` |
| U3 | A party not on the project asks its role and is linked on save, only by someone who can edit the project | `test_a_party_not_on_the_project_needs_a_role`, `..._is_linked_in_the_role_given`, `test_a_salesperson_who_cannot_edit_the_project_cannot_add_a_party_to_it`, `test_a_non_editor_may_still_pick_a_party_already_on_the_project` |
| U4 | Another company's party or contact is refused | `test_another_companys_party_is_refused`, `test_a_contact_of_another_party_is_refused` |
| U5 | Contact person from the party's people (registration popup): "A & B", phone from the first (only with the parties view grant), they join the stakeholders when the caller can edit the project | `test_several_contacts_print_a_and_b_with_the_first_ones_phone`, `test_picked_contacts_join_the_projects_stakeholders`, `test_a_non_editors_contacts_print_but_do_not_join_the_stakeholders`, `test_the_contact_phone_is_not_copied_without_the_parties_view_grant` |
| U6 | Staff submit needs a party and a shipping address | `test_staff_submit_needs_a_ship_to_party`, `test_staff_submit_needs_a_shipping_address`, `test_staff_submit_with_a_party_and_a_debtor_passes` |
| U7 | Editing a saved draft: clearing the party, unticking contacts, clearing the address all clear on the server; re-picking works | `test_clearing_then_repicking_the_party_leaves_a_submittable_draft`, `test_unticking_every_contact_clears_the_contact_person`, `test_a_cleared_address_is_cleared_and_then_blocks_submit`; `lib/sample-request-form.staff.test.ts` |
| U8 | "For" and the free contact phone / note are gone from the form; old rows keep and show them (For only when set) | vitest "drops For, the free contact phone / note..."; `test_an_old_free_text_draft_keeps_its_text_until_a_party_is_picked`; `stateFromDetail (card example E)` |
| U9 | Portal (external contact, limited salesperson until slice 2) ignores and never sees the ship-to party | `test_sample_request_v2_portal_ignores_the_ship_to_party` |
| U10 | Four sections, Preview the only main button, Submit in the popup, dd/mm/yyyy picker | vitest "SAMPLE-REQUEST-V2 the guided form", "Preview, then Submit in the popup" |
| U11 | Submit / Save draft / Cancel / Back return to where the person started; an unsafe origin is ignored | vitest "owner 16:30: every exit returns...", `ProjectDetailClient.test.tsx` AC-PS-20; browser pass 08, 09 |
| U12 | From the project tab, the detail page's Back and breadcrumb go to the tab, prev/next walks the project's requests | browser pass 09 (Back to project), `SampleRequestPageHeader.tsx` |
| U13 | Every list row one line; the Delivery pill inline; a Delivered row shows its delivered day, no pill | `lib/sample-request-tracking.test.ts` "once delivered"; browser pass 02, 12 (cell height 20-24 px) |
| U14 | The proposal "To" picker and the Ship to picker are one component | `QuotationRecipientPicker.test.tsx` (14) on `_shared/components/ProjectPartyPicker.tsx` |
