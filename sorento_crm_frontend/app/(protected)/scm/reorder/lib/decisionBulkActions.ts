import { Check, X } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

/**
 * Builds the "Actions" dropdown items for the reorder RESULTS bulk strip
 * (M4-D9/D13), gated by the current selection - same pattern as the Unified
 * Drive's `buildDriveBulkActions`. Pure, so the selection-gating is
 * unit-testable without the DataGrid stack.
 *
 * Gating - a decision is CHANGEABLE (a rejected buy can be re-accepted, an
 * accepted one re-rejected), so an action shows whenever it would change at least
 * one selected row:
 * - Accept shows unless EVERY selected row is already accepted (acts on the ones
 *    that aren't).
 * - Reject shows unless EVERY selected row is already rejected (acts on the rest).
 * - Both hidden only when the selection is empty. Adjust stays single-row only.
 */
export interface ResultsBulkActionState {
  /** Selected rows that aren't already accepted - Accept's target subset. */
  acceptCount: number;
  /** Selected rows that aren't already rejected - Reject's target subset. */
  rejectCount: number;
}

export interface ResultsBulkActionHandlers {
  onAccept: () => void;
  onReject: () => void;
}

export function buildResultsBulkActions(
  state: ResultsBulkActionState,
  handlers: ResultsBulkActionHandlers,
): ToolbarAction[] {
  const actions: ToolbarAction[] = [];
  if (state.acceptCount > 0) {
    actions.push({ key: 'bulk-accept', label: 'Accept', icon: Check, onClick: handlers.onAccept });
  }
  if (state.rejectCount > 0) {
    actions.push({ key: 'bulk-reject', label: 'Reject', icon: X, destructive: true, onClick: handlers.onReject });
  }
  return actions;
}
