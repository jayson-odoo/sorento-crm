/**
 * Cross-Entity Activity Timeline types.
 *
 * A higher-level, human-readable view over the backend `audit_logs` table.
 * Unlike the raw Audit Logs page, the timeline groups entries by day and by
 * `trace_id` (a single user action that changed multiple rows), resolves
 * entity IDs to human labels, and renders change diffs in plain language.
 *
 * PHASE-1 PROTOTYPE — shapes may still shift after sign-off. See
 * `services/activityService.ts` for the proposed real API contract.
 */

/** Entity families that emit audit rows today. Drives badge colour + label prefix. */
export type ActivityEntityType =
  | 'complaint'
  | 'order'
  | 'user'
  | 'supplier'
  | 'promotion'
  | 'form'
  | 'ticket'
  | 'stock_inquiry'
  | 'purchase_request'
  | 'product';

/** Normalised action verb. Backend INSERT/CREATE collapse to "created". */
export type ActivityAction = 'created' | 'updated' | 'deleted';

/** A single field-level change within an activity item. */
export interface ActivityChange {
  field: string; // human label, e.g. "Status"
  from?: string | null; // previous value, human-readable ("—" when absent)
  to?: string | null; // new value, human-readable
}

/** One row of the timeline (one audit_logs row, label-resolved). */
export interface ActivityItem {
  id: string;
  entity_type: ActivityEntityType;
  /**
   * Human-readable entity label resolved by the backend, e.g.
   * "Complaint CMP-1023", "Order SO-5567", "User Jane Tan".
   * The FE never renders raw entity UUIDs.
   */
  entity_label: string;
  /** Deep-link to the entity detail page, when one exists. */
  entity_href?: string | null;
  action: ActivityAction;
  /** Resolved actor display name; null/"System" for backend-driven changes. */
  actor_name?: string | null;
  actor_avatar_url?: string | null;
  changed_at: string; // ISO datetime (UTC)
  /** Short one-line summary, e.g. "status: pending → resolved". */
  summary?: string | null;
  /** Structured field diffs (optional; summary is the fallback). */
  changes?: ActivityChange[];
  /**
   * Groups rows produced by one user action across multiple entities.
   * Items sharing a trace_id are badged as "one action".
   */
  trace_id?: string | null;
}

/** Timeline items bucketed under a calendar day for the grouped render. */
export interface ActivityDayGroup {
  /** yyyy-MM-dd key used for grouping/labelling. */
  date_key: string;
  /** Human day label, e.g. "Today", "Yesterday", "28 Jun 2026". */
  label: string;
  items: ActivityItem[];
}

/** Lightweight actor option for the user filter. */
export interface ActivityActorOption {
  id: string;
  name: string;
}

/** Response envelope the timeline expects from the backend. */
export interface ActivityFeedResponse {
  items: ActivityItem[];
  /** Distinct actors seen in the (unfiltered) window — powers the user filter. */
  actors: ActivityActorOption[];
  pagination: {
    page: number;
    limit: number;
    total: number;
  };
}

/** Client-side filter state shared between the toolbar and the hook. */
export interface ActivityFilters {
  entity_types: ActivityEntityType[];
  action?: ActivityAction;
  user_id?: string;
  date_from?: string; // yyyy-MM-dd
  date_to?: string; // yyyy-MM-dd
  q?: string;
  /** Show only rows in one grouped multi-row action. */
  trace_id?: string;
}
