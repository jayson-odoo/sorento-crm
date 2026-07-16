import { Check, X } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

/**
 * Builds the "Actions" dropdown items for the reorder RESULTS bulk strip
 * (M4-D9/D13), gated by the current selection — same pattern as the Unified
 * Drive's `buildDriveBulkActions`. Pure, so the selection-gating is
 * unit-testable without the DataGrid stack.
 *
 * Gating:
 *  - Accept and Reject apply ONLY to still-PENDING (proposed) recommendations in
 *    the selection; each acts on that subset. Adjust is single-row only (never a
 *    bulk action).
 *  - If the selection contains no pending recs (all already decided), NO action
 *    applies → returns `[]` so the Actions button does not render.
 */
export interface ResultsBulkActionState {
  /** How many selected rows are still pending (proposed) — the actionable subset. */
  pendingCount: number;
}

export interface ResultsBulkActionHandlers {
  onAccept: () => void;
  onReject: () => void;
}

export function buildResultsBulkActions(
  state: ResultsBulkActionState,
  handlers: ResultsBulkActionHandlers,
): ToolbarAction[] {
  if (state.pendingCount === 0) return [];
  return [
    { key: 'bulk-accept', label: 'Accept', icon: Check, onClick: handlers.onAccept },
    { key: 'bulk-reject', label: 'Reject', icon: X, destructive: true, onClick: handlers.onReject },
  ];
}
