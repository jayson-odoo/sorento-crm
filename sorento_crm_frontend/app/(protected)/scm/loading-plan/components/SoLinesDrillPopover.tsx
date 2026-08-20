'use client';

import { ReactNode } from 'react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { formatDateInMalaysia } from '@/lib/helpers';
import { EM_DASH, fmtInt } from '../../lib/format';
import type { ContainerRequestSoLine } from '../../services/fulfilmentService';

/**
 * "What SO am I addressing" (6b.3): the open sales-order lines behind one product, or behind
 * one matrix cell - the SAME popover content either way, so the Open SOs drill and the
 * schedule matrix's cell drill can never disagree about what a figure is made of.
 *
 * A span with `onClick`+`stopPropagation` (not an escape route this section needs today, since
 * neither the table nor the matrix has a row-level click of its own - kept anyway so a trigger
 * embedded in a DataGrid row can never be mistaken for a click on the row itself, the same
 * guard `PlanLinesGrid.tsx`'s own `StopClick` exists for).
 *
 * Wrapped AROUND the whole `Popover`, never INSIDE `PopoverTrigger asChild`: Radix's `Slot`
 * only merges its injected `onClick`/`aria-*`/`ref` onto keys already present on its immediate
 * child's OWN props (`mergeProps` iterates `childProps`, not `slotProps`) - so putting this
 * plain-`children` wrapper directly under `asChild` silently drops every one of them, and the
 * trigger never opens. `PlanDemandPopover.tsx` / `ProductLocationsPopover.tsx` avoid this by
 * giving `asChild` a real DOM element (a `<button>`) as its immediate child; here the caller
 * supplies an arbitrary `trigger` node, so that element - not this wrapper - has to be what
 * `PopoverTrigger asChild` sees.
 *
 * `PopoverContent` is wrapped in `PopoverPortal` (captain, live test): this trigger sits inside
 * a `DataGrid` cell, whose sticky/pinned columns otherwise paint OVER the un-portaled default,
 * since a sibling with `position: sticky` wins the cell's own stacking context. Portaling to
 * `document.body` escapes that context entirely. `StopClick` still wraps the trigger for the
 * reason above; it does nothing for clicks inside the portaled content, but that content no
 * longer sits inside any row's click target, so there is nothing left for it to guard there.
 */
function StopClick({ children }: { children: ReactNode }) {
  return (
    <span onClick={(e) => e.stopPropagation()} className="contents">
      {children}
    </span>
  );
}

function classLabel(demandClass: string | null): string {
  if (demandClass === 'project') return 'Project';
  if (demandClass) return 'Retail';
  return 'Unclassified';
}

const CLASS_TONE: Record<string, string> = {
  Project: 'bg-primary/10 text-primary',
  Retail: 'bg-muted text-muted-foreground',
  Unclassified: 'bg-muted text-muted-foreground',
};

export function SoLinesDrillPopover({
  trigger,
  title,
  lines,
  align = 'end',
}: {
  trigger: ReactNode;
  title: string;
  lines: ContainerRequestSoLine[];
  align?: 'start' | 'end' | 'center';
}) {
  return (
    <StopClick>
      <Popover>
        <PopoverTrigger asChild>{trigger}</PopoverTrigger>
        <PopoverPortal>
          <PopoverContent className="w-96 p-0" align={align}>
            <div className="border-b border-border px-3 py-2">
              <h4 className="text-xs font-semibold">{title}</h4>
              <p className="text-2xs text-muted-foreground">
                {lines.length} SO line{lines.length === 1 ? '' : 's'}
              </p>
            </div>
            {/* Scroll after roughly ten rows, so a product with dozens of open lines does not
                push the popover off the screen. */}
            <div className="max-h-72 divide-y divide-border overflow-y-auto">
              {lines.length === 0 ? (
                <p className="p-3 text-center text-2xs text-muted-foreground">No lines here.</p>
              ) : (
                lines.map((l, i) => (
                  <div key={`${l.so_number ?? 'unnumbered'}-${i}`} className="p-2.5 text-2xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium" title={l.so_number ?? ''}>
                        {l.so_number ?? 'Not numbered'}
                      </span>
                      <span className="shrink-0 tabular-nums font-medium">{fmtInt(l.qty)}</span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2 text-muted-foreground">
                      <span className="truncate" title={l.customer_label ?? ''}>
                        {l.customer_label ?? EM_DASH}
                      </span>
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 ${CLASS_TONE[classLabel(l.demand_class)]}`}
                      >
                        {classLabel(l.demand_class)}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2 text-muted-foreground">
                      <span>
                        Ordered {l.order_date ? formatDateInMalaysia(l.order_date) : EM_DASH}
                      </span>
                      <span>
                        Needed {l.required_date ? formatDateInMalaysia(l.required_date) : EM_DASH}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </PopoverContent>
        </PopoverPortal>
      </Popover>
    </StopClick>
  );
}

export default SoLinesDrillPopover;
