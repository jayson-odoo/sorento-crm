'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

const MAX_INLINE_BADGES = 2;

/**
 * Single-line access-levels cell. Renders up to {@link MAX_INLINE_BADGES} badges
 * on one row, then a compact "+N" chip that opens a Popover listing ALL levels.
 * Keeps the row height fixed - badges never wrap (see review item A). Folders
 * have no access levels and render nothing (the column passes `levels: []`).
 */
export default function AccessLevelsCell({
  levels,
  nameByCode,
}: {
  /** De-duplicated access-level codes for the file. Empty -> renders a dash. */
  levels: string[];
  nameByCode: Map<string, string>;
}) {
  const [open, setOpen] = useState(false);
  if (levels.length === 0) {
    return <span className="text-muted-foreground">-</span>;
  }

  const labelFor = (code: string) => nameByCode.get(code) ?? code;
  const inline = levels.slice(0, MAX_INLINE_BADGES);
  const overflow = levels.slice(MAX_INLINE_BADGES);

  return (
    <div className="flex min-w-0 items-center gap-1">
      {inline.map((code) => (
        <Badge
          key={code}
          variant="secondary"
          className="max-w-[100px] shrink truncate text-[10px]"
          title={labelFor(code)}
        >
          {labelFor(code)}
        </Badge>
      ))}
      {overflow.length > 0 && (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="shrink-0 rounded-full border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/70"
              aria-label={`Show ${overflow.length} more access level(s)`}
              onClick={(e) => {
                e.stopPropagation();
                setOpen((v) => !v);
              }}
            >
              +{overflow.length}
            </button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            className="w-56 p-2"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-1.5 text-xs font-medium">Access levels</p>
            <div className="flex flex-wrap gap-1">
              {levels.map((code) => (
                <Badge key={code} variant="secondary" className="text-[10px]">
                  {labelFor(code)}
                </Badge>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
