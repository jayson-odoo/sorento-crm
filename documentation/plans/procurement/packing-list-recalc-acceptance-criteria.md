# UAC: PACKING-LIST-RECALC

- AC-1 An AutoCount shipping-order push that adds a container number to an SPO whose receipt is
  already stated updates the packing list's stored line status, received quantity and header
  status without anybody opening the packing list. (`test_container_arriving_on_a_later_push_recomputes_the_packing_list`)
- AC-2 Moving an SPO from container A to B recomputes both packing lists; A's lines are released.
  (`test_container_moved_recomputes_both_packing_lists`)
- AC-3 Approving a GRN against a linked SPO line recomputes the packing list; a draft GRN counts
  nothing. (`test_grn_approval_recomputes_the_packing_list`)
- AC-4 A write that does not touch a recompute input, or that rolls back, queues nothing.
- AC-5 Opening the packing list page writes nothing; stale stored figures queue a recompute and
  the page itself shows live figures.
- AC-6 Many writes to one container while its recompute waits queue one job; Redis down
  recomputes inline.
- AC-7 Every automatic header status change leaves an audit entry with old and new status.
- AC-8 Open packing lists are re-swept hourly.

## Follow-up (#2218)
- AC-9 A hand-run script that only imports `app.database` has the recompute listener.
  (`test_a_script_session_has_the_recalc_listener`)
- AC-10 A change made around the listener (a bulk `query.update()`) that should take a Fully
  Received container back is caught by the next hourly sweep through the `updated_at`
  watermark; an untouched container is not revisited.
  (`test_sweep_takes_a_fully_received_container_back_after_a_change_the_listener_missed`,
  `test_the_watched_updated_at_columns_are_stamped_by_the_orm`)
- AC-11 Editing the header's status or company queues the recompute; the recompute's own
  header write does not queue another run. (`test_header_status_or_company_edit_queues_the_recompute`,
  `test_the_recompute_does_not_queue_itself`)
