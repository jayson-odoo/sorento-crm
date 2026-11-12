'use client';

import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export interface AutocountDecideItem {
  key: string;
  label: string;
  enabled: boolean;
  /** Shown under a greyed item: why it cannot run now. */
  reason: string | null;
  onSelect: () => void;
}

/**
 * The Decide menu for AutoCount actions (the shape of the Stock Debt drill's Decide control).
 * A greyed item stays in the menu with its reason under it, never hidden. The caller renders it
 * only when the switch is on and the permission is held.
 */
export function AutocountDecideMenu({
  label,
  items,
}: {
  label: string;
  items: AutocountDecideItem[];
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" size="sm" variant="outline">
          {label}
          <ChevronDown className="size-4" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        {items.map((item) => (
          <DropdownMenuItem
            key={item.key}
            disabled={!item.enabled}
            onSelect={item.onSelect}
            className="flex flex-col items-start gap-0.5"
          >
            <span>{item.label}</span>
            {!item.enabled && item.reason ? (
              <span className="text-xs text-muted-foreground">{item.reason}</span>
            ) : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
