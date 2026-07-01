/**
 * Types for the reusable BulkUpdateDialog (safe, whitelisted bulk edit).
 *
 * A list opts into bulk edit by declaring a WHITELIST of `BulkEditableField`s —
 * only these fields are editable, and (for `select`) only their `options` are
 * allowed values. This is deliberately NOT a "generic update any column" tool:
 * it drives a per-resource, per-field allow-list so the backend can run every
 * row through the normal update path (validation, business rules, side effects,
 * audit) instead of a raw column write.
 */

/** Input kind that drives which control the dialog renders for the chosen field. */
export type BulkEditableFieldType = 'select' | 'text' | 'user';

export interface BulkEditableFieldOption {
  value: string;
  label: string;
}

export interface BulkEditableField {
  /** Stable field key sent to the backend (e.g. `status`, `priority`, `assignee_id`). */
  key: string;
  /** Human-readable label shown in the field picker and the confirmation summary. */
  label: string;
  /** Control kind: `select` (allowed options), `text` (free input), `user` (user-select stub). */
  type: BulkEditableFieldType;
  /** Required when `type === 'select'`: the whitelist of allowed values. */
  options?: BulkEditableFieldOption[];
  /** Optional guidance shown under the value control. */
  helpText?: string;
}

/** One row the backend refused to update, with a human-readable reason. */
export interface BulkUpdateSkipped {
  id: string;
  /** Human-readable row label (NEVER a raw UUID in the UI). */
  label: string;
  reason: string;
}

/** Partial-result summary returned by `onApply`. */
export interface BulkUpdateResult {
  updated: number;
  skipped: BulkUpdateSkipped[];
}
