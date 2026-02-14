'use client';

import { ReactNode } from 'react';
import { Cog } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface DetailActionsMenuProps {
  /** Menu items (e.g. DropdownMenuItem). Use for status actions, export, etc. */
  children: ReactNode;
  /** Optional aria-label for the trigger button. */
  ariaLabel?: string;
  /** Optional class for the trigger button. */
  className?: string;
}

/**
 * Reusable gear-button dropdown for detail/form views.
 * Use for actions like "Change to pending approval", "Send for approval", "Export to Excel", etc.
 * Pass DropdownMenuItem(s) as children.
 */
export function DetailActionsMenu({
  children,
  ariaLabel = 'Actions',
  className,
}: DetailActionsMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          aria-label={ariaLabel}
          className={className}
        >
          <Cog className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
