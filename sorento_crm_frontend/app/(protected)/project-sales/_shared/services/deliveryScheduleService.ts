/**
 * Delivery schedule intake (P6), CONTRACT-project-lead-to-so.md section 4.
 *
 * Endpoints taken verbatim from the contract:
 *   POST /purchase-orders/{po_id}/delivery-schedules/upload
 *   GET  /delivery-schedule-versions/{version_id}
 *   PUT  /delivery-schedule-versions/{version_id}/cells
 *   PUT  /delivery-schedule-versions/{version_id}/products/{product_index}
 *   POST /delivery-schedule-versions/{version_id}/confirm
 *
 * Added after the contract, on the same shape as the two PUTs above:
 *   PUT  /delivery-schedule-versions/{version_id}/columns/{column_index}/dismissal
 *
 * Two endpoints below are NOT in the contract and are marked GUESS. Section 4 gives no way
 * to find a version id from a project, and the tab has to list something. They mirror the
 * quotation pair phase 1 already ships (`/projects/{id}/quotations` and
 * `/quotations/{id}/versions`), which is the nearest precedent in this codebase.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  DeliverySchedule,
  DeliveryScheduleCellInput,
  DeliveryScheduleConfirmBody,
  DeliveryScheduleUploadBody,
  DeliveryScheduleUploadResult,
  DeliveryScheduleVersion,
  DeliveryScheduleVersionSummary,
} from '../types/deliverySchedule.types';

const BASE = '/api/v1/project-sales';

interface ListEnvelope<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

/** GUESS (see the file header): every schedule on the project, newest first. */
export async function listDeliverySchedules(
  projectId: string,
): Promise<DeliverySchedule[]> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/delivery-schedules`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load delivery schedules'));
  const body: ListEnvelope<DeliverySchedule> = await response.json();
  return body.data;
}

/** GUESS (see the file header): the version history of one schedule, newest first. */
export async function listDeliveryScheduleVersions(
  scheduleId: string,
): Promise<DeliveryScheduleVersionSummary[]> {
  const response = await apiFetch(`${BASE}/delivery-schedules/${scheduleId}/versions`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the version history'));
  const body: ListEnvelope<DeliveryScheduleVersionSummary> = await response.json();
  return body.data;
}


export async function getDeliveryScheduleVersion(
  versionId: string,
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(`${BASE}/delivery-schedule-versions/${versionId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this schedule'));
  return response.json();
}

/**
 * Returns `202` with extraction queued. No Content-Type header: the browser has to set the
 * multipart boundary itself, and naming the type here silently breaks the upload.
 */
