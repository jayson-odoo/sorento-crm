import { CheckCircle2, Trash2 } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

/**
 * Builds the "Actions" dropdown items for the Purchase Orders bulk strip
 * (M4-D6/D9, plus bulk delete - captain, 20 Aug), gated by the current
 * selection - same pattern as the Unified Drive's `buildDriveBulkActions`.
 * Pure + unit-testable.
 *
 * Gating:
 *  - Confirm applies ONLY to DRAFT POs in the selection; it acts on that subset
 *    (already-active POs in the selection are skipped). Confirming assigns the
 *    canonical PO-YYYY-#### number and makes the PO count as on-order.
 *  - Delete applies to the WHOLE selection regardless of status - draft or
 *    active, a purchase order the buyer selects is one they want gone. It
 *    surfaces whenever anything is selected, independently of Confirm.
 *  - create-GR stays a per-row action on an active PO (not a bulk action).
 *  - If nothing applies to the selection (nothing selected at all), NO action
 *    applies → returns `[]` so the Actions button does not render.
 */
export interface PoBulkActionState {
  /** How many selected rows are drafts - the confirmable subset. */
  draftCount: number;
  /** How many rows are selected in total - the deletable set. */
  selectedCount: number;
}

export interface PoBulkActionHandlers {
  onConfirm: () => void;
  onDelete: () => void;
}

export function buildPoBulkActions(
  state: PoBulkActionState,
  handlers: PoBulkActionHandlers,
): ToolbarAction[] {
  const actions: ToolbarAction[] = [];
  if (state.draftCount > 0) {
    actions.push({
      key: 'bulk-confirm',
      label: `Confirm ${state.draftCount} draft${state.draftCount === 1 ? '' : 's'}`,
      icon: CheckCircle2,
      onClick: handlers.onConfirm,
    });
  }
  if (state.selectedCount > 0) {
    actions.push({
      key: 'bulk-delete',
      label: `Delete ${state.selectedCount}`,
      icon: Trash2,
      onClick: handlers.onDelete,
      destructive: true,
    });
  }
  return actions;
}
