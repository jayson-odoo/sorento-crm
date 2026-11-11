'use client';

import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { MenuItemState } from '../../_shared/po-link/poLinkWording';

/**
 * AC-LINK-CRM-UI (mock v4, owner 4 Nov: "click rows to decide"): the drill group's ONE action,
 * "Decide (N)" over the ticked lines - the shape of the OI Lines tab's
 * `order-inquiries/[id]/components/ReserveDecideControl.tsx` and Fulfilment Planning's
 * `BoardDecideControl.tsx`. Greyed at 0 with the reason as its title. A greyed item stays in
 * the menu with its reason under it (AutoCount not ready, switched off here): never hidden.
 */
export interface DecideItem extends MenuItemState {
  key: string;
  label: string;
  onSelect: () => void;
}

export function SnapshotDecideControl({
  count,
  items,
  onOpenChange,
}: {
  count: number;
  /** Reserve first, then the PO items; an empty group is not rendered. */
  items: DecideItem[][];
  onOpenChange?: (open: boolean) => void;
}) {
  const enabled = count > 0;
  const groups = items.filter((group) => group.length > 0);
  return (
    <DropdownMenu onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild disabled={!enabled}>
        <Button
          type="button"
          size="sm"
          disabled={!enabled}
          title={enabled ? undefined : 'Tick the lines to decide on'}
          data-testid="snapshot-decide-button"
        >
          {`Decide (${count})`}
          <ChevronDown className="size-4" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        {groups.map((group, index) => (
          <div key={group[0].key}>
            {index > 0 ? <DropdownMenuSeparator /> : null}
            {group.map((item) => (
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
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
