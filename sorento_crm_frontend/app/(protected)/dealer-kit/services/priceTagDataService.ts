/**
 * The product-data gate and the request's own version history (r9 S5/D16-D19).
 *
 * ## API contract
 *
 * ```
 * GET  /api/v1/dealer-kit/price-tag-requests/{id}/data-changes
 *   200 [{ tag_id, tag_label, line_id, code, name, changes: LineDataChange[] }]
 *   The same diff the resolver computes per TAG; a terminal request answers
 *   an empty list, because nothing on it can be updated.
 *
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/tags/{tagId}/pin
 *   { action: "update" | "keep" }
 *   200 { tag_id, pinned_at }
 *   update = snapshot the draft as "Before product update: <fields>", then
 *            overwrite the pin and clear the ack
 *   keep   = store the live hash as the ack, so the same change stops asking
 *
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/data-changes/recheck
 *   200 [{ tag_id, tag_label, line_id, code, name, changes: LineDataChange[] }]
 *   Clears every tag's Keep ack and answers the same shape the GET does -
 *   "Check product data" re-arms a gate a Keep silenced (owner round finding 3).
 *
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/tags/{tagId}/dismiss   (r10 S8)
 *   200 { tag_id }
 *   Clears the tag's `data_updated_at` / `data_update_changes` /
 *   `data_update_version` - the person has seen what the auto-update did.
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
  TagDataChangeSet,
  RequestVersionSummary,
} from '@/lib/dealer-kit/product-data-changes';

export type { TagDataChangeSet, RequestVersionSummary };

const BASE = '/api/v1/dealer-kit/price-tag-requests';

async function unwrap<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await extractApiError(response, fallback));
  }
  return response.json();
}

/** What has changed under this request since its tags' data was pinned. */
export async function listTagDataChanges(
  requestId: string,
): Promise<TagDataChangeSet[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/data-changes`,
  );
  return unwrap<TagDataChangeSet[]>(
    response,
    'Failed to load the product changes',
  );
}

/**
 * "Check product data" (owner round finding 3): forgets every Keep on this
 * request and re-runs the comparison, so a red dot silenced once is not
 * silenced forever - a later, unrelated edit trips the gate again.
 */
export async function recheckTagDataChanges(
  requestId: string,
): Promise<TagDataChangeSet[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/data-changes/recheck`,
    { method: 'POST' },
  );
  return unwrap<TagDataChangeSet[]>(
    response,
    'Failed to recheck the product data',
  );
}

/**
 * Answer one TAG's question (D18).
 *
 * `update` snapshots the design as it stands BEFORE it takes the new values,
 * so the tag is always one Restore away from what it was; `keep` records the
 * ack so the same change stops asking.
 */
export async function resolveTagPin(
  requestId: string,
  tagId: string,
  action: 'update' | 'keep',
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/tags/${encodeURIComponent(tagId)}/pin`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    },
  );
  await unwrap<unknown>(response, 'Failed to apply that decision');
}

/**
 * r10 S8: the auto-update indicator's Dismiss. Nothing on the tag moves -
 * the new data is already pinned - so this only clears the three "updated"
 * columns and the red dot they light.
 */
export async function dismissTagDataUpdate(
  requestId: string,
  tagId: string,
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/tags/${encodeURIComponent(tagId)}/dismiss`,
    { method: 'POST' },
  );
  await unwrap<unknown>(response, 'Failed to dismiss the update');
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
