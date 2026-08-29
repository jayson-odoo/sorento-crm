'use client';

import { ReactNode } from 'react';
import { Cog, MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
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
  /** Ad-hoc menu items. Used by the 15 call sites that predate `actions`. */
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

  // Nothing to show is not an empty menu, it is no menu at all: an entity whose
  // actions are all permission-filtered away must not leave a dead button behind.
  if (actions && actions.length === 0 && !children) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant={trigger === 'ellipsis' ? 'ghost' : 'outline'}
          size="icon"
          aria-label={ariaLabel}
          disabled={disabled}
          className={className}
        >
          <TriggerIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {actions ? <RecordActionMenuItems actions={actions} /> : children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
