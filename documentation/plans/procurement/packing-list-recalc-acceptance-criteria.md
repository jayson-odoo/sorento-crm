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
