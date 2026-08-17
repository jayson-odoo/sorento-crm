/** A Respond.io contact as the outbound switch screen sees it.
 *
 * `id` is the internal `respond_contacts.id`. It is the mutation target and the
 * DataGrid row key - it is NEVER rendered (no UUIDs in the UI).
 */
export interface RespondContactOutboundRow {
  id: string;
  name: string | null;
  phone_number: string | null;
  respond_io_id: string | null;
  outbound_enabled: boolean;
}

/** The at-a-glance audit: how many contacts we can currently message. */
export interface RespondOutboundCounts {
  enabled: number;
  disabled: number;
  total: number;
}

export interface RespondContactOutboundListResponse {
  data: RespondContactOutboundRow[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
  /** Whole-table counts, NOT the filtered page - the kill switch is global. */
  counts: RespondOutboundCounts;
}

export interface RespondContactOutboundBulkResult {
  requested: number;
  changed: number;
  counts: RespondOutboundCounts;
}

/** Which slice of contacts the grid is showing. */
export type OutboundFilter = 'all' | 'enabled' | 'disabled';
