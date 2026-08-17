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
