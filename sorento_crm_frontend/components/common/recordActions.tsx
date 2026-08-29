'use client';

/**
 * One action set per entity, shown in two places (D15).
 *
 * An entity declares its actions once, in
 * `app/(protected)/<module>/<entity>/actions.tsx`, as
 * `use<Entity>Actions(record) -> { actions, dialogs }`. The record page renders
 * them in the gear (`DetailActions`) and the list row renders the SAME array, in
 * the same order, in its "..." menu (`RowActionsMenu`), so an action can never be
 * reachable from one surface and missing from the other.
 *
 * Permissions are resolved once, inside the definition hook: an action the user
 * may not run is simply not in the array. That is why there is no `permission`
 * field here - nothing downstream could act on it, and a second check is a second
 * place to get it wrong.
 *
 * `dialogs` is the node the definition hook needs mounted (a confirm dialog, a
 * form). Both surfaces render it, so a list row and a record page open the very
 * same dialog. When S6 lands, a destructive action swaps its dialog for a pending
 * action + countdown and neither call site changes.
 */

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';

export interface RecordAction {
  /** Stable identity for the item, e.g. `user.impersonate`. */
  key: string;
  label: string;
  icon?: LucideIcon;
  /** `destructive` items are rendered last, after a separator, in red. */
  kind?: 'secondary' | 'destructive';
  disabled?: boolean;
  run: () => void;
}

/** What a `use<Entity>Actions` hook returns. */
export interface RecordActionSet {
  actions: RecordAction[];
  /** Mount this wherever the actions are rendered. */
  dialogs?: ReactNode;
}

/** Secondary items first, then a separator, then the destructive ones. */
export function orderRecordActions(actions: RecordAction[]): {
  secondary: RecordAction[];
  destructive: RecordAction[];
} {
  return {
    secondary: actions.filter((a) => a.kind !== 'destructive'),
    destructive: actions.filter((a) => a.kind === 'destructive'),
  };
}

/** The menu items themselves, so the gear and the row "..." render one list. */
export function RecordActionMenuItems({ actions }: { actions: RecordAction[] }) {
  const { secondary, destructive } = orderRecordActions(actions);

  return (
    <>
      {secondary.map((action) => (
        <DropdownMenuItem
          key={action.key}
          disabled={action.disabled}
          onSelect={() => action.run()}
        >
          {action.icon && <action.icon className="size-4" />}
          {action.label}
        </DropdownMenuItem>
      ))}
      {secondary.length > 0 && destructive.length > 0 && <DropdownMenuSeparator />}
      {destructive.map((action) => (
        <DropdownMenuItem
          key={action.key}
          variant="destructive"
          disabled={action.disabled}
          onSelect={() => action.run()}
        >
          {action.icon && <action.icon className="size-4" />}
          {action.label}
        </DropdownMenuItem>
      ))}
    </>
  );
}
