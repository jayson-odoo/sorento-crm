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

import type { ReactElement, ReactNode } from 'react';
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
  /**
   * The countdown of an action parked on this record (D7, S6-06), for the record
   * page to pass to `DetailActions` as `pendingAction`. Null while nothing is
   * parked, and null on a list row, where the countdown travels to a toast.
   */
  pending?: ReactNode;
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

/**
 * The items as an ARRAY, not a fragment.
 *
 * A gear whose other items are a workflow (the SLA tracking one, say) splices
 * these in among its own children, and `DetailActionsMenu` can only see a
 * destructive item, and move it last, if the array is flattened into its
 * children rather than hidden inside one fragment.
 */
export function recordActionItems(actions: RecordAction[]): ReactElement[] {
  return actions.map((action) => (
    <DropdownMenuItem
      key={action.key}
      variant={action.kind === 'destructive' ? 'destructive' : undefined}
      disabled={action.disabled}
      onSelect={() => action.run()}
    >
      {action.icon && <action.icon className="size-4" />}
      {action.label}
    </DropdownMenuItem>
  ));
}

/** The menu items themselves, so the gear and the row "..." render one list. */
export function RecordActionMenuItems({ actions }: { actions: RecordAction[] }) {
  const { secondary, destructive } = orderRecordActions(actions);

  return (
    <>
      {recordActionItems(secondary)}
      {secondary.length > 0 && destructive.length > 0 && <DropdownMenuSeparator />}
      {recordActionItems(destructive)}
    </>
  );
}
