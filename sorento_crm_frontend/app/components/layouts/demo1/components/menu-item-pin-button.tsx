'use client';

import { Star } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useQuickAccess, useAddQuickAccess } from '@/hooks/useQuickAccess';
import { useHasPermission } from '@/hooks/usePermissions';
import { cn } from '@/lib/utils';

interface MenuItemPinButtonProps {
  path: string;
  title?: string;
  className?: string;
  /** Use smaller icon for nested menu items */
  size?: 'sm' | 'default';
}

export function MenuItemPinButton({ path, title, className, size = 'default' }: MenuItemPinButtonProps) {
  const canPin = useHasPermission('menu.quick_access.pin');
  const { data: items = [] } = useQuickAccess();
  const addMutation = useAddQuickAccess();
  const isPinned = items.some((i) => i.path === path);
  const iconSize = size === 'sm' ? 'size-3.5' : 'size-4';

  if (!canPin) return null;

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (isPinned) return;
    addMutation.mutate({ path });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      if (isPinned) return;
      addMutation.mutate({ path });
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="button"
          tabIndex={0}
          aria-label={isPinned ? 'In Quick Access' : 'Add to Quick Access'}
          className={cn(
            'inline-flex shrink-0 items-center justify-center rounded-md opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            size === 'sm' ? 'size-6' : 'size-7',
            className
          )}
          onClick={handleClick}
          onKeyDown={handleKeyDown}
        >
          <Star
            className={cn(
              iconSize,
              isPinned ? 'fill-primary text-primary' : 'text-muted-foreground'
            )}
          />
        </span>
      </TooltipTrigger>
      <TooltipContent side="right">
        {isPinned ? 'In Quick Access' : 'Add to Quick Access'}
      </TooltipContent>
    </Tooltip>
  );
}
