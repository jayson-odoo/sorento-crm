/**
 * The product-data gate and the request's own version history (r9 S5/D16-D19).
 *
 * ## API contract
 *
 * ```
 * GET  /api/v1/dealer-kit/price-tag-requests/{id}/data-changes
 *   200 [{ line_id, code, name, changes: LineDataChange[] }]
 *   The same diff the resolver computes per line; a terminal request answers
 *   an empty list, because nothing on it can be updated.
 *
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/lines/{lineId}/pin
 *   { action: "update" | "keep" }
 *   200 { line_id, pinned_at }
 *   update = snapshot the draft as "Before product update: <fields>", then
 *            overwrite the pin and clear the ack
 *   keep   = store the live hash as the ack, so the same change stops asking
 *
 * GET  /api/v1/dealer-kit/price-tag-requests/{id}/versions
 *   200 [{ version, commit_message, created_by_name, created_at }] newest first
 * GET  /api/v1/dealer-kit/price-tag-requests/{id}/versions/{version}
 *   200 the design payload for THAT version (doc, lines, assets, images, fonts)
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/versions/{version}/restore
 *   200 { version }   the NEW snapshot, written as "Restored v<n>"
 * ```
 *
 * The row shapes live in `lib/dealer-kit/product-data-changes.ts`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  designPayloadFromResponse,
  type TagSheetDesignPayload,
} from '@/lib/dealer-kit/design-payload';
import type {
  LineDataChangeSet,
  RequestVersionSummary,
} from '@/lib/dealer-kit/product-data-changes';

export type { LineDataChangeSet, RequestVersionSummary };

const BASE = '/api/v1/dealer-kit/price-tag-requests';

async function unwrap<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await extractApiError(response, fallback));
  }
  return response.json();
}

/** What has changed under this request since its data was pinned. */
export async function listLineDataChanges(
  requestId: string,
): Promise<LineDataChangeSet[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/data-changes`,
  );
  return unwrap<LineDataChangeSet[]>(
    response,
    'Failed to load the product changes',
  );
}

/**
 * Answer one line's question (D18).
 *
 * `update` snapshots the design as it stands BEFORE it takes the new values,
 * so the tag is always one Restore away from what it was; `keep` records the
 * ack so the same change stops asking.
 */
export async function resolveLinePin(
  requestId: string,
  lineId: string,
  action: 'update' | 'keep',
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/lines/${encodeURIComponent(lineId)}/pin`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    },
  );
  await unwrap<unknown>(response, 'Failed to apply that decision');
}

/** "Update all" (D18): the same call per changed line, in order. */
export async function updateAllLinePins(
  requestId: string,
  lineIds: string[],
): Promise<void> {
  for (const lineId of lineIds) {
    await resolveLinePin(requestId, lineId, 'update');
  }
}

/** `GET .../versions` - newest first. */
export async function listRequestVersions(
  requestId: string,
): Promise<RequestVersionSummary[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/versions`,
  );
  return unwrap<RequestVersionSummary[]>(response, 'Failed to load the history');
}

/**
 * One version's own document and pins, for the shared lightbox (D19).
 *
 * A version IS a whole tag sheet, so it answers the same payload a live design
 * does - drawing today's draft under a version's name would tell the reader
 * that v1 looked like something it never looked like.
 */
export async function getRequestVersion(
  requestId: string,
  version: number,
): Promise<TagSheetDesignPayload> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/versions/${version}`,
  );
  return designPayloadFromResponse(
    await unwrap(response, 'Failed to load that version'),
  );
}

/**
 * `POST .../versions/{version}/restore` - the version's doc AND its pins.
 *
 * Not a deferred action and it asks nothing: it ADDS a version rather than
 * destroying one, so the way back is the list itself.
 */
export async function restoreRequestVersion(
  requestId: string,
  version: number,
): Promise<RequestVersionSummary> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/versions/${version}/restore`,
    { method: 'POST' },
  );
  return unwrap<RequestVersionSummary>(response, 'Failed to restore that version');
}
