# PLAN: SPARE-PART-OR-B C (order request follows SO -> FP -> OI)

Status: Build (card v1 + correction accepted by crew 14 Nov, owner rulings). Track L (additive migration, approval bypass for approvers, purchasing email, security-reviewer required). Lane SPARE-PART-OR-B C, follow-up to #2412 (merged 6f32b1d419).

UAC: `spare-part-or-c-14nov-acceptance-criteria.md` (C1-C5). Card + answers: crew-ask comments on #2412 (card v1, correction, crew acceptance).

## Owner feedback (14 Nov 18:42 hand test of #2412)
1. An approver can create, raise and revise; an approver-raised request skips approval.
2. Approval emails purchasing like the FP confirm email; the OR-sourced header carries OR fields (screenshot: "OI: BRW @", empty S/O NO row).
3. The OI page shows no pre-approval OR history; purchasing sees only what changed for them.
4. Behave exactly like SO -> FP -> OI; revise after approval -> "Waiting for CS"; reuse the functions, no parallel path.
5. Each OR line has a Delivery date; header "Needed by" -> "Delivery date".

## Discovery (measured 14 Nov; POI = `sorento_crm_backend/app/services/project_order_inquiry_service.py`, SPR = `spare_part_request_service.py`)

| Piece | Exists at | Decision |
|---|---|---|
| FP confirm -> OI rows | `ProjectSupplyService.confirm` (`project_supply_service.py:5646`) -> `refresh_for_decision` (POI:1812) | not reusable (needs SO + supply decision); OR raise stays SPR final approval |
| SO change applied | `_settle_row_in_place` (POI:~2985): qty, date, item code, previous_*, `_trim_links`, `refresh_link_state`, `_amended_by_cs`, `_record_handover` | reuse; make `decision` optional (one function) |
| Product swap | `_restate_product` (POI:~3273) | reuse via the settle |
| Removed line | `cancel_row_told` (POI:~6664) | reuse |
| Waiting for CS | derived in `oi_waiting_for_cs.py:22-52` (pending `PlanningChangeRow` on `so_line_id`); feeds worklist, header, purchasing confirm guard | widen the one clause pair with the OR source (open revision with a moved row) |
| Purchasing email | `mark_purchasing_email_trigger` (POI:352), `_record_handover` (POI:4781), `handover_item` (POI:~4921), `_handover_order_facts` (POI:5968), `_fire_pending_handover` (POI:~15923), header dedup (POI:~15425), template `order_inquiry_handover_default` (`alembic/versions/oihe_0001_*`, `oihr_0012_*`) | fill OR facts in `handover_item`; dedup on `pso_id or order_inquiry_id`; relabel via guarded template data migration |
| Email preview | `oi_handover_resend.py` (preview :319) -> `HandoverResendDialog.tsx:44` | same builder, no separate change |
| SO-line Qty cell for purchasing | `QtyCell` + `QtyAnnotationButton` (`orderInquiryWorklistColumns.tsx:~661, :809`), Changed pill (`:835`) | reuse on the spare part OI view |
| OI line date | `oi_delivery_date.resolve` (`:119`) falls back to the row's own date | reuse as is |
| Stage membership | `_on_stage_team` (SPR), `UserService.get_user_tier_in_team_set` | reuse for `is_final_approver` |
| History | `order_inquiry_history_service.history` | add `view=inquiry` cut at first raise (owner's newer ruling, OI page only) |

## Migration
One additive revision: `order_inquiry_rows.revised_product_id`, `order_inquiry_rows.revised_delivery_date`; guarded data step relabelling the seeded default handover template for OR-sourced rows. Nothing dropped.

## Standing rules that apply
One line per row; one value per column; History via the shared component; approval flows (status chip, Revise); number fields; date fields = shared picker, dd/mm/yyyy; email keeps its existing layout; plain words; reuse functions (bulk = single); notification only when the receiver has something to do.
