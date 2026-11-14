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
| U15 | Owner ruling 11 Nov ~19:55: no Customer confirmed status, move or button; existing rows moved to Processing with a History entry (migration `srv2_0002_status_ruling`) | `test_the_graph_has_no_customer_confirmed_move`, `test_a_fresh_install_seeds_no_customer_confirmed`, `test_existing_customer_confirmed_rows_move_to_processing_with_a_history_entry`; vitest `SampleRequestDetail.consignment.test.tsx` |
| U16 | Delivered only by linking the AutoCount consignment; a hand move to Delivered is refused | `test_nobody_marks_delivered_by_hand`, `test_linking_a_live_consignment_from_processing_delivers`, core AC-SR-30 matrix |
| U17 | A voided consignment stays voided: request back to Processing, unlinked, History names the void; a restore never re-delivers; a new consignment delivers | `test_a_voided_consignment_unlinks_and_takes_the_request_back_to_processing`, `test_a_restored_voided_consignment_never_delivers_again`, `test_a_new_consignment_delivers_after_the_void`, `test_the_void_is_in_the_requests_history`, pipeline `test_a_cg_voided_in_autocount_takes_the_request_back` |

## Owner standing rules (documentation/owner-standing-rules.md), slice 1

Checked, applicable lines (22), all pass; 0 open:
- Lists: one toolbar row with "Create" (project tab, unchanged); row click opens the record; every row ONE line
  (Delivery pill inline, browser pass 20-24 px rows); long text truncated with hover (Ship to); prev/next follows
  the list it came from (project tab pager); standard record header (unchanged); History shows every tracked
  action (status changes audited; consignment void writes its own History entry).
- Filters: pickers searchable by name and code (debtor name / code; parties by name, they carry no code).
- Forms: previews and secondary editors in a centred popup (Preview, contacts); minimal default view; Edit is the
  same form as Create with the same Preview step; header fields on top, products in the shared line table;
  number fields unchanged (round 9 tests green); nothing hangs (loading, error and empty states unchanged).
- Dates: dd/mm/yyyy everywhere touched; the shared date picker, no native date input.
- Wording: ONE main button per screen (Preview; Submit inside its popup); plain business words; no explaining
  headings; no UUIDs shown; "Requested by" is the creator, read-only.
- Data: only owner-ruled refusals (consignment-only Delivered); explicit links only (party and consignment picked
  by a person); catalogue product lines only.

Skipped as not applicable to this diff: bulk ticking/actions, column chooser and server sort (no grid columns
changed beyond the Delivery cell), exports, images, scheduled jobs, ERP-write switches, notifications, sales
figures, AI/chatbot. Portal/CRM parity (forms line 39): the owner ruled (Q1 a) that external portal contacts keep
today's form; the limited salesperson's form is slice 2 (#2348).