export async function uploadDeliverySchedule(
  poId: string,
  body: DeliveryScheduleUploadBody,
): Promise<DeliveryScheduleUploadResult> {
  const form = new FormData();
  form.append('file', body.file);
  if (body.issuer_party_id) form.append('issuer_party_id', body.issuer_party_id);
  if (body.revision_label) form.append('revision_label', body.revision_label);
  if (body.delivery_schedule_id)
    form.append('delivery_schedule_id', body.delivery_schedule_id);
  if (body.po_version_id) form.append('po_version_id', body.po_version_id);

  const response = await apiFetch(
    `${BASE}/purchase-orders/${poId}/delivery-schedules/upload`,
    { method: 'POST', body: form },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to upload the schedule'));
  return response.json();
}

/**
 * The per-column correction path. Upsert by `(phase_id, product_id)`; a qty of `"0"`
 * deletes the cell. The server recomputes the column total and the reconciliation, so the
 * whole version comes back rather than just the cells.
 */
export async function saveDeliveryScheduleCells(
  versionId: string,
  cells: DeliveryScheduleCellInput[],
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(`${BASE}/delivery-schedule-versions/${versionId}/cells`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cells }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the quantities'));
  return response.json();
}

/**
 * Identifies a column a human had to read. The server also writes the customer item code
 * map, so the same code resolves by itself on the next schedule from this customer.
 */
export async function resolveDeliveryScheduleProduct(
  versionId: string,
  productIndex: number,
  productId: string,
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(
    `${BASE}/delivery-schedule-versions/${versionId}/products/${productIndex}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId }),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to set the product'));
  return response.json();
}

/**
 * Overrules ONE column's failing check as a false signal, with a reason, so it stops
 * blocking the confirm.
 *
 * `PUT /delivery-schedule-versions/{id}/columns/{column_index}/dismissal` -> the whole
 * version. `dismissed: false` puts the column back under its verdict. 422 when dismissing
 * without a reason. Anything that CHANGES the column (its product, its cells, a re-read of
 * the document) clears the dismissal server-side, so the verdict is live again.
 */
export async function dismissDeliveryScheduleColumn(
  versionId: string,
  columnIndex: number,
  dismissed: boolean,
  reason?: string | null,
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(
    `${BASE}/delivery-schedule-versions/${versionId}/columns/${columnIndex}/dismissal`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dismissed, reason: reason ?? null }),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to dismiss the warning'));
  return response.json();
}

/**
 * Read this schedule again, on the same version.
 *
 * `POST /delivery-schedule-versions/{id}/retry-extraction` -> the whole version body, back
 * on `queued`. 409 when there is nothing to retry: the read is genuinely still in flight,
 * the document has already been read, or the version is confirmed.
 *
 * The PO path carries the identical endpoint for the identical reason: a background
 * work-horse that is killed does not run its own error handling, so a read can end without
 * anything being written onto the row.
 */
export async function retryDeliveryScheduleExtraction(
  versionId: string,
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(
    `${BASE}/delivery-schedule-versions/${versionId}/retry-extraction`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not start another read'));
  return response.json();
}

/**
 * Promotes the phases onto the project. 409 while any column is unreconciled unless the
 * caller sends `acknowledge_unreconciled` with a reason.
 */
/**
 * Writes the override for every cell this proposal names (section 9.7c). 409 when the
 * proposal was already decided, or the version is confirmed.
 *
 * `POST /delivery-schedule-versions/{id}/revision-proposals/{index}/accept` -> the whole
 * version, same shape as every other write on this screen.
 */
export async function acceptRevisionProposal(
  versionId: string,
  index: number,
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(
    `${BASE}/delivery-schedule-versions/${versionId}/revision-proposals/${index}/accept`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to accept this proposal'));
  return response.json();
}

/**
 * Marks the proposal rejected. Writes no override; the note and the highlighted cells stay
 * exactly as read. Same 409s as accept.
 */
export async function rejectRevisionProposal(
  versionId: string,
  index: number,
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(
    `${BASE}/delivery-schedule-versions/${versionId}/revision-proposals/${index}/reject`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to reject this proposal'));
  return response.json();
}

export async function confirmDeliveryScheduleVersion(
  versionId: string,
  body: DeliveryScheduleConfirmBody = {},
): Promise<DeliveryScheduleVersion> {
  const response = await apiFetch(
    `${BASE}/delivery-schedule-versions/${versionId}/confirm`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to confirm the schedule'));
  return response.json();
}

/**
 * Hard delete: every version, its cells and its document, then the schedule. The
 * purchase order it was checked against is untouched.
 *
 * `DELETE /delivery-schedules/{schedule_id}` -> `{ success, deleted }`. 409, naming the
 * blocker, when a confirmed version is a live commitment (built into a published/amended
 * sales order, or named by a published amendment).
 */
export async function deleteDeliverySchedule(scheduleId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/delivery-schedules/${scheduleId}`, {
    method: 'DELETE',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete this schedule'));
}

/**
 * One version, and its cells and document. The schedule and its other versions are
 * untouched.
 *
 * `DELETE /delivery-schedule-versions/{version_id}` -> `{ success, deleted }`. 409
 * `schedule_version_last` on the only version of a schedule (delete the schedule
 * instead); 409 on a confirmed version that is a live commitment, same rule as the
 * schedule delete.
 */
export async function deleteDeliveryScheduleVersion(versionId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/delivery-schedule-versions/${versionId}`, {
    method: 'DELETE',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete this version'));
}
