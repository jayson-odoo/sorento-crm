/**
 * Status engine types (ADR-0001).
 *
 * Contract mirrors `app/schemas/status.py`. Two fields carry meaning that is easy
 * to lose:
 *
 * - `key` is the machine identifier and the roll-up axis. A forked graph reuses the
 *   same key for the same rung, which is what makes cross-template reporting work.
 *   `category` is cosmetic only; never branch on it.
 * - `resolved_scope_id` / `is_fork` tell you whether you are looking at a scope's
 *   own forked graph or the default it inherits. Editing the default changes every
 *   scope that inherits it, so the UI has to say which one is on screen.
 */

export type TriggerMode = 'manual' | 'auto';

export interface StatusEntity {
  entity_type: string;
  label: string;
  module: string;
  supports_scoped_graphs: boolean;
  scope_label: string;
  required_flags: string[];
}

export interface Status {
  id: string;
  entity_type: string;
  scope_id: string | null;
  key: string;
  label: string;
  category: string | null;
  color_hex: string | null;
  description: string | null;
  sort_order: number;
  is_initial: boolean;
  is_terminal: boolean;
  is_active: boolean;
  is_archived: boolean;
  is_default: boolean;
  is_system: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  /** Live records holding this status. Present only when requested with counts. */
  record_count?: number | null;
}

export interface StatusTransition {
  id: string;
  entity_type: string;
  scope_id: string | null;
  from_status_id: string;
  to_status_id: string;
  label: string;
  sort_order: number;
  trigger_mode: TriggerMode;
  conditions_json: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface StatusGraph {
  entity_type: string;
  requested_scope_id: string | null;
  resolved_scope_id: string | null;
  is_fork: boolean;
  statuses: Status[];
  transitions: StatusTransition[];
}

export interface StatusCreateBody {
  entity_type: string;
  scope_id?: string | null;
  key: string;
  label: string;
  category?: string | null;
  color_hex?: string | null;
  description?: string | null;
  sort_order?: number;
  is_initial?: boolean;
  is_terminal?: boolean;
  is_active?: boolean;
  is_archived?: boolean;
  is_default?: boolean;
}

export type StatusUpdateBody = Partial<Omit<StatusCreateBody, 'entity_type' | 'scope_id'>>;

export interface TransitionCreateBody {
  entity_type: string;
  from_status_id: string;
  to_status_id: string;
  label: string;
  sort_order?: number;
  trigger_mode?: TriggerMode;
  conditions_json?: Record<string, unknown> | null;
}

export type TransitionUpdateBody = Partial<
  Omit<TransitionCreateBody, 'entity_type' | 'from_status_id' | 'to_status_id'>
>;

export interface StatusMigrateResult {
  migrated: number;
  from_status_id: string;
  to_status_id: string;
}
