'use client';

import { Children, isValidElement, ReactNode, useState } from 'react';
import { Cog, MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { RecordActionMenuItems, type RecordAction } from './recordActions';

interface DetailActionsMenuProps {
  /**
   * The entity's action set (D15). Rendered secondary items first, then a
   * separator, then the destructive ones in red. Prefer this over `children`:
   * the same array feeds the list row's "..." menu, so the two cannot drift.
   */
  actions?: RecordAction[];
  /**
   * Ad-hoc menu items, for the gears whose secondary actions are a WORKFLOW
   * rather than a record action set. An item marked `variant="destructive"` is
   * moved to the end behind a separator, exactly as `actions` mode does it, so
   * the two modes cannot look different.
   */
  children?: ReactNode;
  /** Gear on a record page, ellipsis in a list row. */
  trigger?: 'gear' | 'ellipsis';
  /** Optional aria-label for the trigger button. */
  ariaLabel?: string;
  /** Optional class for the trigger button. */
  className?: string;
  disabled?: boolean;
}

/**
 * Destructive children last, behind a separator.
 *
 * The rule lives here rather than in each of the fifteen workflow gears, because
 * a Delete that drifts up among the ordinary items, or loses the rule that sets
 * it apart, is exactly the regression this menu exists to prevent. Separators the
 * caller wrote are kept where they are; only a trailing one, left dangling once
 * the destructive items move, is dropped.
 */
function orderChildren(children: ReactNode): ReactNode {
  const flat = Children.toArray(children).filter(Boolean);
  const isDestructive = (node: unknown) =>
    isValidElement<{ variant?: string }>(node) && node.props.variant === 'destructive';

  const destructive = flat.filter(isDestructive);
  if (destructive.length === 0) return children;

  const secondary = flat.filter((node) => !isDestructive(node));
  const isSeparator = (node: unknown) =>
    isValidElement(node) && node.type === DropdownMenuSeparator;
  while (secondary.length > 0 && isSeparator(secondary[secondary.length - 1])) {
    secondary.pop();
  }

  return (
    <>
      {secondary}
      {secondary.length > 0 && <DropdownMenuSeparator />}
      {destructive}
    </>
  );
}

/**
 * Reusable dropdown of a record's secondary actions.
 * Use for actions like "Change to pending approval", "Send for approval", "Export to Excel", etc.
 * Pass the entity's `RecordAction[]` as `actions`, or DropdownMenuItem(s) as children.
 */
export function DetailActionsMenu({
  actions,
  children,
  trigger = 'gear',
  ariaLabel = 'Actions',
  className,
  disabled,
}: DetailActionsMenuProps) {
  const TriggerIcon = trigger === 'ellipsis' ? MoreHorizontal : Cog;
  const items = actions ? null : orderChildren(children);
  // Controlled so a confirmable item (Copy link's tick) can hold the menu open
  // through its own click and close it again once the confirmation has shown.
  const [open, setOpen] = useState(false);

  // Nothing to show is not an empty menu, it is no menu at all: an entity whose
  // actions are all permission-filtered away must not leave a dead button behind.
  if (actions && actions.length === 0 && !children) return null;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant={trigger === 'ellipsis' ? 'ghost' : 'outline'}
          size="icon"
          aria-label={ariaLabel}
          title={ariaLabel}
          disabled={disabled}
          className={className}
        >
          <TriggerIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {actions ? (
          <RecordActionMenuItems actions={actions} onRequestClose={() => setOpen(false)} />
        ) : (
          items
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
