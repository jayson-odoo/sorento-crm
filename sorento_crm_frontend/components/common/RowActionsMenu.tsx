'use client';

import { DetailActionsMenu } from './DetailActionsMenu';
import type { RecordAction } from './recordActions';

export interface RowActionsMenuProps {
  /** The entity's action set - the same array the record page's gear renders. */
  actions: RecordAction[];
  /** e.g. "user", used for the trigger's accessible name. */
  ariaLabel?: string;
}

/**
 * The list row's "..." cell (D15).
 *
 * Replaces the icon-button `actions` columns: the row itself opens the record
 * (`rowHref`), so the cell carries only the secondary and destructive actions,
 * in the same order as the record page's gear.
 *
 * The row is a link, so the cell stops the click from bubbling - the menu is one
 * of the interactive controls a clickable row leaves alone (`ROW_INTERACTIVE_SELECTOR`
 * in `data-grid-table.tsx` matches the trigger button and the menu items).
 */
export function RowActionsMenu({ actions, ariaLabel = 'record' }: RowActionsMenuProps) {
  return (
    <div
      className="flex items-center justify-end"
      onClick={(event) => event.stopPropagation()}
    >
      <DetailActionsMenu
        actions={actions}
        trigger="ellipsis"
        ariaLabel={`${ariaLabel} actions`}
        className="size-7"
      />
    </div>
  );
}

export default RowActionsMenu;
