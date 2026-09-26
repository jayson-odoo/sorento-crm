'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  FINDING_SEVERITY_BADGE_VARIANT,
  FINDING_SEVERITY_LABEL,
  FINDING_SOURCE_LABEL,
  type FlagItem,
} from '../../_shared/lib/findings';

/**
 * A row's Flag (S7-3): one compact pill, the most severe open item's words and how many
 * items the row carries, opening a popover with one entry per item and its Dismiss (owner
 * lesson (b), S6 hand test: no expanded cards under a row, the row stays one line high).
 *
 * Holds no grid, so it is not a floating-surface site for the nested-grid census.
 */
export function SalesOrderFlagCell({
  items,
  label,
  canDismiss,
  onDismiss,
}: {
  items: FlagItem[];
  /** What the row is, for the trigger's accessible name ("line 4", "CB1178A"). */
  label: string;
  /** Null while nothing may be dismissed from here (a reader, a published order, an edit). */
  canDismiss: ((item: FlagItem) => boolean) | null;
  onDismiss: (item: FlagItem) => void;
}) {
  const [open, setOpen] = React.useState(false);
  if (items.length === 0) return <span className="text-muted-foreground">-</span>;

  const openItems = items.filter((item) => item.open);
  const lead = openItems[0];
  const pill = lead ? FINDING_SEVERITY_LABEL[lead.severity] : 'Dismissed';
  const count = openItems.length > 1 ? openItems.length : null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex max-w-full items-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`${pill}${count ? `, ${count} findings` : ''} on ${label}`}
        >
          <Badge
            variant={lead ? FINDING_SEVERITY_BADGE_VARIANT[lead.severity] : 'secondary'}
            appearance="light"
            size="sm"
            className="max-w-full truncate"
          >
            {count ? `${pill} ${count}` : pill}
          </Badge>
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] space-y-2">
          {items.map((item) => {
            const sources = Array.from(new Set(item.members.map((member) => member.source)));
            const dismissed = item.members[0].finding;
            return (
              <div key={item.key} className="space-y-1.5 rounded-md border border-border px-3 py-2">
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <Badge
                    variant={item.open ? FINDING_SEVERITY_BADGE_VARIANT[item.severity] : 'secondary'}
                    appearance="light"
                    size="sm"
                  >
                    {item.open ? FINDING_SEVERITY_LABEL[item.severity] : 'Dismissed'}
                  </Badge>
                  <span>{sources.map((source) => FINDING_SOURCE_LABEL[source]).join(' and ')}</span>
                  {item.members.length > 1 && <span>{`${item.members.length} findings`}</span>}
                </div>
                {Array.from(new Set(item.members.map((member) => member.finding.detail))).map(
                  (detail) => (
                    <p key={detail} className="break-words text-sm">
                      {detail}
                    </p>
                  ),
                )}
                {!item.open && (
                  <p className="break-words text-xs text-muted-foreground">
                    {[dismissed.acknowledged_by_name, dismissed.acknowledged_reason]
                      .filter(Boolean)
                      .join(': ') || '-'}
                  </p>
                )}
                {item.open && canDismiss?.(item) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setOpen(false);
                      onDismiss(item);
                    }}
                  >
                    Dismiss with a reason
                  </Button>
                )}
              </div>
            );
          })}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
