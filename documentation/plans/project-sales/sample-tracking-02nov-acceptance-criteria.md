# UAC: Sample request two-stage tracking (PS-SAMPLE-TRACKING)

Plan: `PLAN-sample-tracking-02nov.md`. Each AC names the test that proves it.

## Stage 1: the date answer

- AC-ST-01: Change to processing without an answer is refused (422,
  `SAMPLE_REQUEST_DATE_ANSWER_REQUIRED`, field `date_feasible`); the request stays Submitted.
  `test_start_processing_needs_a_date_answer`
- AC-ST-02: Yes moves it to Processing; detail shows `date_feasible` true, no proposed date, who and when.
  `test_start_processing_can_meet_the_date`, `test_feasible_drops_a_stray_proposed_date`
- AC-ST-03: No without a date -> 422 `SAMPLE_REQUEST_PROPOSED_DATE_REQUIRED`; a past date -> 422
  `SAMPLE_REQUEST_PROPOSED_DATE_PAST`. `test_cannot_meet_needs_a_proposed_date`,
  `test_proposed_date_cannot_be_in_the_past`
- AC-ST-04: The salesperson sees the proposed date and note on detail and list rows.
  `test_salesperson_sees_the_proposed_date_on_detail_and_list`; FE
  `SampleRequestDetail.dateAnswer.test.tsx`
- AC-ST-05: The sample team changes the answer in Processing / Customer confirmed only (409
  `SAMPLE_REQUEST_DATE_ANSWER_CLOSED` otherwise); a salesperson gets 403.
  `test_coordinator_changes_the_answer_while_processing`, `test_answer_only_in_stage_one`,
  `test_salesperson_cannot_answer`, `test_answer_change_is_validated_like_the_move`
- AC-ST-06: Stages: Submitted/Processing/Customer confirmed = Processing, Delivered = Delivery,
  others none. `test_stage_for_status_key`, `test_stage_on_detail_through_the_flow`
- AC-ST-07: `?stage=` is multi-select and finds Delivered rows; the Delivery sort follows the shown
  date. `test_stage_filter_is_multi_select_and_finds_delivered`,
  `test_delivery_date_sort_follows_the_proposed_date`

## Stage 2: the consignment is the delivery

- AC-ST-10: The picker lists only the company's live consignments; sample team only.
  `test_picker_lists_live_consignments_of_the_company_only`, `test_picker_is_for_the_sample_team`
- AC-ST-11: Linking a live CG delivers it; `return_due` follows the loan; `consignment_no` is the CG
  number. `test_linking_a_live_consignment_delivers_on_its_date`,
  `test_linking_from_customer_confirmed_also_delivers`
- AC-ST-12: Refusals: before Processing (409), a cancelled request (409), not a live consignment of the
  company (422), a salesperson (403). `test_link_needs_processing_first`,
  `test_cancelled_request_cannot_be_linked`,
  `test_link_refuses_what_is_not_a_live_consignment_of_the_company`, `test_salesperson_cannot_link`
- AC-ST-13: Manual Delivered is refused (409) while a CG is linked; without one it still works.
  `test_manual_delivered_is_refused_while_a_consignment_is_linked`,
  `test_manual_delivered_still_works_without_a_consignment`; FE hides Mark delivered
  (`SampleRequestDetail.consignment.test.tsx`)
- AC-ST-14: A voided CG reverts to Customer confirmed (or Processing); restored, it delivers again.
  `test_voided_consignment_reverts_and_a_restored_one_delivers_again`,
  `test_void_reverts_to_processing_when_never_confirmed`
- AC-ST-15: The delivered date is the Overall Tracking date of the CG-numbered `orders` row when
  live and dated, else the CG date, and the source is named. Cancelled, deleted, undated, other-number
  and other-company rows are ignored. `test_tracked_delivery_date_wins_over_the_cg_date`,
  `test_tracking_rows_that_do_not_count_are_ignored`
- AC-ST-16: A tracking date landing after the link updates `delivered_at` and `return_due`;
  unrelated orders change nothing. `test_a_tracking_date_that_lands_later_updates_the_delivery`,
  `test_tracking_sync_leaves_unrelated_orders_alone`
- AC-ST-17: Unlink undoes the delivery; manual Delivered then link takes the CG date.
  `test_unlink_undoes_the_delivery`, `test_manual_delivered_then_link_takes_the_consignment_date`
