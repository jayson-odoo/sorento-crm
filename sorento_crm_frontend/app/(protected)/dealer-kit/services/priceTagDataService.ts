/**
 * The product-data gate and the request's own version history (r9 S5/D16-D19).
 *
 * The contract, the row shapes and the Phase 1 store all live in
 * `lib/dealer-kit/product-data-changes.ts`; this is the CRM's door to them.
 * Each function below becomes an `apiFetch` in Phase 2 and no caller changes.
 */

import {
  mockAddVersion,
  mockListDataChanges,
  mockListVersions,
  mockResolveLinePin,
  type LineDataChangeSet,
  type RequestVersionSummary,
} from '@/lib/dealer-kit/product-data-changes';

export type { LineDataChangeSet, RequestVersionSummary };

/**
 * What has changed under this request since its data was pinned.
 *
 * ```
 * The resolver carries `data_changes` per line on every read of a
 * non-terminal request (`POST .../resolve-prices` and the design payloads),
 * so Phase 2 reads it off the rows the page already has instead of asking
 * again. Terminal requests never carry it.
 * ```
 */
export async function listLineDataChanges(
  requestId: string,
): Promise<LineDataChangeSet[]> {
  return mockListDataChanges(requestId);
}

/**
 * Answer one line's question (D18).
 *
 * ```
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/lines/{lineId}/pin
 *   { action: "update" | "keep" }
 * ```
 *
 * `update` snapshots the current draft as "Before product update: <fields>"
 * BEFORE it overwrites the pin, so the design as it stood is always one
 * Restore away; `keep` records the ack so the same change stops asking.
 */
export async function resolveLinePin(
  requestId: string,
  lineId: string,
  action: 'update' | 'keep',
): Promise<void> {
  mockResolveLinePin(requestId, lineId, action);
}

/** "Update all" (D18): the same call per changed line, in one go. */
export async function updateAllLinePins(
  requestId: string,
  lineIds: string[],
): Promise<void> {
  for (const lineId of lineIds) {
    mockResolveLinePin(requestId, lineId, 'update');
  }
}

/** `GET .../versions` - newest first. */
export async function listRequestVersions(
  requestId: string,
): Promise<RequestVersionSummary[]> {
  return mockListVersions(requestId);
}

/**
 * `POST .../versions/{version}/restore` - writes the version's doc and pins
 * back onto the draft, then snapshots the result as "Restored v<n>".
 *
 * Not a confirmation dialog and not a deferred action: it writes a NEW
 * version rather than destroying one, so the way back is the list itself.
 */
export async function restoreRequestVersion(
  requestId: string,
  version: number,
): Promise<RequestVersionSummary> {
  return mockAddVersion(requestId, `Restored v${version}`);
}
