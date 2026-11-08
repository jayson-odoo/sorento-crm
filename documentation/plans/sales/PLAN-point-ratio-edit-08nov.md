# PLAN: Point ratio rows, edit and delete (lane POINT-RATIO-EDIT)

Status: in review, small fix track (no migration, no new permission, no external ingest). Browser pass: `evidence/point-ratio-edit/README.md`.

## Journey
Owner, 8 Nov: on Sales > Targets (Dealers tab) > Point ratio, a ratio added by mistake cannot be
fixed or removed. Each row needs Edit (RM per point and From date) and Delete.

## Facts (measured)
- Dialog: `sorento_crm_frontend/app/(protected)/sales/targets/components/PointRatioDialog.tsx`.
- API: `GET|POST /api/v1/sales/targets/point-ratios` (`app/api/v1/sales/targets.py`), service
  `target_service.point_ratios / ratio_on / save_point_ratio`.
- Model `SalesPointRatio` (`app/models/sales.py`): unique (company_id, effective_from),
  `__audit_track__ = True`, so update and delete are audited by the generic audit listeners.
- Ratios are read live on every target read (`point_ratios(db)` then `ratio_on(...)`); nothing is
  snapshotted, so an edit or delete is seen on the next read. The FE invalidates the ratio list and
  the target queries, as Add does today.
- No ratio in force for a period is an existing state: `commission_service` marks it
  "ratio missing" and the target and % read empty (same as before any ratio was added).

## Design
- Edit: `PATCH /point-ratios/{id}` `{effective_from, rm_per_point}`, `sales.targets.edit`.
  Another row on the same From date is refused (409, plain words), never merged silently.
  In the dialog, the row's pencil swaps the row's values for inputs in place (Save / Cancel).
- Delete: server-deferred pending action `point_ratio.delete` (D7), same as the SCM Exchange
  rates panel (`CurrencyRatesPanel.tsx`, `useDeferredRowAction`), permission `sales.targets.edit`
  (ratio writes are `.edit` today). Registered in `_PARK_SCOPED_MODELS` so it is company-scoped.
- Deleting a row: the previous (older) ratio applies from that date on. Deleting the only row is
  allowed: points targets then read as "ratio missing", exactly the state before the first ratio.

## Tests (red first)
- pytest: edit changes value and date; edit onto an existing date is 409; edit unknown id 404;
  delete via pending action removes row and the older ratio then applies; audit rows written.
- vitest: row Edit swaps to inputs and saves the payload; Delete calls the deferred row action.
