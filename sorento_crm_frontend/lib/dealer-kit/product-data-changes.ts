/**
 * Pinned product data, what changed under it, and the versions that record it
 * (r9 S5/D16-D19).
 *
 * ADR 0008 resolves a tag's product data LIVE on every render, which is right
 * for a design being drawn and wrong for one that has been sent for approval: a
 * price edited in master data on Tuesday silently rewrote the proof the
 * salesperson approved on Monday. So the data is PINNED when marketing starts
 * designing, the live resolve keeps running beside it, and the difference is
 * shown to a person who decides. Nothing on a tag changes without that decision.
 *
 * ## Expected API contract (Phase 1: the store below stands in)
 *
 * Every resolver read (`POST .../resolve-prices`, the CRM and portal design
 * payloads, the print payload) answers PINNED values, and a non-terminal
 * request also carries, per line:
 *
 * ```
 * data_changes: [
 *   {
 *     field: "name" | "dimensions" | "spec_lines" | "list_price" |
 *            "offer_price" | "barcode" | "set_members" | "set_price" |
 *            "spec:<key>" | "image:<attachment_id>",
 *     label: string,          // "List price", "Spec: Bowl depth", "Photo"
 *     old:   string | null,   // already formatted for display
 *     new:   string | null,
 *     old_image_url?: string | null,   // image fields only
 *     new_image_url?: string | null,
 *     note?: string | null    // "Promotion ended" when the offer goes null
 *   }
 * ]
 * ```
 *
 * A terminal request never carries the key at all: nothing can be updated, so
 * running the live resolve to say so is work with no reader.
 *
 * ```
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/lines/{lineId}/pin
 *   { action: "update" | "keep" }
 *   200 { line_id, pinned_at }
 *   update = snapshot the draft as "Before product update: <fields>", then
 *            overwrite the pin and clear the ack hash
 *   keep   = store the live hash as the ack, so the same change stops asking
 *
 * GET  /api/v1/dealer-kit/price-tag-requests/{id}/versions
 *   200 [{ version, commit_message, created_by_name, created_at }]  newest first
 * GET  /api/v1/dealer-kit/price-tag-requests/{id}/versions/{version}
 *   200 the design payload for that version (doc, lines, assets, images, fonts)
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/versions/{version}/restore
 *   200 { version }   the NEW snapshot, written as "Restored v<n>", carrying
 *                     the restored doc and the restored pins
 * ```
 */

export interface LineDataChange {
  field: string;
  label: string;
  old: string | null;
  new: string | null;
  old_image_url?: string | null;
  new_image_url?: string | null;
  /** "Promotion ended" and friends: why the value moved, when that is not obvious. */
  note?: string | null;
}

/** One line's worth of pending decision, as a page reads it. */
export interface LineDataChangeSet {
  line_id: string;
  /** The line's code, so no id reaches a screen. */
  code: string;
  name: string;
  changes: LineDataChange[];
}

export interface RequestVersionSummary {
  version: number;
  commit_message: string | null;
  created_by_name: string | null;
  created_at: string;
}

/** How many lines are waiting on a decision. What the card pill counts. */
export function changedLineCount(sets: LineDataChangeSet[]): number {
  return sets.filter((set) => set.changes.length > 0).length;
}

/** The field names an "Update tag" version message lists. */
export function changedFieldLabels(changes: LineDataChange[]): string {
  return changes.map((change) => change.label).join(', ');
}

// ---------------------------------------------------------------------------
// PHASE 1 MOCK - deleted when the pin column, the diff and the versions exist
// ---------------------------------------------------------------------------

/**
 * The diff and the version history, in memory.
 *
 * There is no pin column yet, so nothing can differ from it: a walk of this
 * screen needs the change to come from somewhere, and seeding it here is what
 * lets every state (no changes, one line, several lines, a promotion that
 * ended, a photo swapped) be seen before the backend exists. The version list
 * starts from whatever a request already has and grows as Update tag and
 * Restore write to it, so the two halves of the slice can be walked together.
 */
const changeSets = new Map<string, LineDataChangeSet[]>();
const versions = new Map<string, RequestVersionSummary[]>();

export function mockListDataChanges(requestId: string): LineDataChangeSet[] {
  return [...(changeSets.get(requestId) ?? [])];
}

export function mockSeedDataChanges(
  requestId: string,
  sets: LineDataChangeSet[],
): void {
  changeSets.set(requestId, sets);
}

/** `keep` and `update` both end the question; only `update` writes a version. */
export function mockResolveLinePin(
  requestId: string,
  lineId: string,
  action: 'update' | 'keep',
): void {
  const current = changeSets.get(requestId) ?? [];
  const target = current.find((set) => set.line_id === lineId);
  if (action === 'update' && target && target.changes.length > 0) {
    mockAddVersion(
      requestId,
      `Before product update: ${changedFieldLabels(target.changes)}`,
    );
  }
  changeSets.set(
    requestId,
    current.map((set) =>
      set.line_id === lineId ? { ...set, changes: [] } : set,
    ),
  );
}

export function mockListVersions(requestId: string): RequestVersionSummary[] {
  return [...(versions.get(requestId) ?? [])].sort(
    (a, b) => b.version - a.version,
  );
}

export function mockAddVersion(
  requestId: string,
  commitMessage: string,
): RequestVersionSummary {
  const existing = versions.get(requestId) ?? [];
  const next: RequestVersionSummary = {
    version: existing.reduce((max, row) => Math.max(max, row.version), 0) + 1,
    commit_message: commitMessage,
    created_by_name: 'You',
    created_at: new Date().toISOString(),
  };
  versions.set(requestId, [...existing, next]);
  return next;
}

export function mockSeedVersions(
  requestId: string,
  rows: RequestVersionSummary[],
): void {
  versions.set(requestId, rows);
}

export function _resetProductDataMock(): void {
  changeSets.clear();
  versions.clear();
}

/** The seeds on `window`, for a Phase 1 browser walk. Goes with the store. */
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__ptagDataMock = {
    seedChanges: mockSeedDataChanges,
    seedVersions: mockSeedVersions,
    listChanges: mockListDataChanges,
    listVersions: mockListVersions,
    reset: _resetProductDataMock,
  };
}
