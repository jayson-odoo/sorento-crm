# PLAN: GRN pull from AutoCount with PO/SPO line linkage (GRN-PULL-CRM)

Status: **behaviour card filed (crew-ask on PR #1427), waiting on owner answers; no code yet.**
Track: full L (new permission slug + grant migration, prod data linkage, cross-repo with
shared-service). PLAN body + UAC are written only after the owner answers the card.

Scope: Goods Receive Notes pulled on request by DocDate, same path as the DO pull
(shared-service snapshot -> CRM preview/compare -> review -> user confirms). Push stays OFF.
Never writes to AutoCount. Confirm applies through `AutocountDocIngestService` (one writer).

Paths: `be/` = `sorento_crm_backend/`.

## 0. Scout (measured on `main` 066b966e)

| Thing | Where | State |
| --- | --- | --- |
| DO pull, end to end | `be/app/services/autocount_pull_service.py:39-67` (entity maps), `be/app/tasks/autocount_pull_tasks.py:795` (`_preview_delivery_orders`), `:833` (`_apply_delivery_orders`), `be/app/api/v1/integrations/autocount_pull.py:332-414` (rows / download / compare dispatch), `be/app/services/autocount_pull_compare.py` | Merged (#1383). GRN is a fourth entity on the same machinery. |
| GRN ingest | `be/app/services/autocount_doc_ingest_service.py:932` (`_apply_grn`) | Exists. Lands on `picking_headers` / `picking_lines`, status `approved`, adopts an Excel GRN by number, never unsets a link. |
| GRN line exact link | same file `:966-970`, `_po_or_spo_line` `:775` | `FromDocDtlKey > 0`: one `source_ref` match across PO lines + SPO allocations, else `po_line_unresolved`. |
| GRN line, key 0 | `:176` (`_link_key`), `:971-978` | 0 = no key. Only `OurPONo` is read: header-level `purchase_order_id` (PO) or `from_doc_type='SPO'`; **line link stays null; `FromDocNo` is stored but never resolved**. The owner's sample line (`PO`, `PO-2026/07-0013`, key 0, and `OurPONo` usually null) therefore links nothing today. |
| GRN Excel upload linkage | `be/app/tasks/import_tasks.py:2177` (`process_grn_lines_import`), SPO column order `:1683` (our po no, from doc no, spo number, transfer from), header fallback `:2346`, group key `:2369`, draw `:2532-2544` | **SPO only, never PO lines.** Matcher `be/app/services/grn_spo_matching.py`: `build_allocation_pool` `:96` (SPO key normalised, product, company, FIFO by age, capacity = allocated - other GRNs' drawn qty - unexplained receipt) + `draw_fifo` `:224` (same warehouse first, then any, remainder unlinked). One receipt may SPLIT into several picking lines. |
| Split vs AutoCount line identity | `be/app/models/procurement.py:840` | `uq_picking_lines_header_dtl_key`: one picking line per AutoCount DtlKey, so an AutoCount line cannot be split the way an upload line is. |
| Cancelled GRN and SPO capacity | `grn_spo_matching.py:185,292` | Pool excludes `rejected` only; the ingest writes a cancelled GRN as `picking_status='cancelled'` (`:947`), so its linked lines still consume SPO capacity. |
| Shared-service GRN snapshot | not readable from this sandbox (repo scope) | Unknown. Contract needed below. |

## 1. Behaviour card

See the `crew-ask` comment on PR #1427 (copied here once answered, with the rulings).
