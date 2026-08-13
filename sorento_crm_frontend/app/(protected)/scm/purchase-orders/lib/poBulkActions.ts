import { CheckCircle2 } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

/**
 * Builds the "Actions" dropdown items for the Purchase Orders bulk strip
 * (M4-D6/D9), gated by the current selection - same pattern as the Unified
 * Drive's `buildDriveBulkActions`. Pure + unit-testable.
 *
 * Gating:
 *  - Confirm applies ONLY to DRAFT POs in the selection; it acts on that subset
 *    (already-active POs in the selection are skipped). Confirming assigns the
 *    canonical PO-YYYY-#### number and makes the PO count as on-order.
 *  - create-GR stays a per-row action on an active PO (not a bulk action).
 *  - If the selection contains no draft POs, NO action applies → returns `[]`
 *    so the Actions button does not render.
 */
export interface PoBulkActionState {
  /** How many selected rows are drafts - the confirmable subset. */
  draftCount: number;
}

export interface PoBulkActionHandlers {
  onConfirm: () => void;
}

export function buildPoBulkActions(
  state: PoBulkActionState,
  handlers: PoBulkActionHandlers,
): ToolbarAction[] {
  if (state.draftCount === 0) return [];
  return [
    { key: 'bulk-confirm', label: 'Confirm', icon: CheckCircle2, onClick: handlers.onConfirm },
  ];
}
