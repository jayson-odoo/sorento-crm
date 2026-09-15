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
 * ## API contract
 *
 * Every resolver read (`POST .../resolve-prices`, the CRM and portal design
 * payloads, the print payload) answers PINNED values, and a non-terminal
 * request also carries, per TAG:
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
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/tags/{tagId}/pin
 *   { action: "update" | "keep" }
 *   200 { tag_id, pinned_at }
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

/**
 * One TAG's worth of pending decision, as a page reads it.
 *
 * Per tag rather than per line since the combos slice: a line may print several
 * tags and two of them resolve different products, so they change apart and a
 * Keep on one must not silence the other. `line_id` and `tag_label` are what
 * the reader is shown ("1a" under the line's code), never the ids.
 */
export interface TagDataChangeSet {
  tag_id: string;
  /** "1a", "1b" - the line's position plus a letter. Never an id. */
  tag_label: string;
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

/** How many tags are waiting on a decision. What the card pill counts. */
export function changedTagCount(sets: TagDataChangeSet[]): number {
  return sets.filter((set) => set.changes.length > 0).length;
}

/** The field names an "Update tag" version message lists. */
export function changedFieldLabels(changes: LineDataChange[]): string {
  return changes.map((change) => change.label).join(', ');
}
