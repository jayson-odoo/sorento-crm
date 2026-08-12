/**
 * Customer PO intake (P4) and handwriting cards (P5).
 *
 * Every path here is `documentation/plans/CONTRACT-project-lead-to-so.md` sections 2 and 3.
 *
 * The base is written out in full: `lib/api.ts` has no `project-sales` entry in its rewrite
 * table, so the short `/api/project-sales/...` form does not resolve. Same base as
 * `projectService`, and no Next route handler for any of it.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  POAnnotationEditBody,
  POLineUpdateBody,
  POUploadBody,
  POUploadResponse,
  POVersion,
  POVersionHeader,
  POVersionSummary,
} from '../types/poIntake.types';

const BASE = '/api/v1/project-sales';

/**
 * The upload returns as soon as the document is stored and a version row exists (202).
 * Extraction then runs on the RQ `project_docs` queue, which is why the caller navigates to
 * the confirm screen and polls rather than holding a spinner for two minutes.
 */
export async function uploadPurchaseOrderDocument(
  projectId: string,
  body: POUploadBody,
): Promise<POUploadResponse> {
  const form = new FormData();
  form.append('file', body.file);
  if (body.po_number) form.append('po_number', body.po_number);
  if (body.purchase_order_id) form.append('purchase_order_id', body.purchase_order_id);
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/purchase-orders/upload`,
    {
      method: 'POST',
      body: form,
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not upload this PO document'));
  return response.json();
}

export async function getPOVersion(versionId: string): Promise<POVersion> {
  const response = await apiFetch(`${BASE}/purchase-order-versions/${versionId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not load this PO document'));
  return response.json();
}

/**
 * Versions of one PO, so a review can be re-entered from the POs tab.
 *
 * NOT in the contract: the contract gives an upload (which returns the new version id) and
 * a read by id, but no list. A 404 here therefore means "the endpoint does not exist yet",
 * not "this PO has no documents", and the caller renders nothing rather than an error. Any
 * other failure is a real error and is raised.
 *
 * Reads the repo's standard list envelope (`{data, pagination, empty}`) and tolerates a bare
 * array, so it works whichever way the route is eventually written.
 */
export async function listPOVersions(poId: string): Promise<POVersionSummary[] | null> {
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/versions`);
  if (response.status === 404) return null;
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not load the PO documents'));
  const payload = await response.json();
  if (Array.isArray(payload)) return payload;
  return Array.isArray(payload?.data) ? payload.data : [];
}

/**
 * The contract does not say what a line PUT returns. When it hands back the whole version
 * we use it directly (one round trip instead of two); when it does not, the caller refetches.
 */
export async function updatePOVersionLine(
  versionId: string,
  lineId: string,
  body: POLineUpdateBody,
): Promise<POVersion | null> {
  const response = await apiFetch(
    `${BASE}/purchase-order-versions/${versionId}/lines/${lineId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not save this line'));
  return asVersionOrNull(await readJson(response));
}

/**
 * NOT in the contract: the contract has a PUT for lines only, and the confirm screen has to
 * let a person fix a misread PO number or date before it binds (AC-D3: every extracted field
 * is editable before approval). Flagged to integration.
 */
export async function updatePOVersionHeader(
  versionId: string,
  body: Partial<POVersionHeader>,
): Promise<POVersion | null> {
  const response = await apiFetch(`${BASE}/purchase-order-versions/${versionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Could not save these header fields'),
    );
  return asVersionOrNull(await readJson(response));
}

/**
 * Read this document again, on the same version.
 *
 * `POST /purchase-order-versions/{id}/retry-extraction` -> the whole version body, back on
 * `queued`. 409 when there is nothing to retry: the read is genuinely still in flight, the
 * document has already been read, or the version is confirmed. The 409 message says which,
 * and is shown where the button is.
 *
 * This exists because a read can end without anything being written onto the row: the
 * background work-horse can be killed, and a process that is killed does not run its own
 * error handling. Re-uploading was the only way out of that, which loses the version
 * number and the history for a document that was never the problem.
 */
export async function retryPOExtraction(versionId: string): Promise<POVersion | null> {
  const response = await apiFetch(
    `${BASE}/purchase-order-versions/${versionId}/retry-extraction`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not start another read'));
  return asVersionOrNull(await readJson(response));
}

/** 409 while any annotation is still proposed. The message is shown where the button is. */
export async function confirmPOVersion(versionId: string): Promise<POVersion | null> {
  const response = await apiFetch(
    `${BASE}/purchase-order-versions/${versionId}/confirm`,
    {
      method: 'POST',
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not confirm this PO'));
  return asVersionOrNull(await readJson(response));
}

export async function approvePurchaseOrder(poId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/approve`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not approve this PO'));
}

export async function countersignPurchaseOrder(poId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/countersign`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not countersign this PO'));
}

export async function acceptPOAnnotation(
  annotationId: string,
  note?: string | null,
): Promise<void> {
  const response = await apiFetch(`${BASE}/po-annotations/${annotationId}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(note ? { note } : {}),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not accept this note'));
}

export async function editPOAnnotation(
  annotationId: string,
  body: POAnnotationEditBody,
): Promise<void> {
  const response = await apiFetch(`${BASE}/po-annotations/${annotationId}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Could not save your reading of this note'),
    );
}

export async function rejectPOAnnotation(
  annotationId: string,
  note: string,
): Promise<void> {
  const response = await apiFetch(`${BASE}/po-annotations/${annotationId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not reject this note'));
}

/**
 * A body we may or may not get. Several of these endpoints are documented as "no body" on
 * the way in and say nothing about the way out, so an empty 204 must not throw.
 */
async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function asVersionOrNull(payload: unknown): POVersion | null {
  if (!payload || typeof payload !== 'object') return null;
  const candidate = payload as Partial<POVersion>;
  return Array.isArray(candidate.lines) && candidate.totals
    ? (payload as POVersion)
    : null;
}
