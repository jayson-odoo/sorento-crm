import { Boxes, Trash2 } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

/**
 * Builds the "Actions" dropdown items for the proforma-invoices bulk strip - same pattern
 * as the Purchase Orders book's `buildPoBulkActions` (mirrored per the captain's ask: one
 * selection mechanism, one Actions menu, serving both a convert and a delete). Pure +
 * unit-testable.
 *
 * Gating:
 *  - Convert applies to the WHOLE selection, any suppliers - a container is routinely
 *    several factories' PIs, so picking more than one is the normal case, not an edge one.
 *  - Delete applies to the WHOLE selection too. Blocked (already-converted) invoices are
 *    named in the RESULT, not filtered out of the button here - the operator selects
 *    invoices without having to know in advance which ones will refuse.
 *  - Both surface whenever anything is selected; if nothing is selected, NO action applies
 *    → returns `[]` so the Actions button does not render.
 */
export interface ProformaBulkActionState {
  /** How many rows are selected in total - both actions act on the whole selection. */
  selectedCount: number;
}

export interface ProformaBulkActionHandlers {
  onConvert: () => void;
  onDelete: () => void;
}

export function buildProformaBulkActions(
  state: ProformaBulkActionState,
  handlers: ProformaBulkActionHandlers,
): ToolbarAction[] {
  if (state.selectedCount === 0) return [];
  return [
    {
      key: 'bulk-convert',
      label: `Convert ${state.selectedCount} to draft shipment`,
      icon: Boxes,
      onClick: handlers.onConvert,
    },
    {
      key: 'bulk-delete',
      label: `Delete ${state.selectedCount}`,
      icon: Trash2,
      onClick: handlers.onDelete,
      destructive: true,
    },
  ];
}
