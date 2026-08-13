'use client';

import { forwardRef, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { fmtInt } from '../../lib/format';

/**
 * One collapsible band of the plan.
 *
 * > "if i want to toggle between buy, covered by stock, stock allocation, is very hassle, I
 * >  want to see all in 1 page and 1 table ... i think the within budget and over budget is
 * >  quite good, the collapse function"
 *
 * The tiles used to SWAP the table, so answering "is any of this covered by stock?" meant
 * leaving the buys, looking, and coming back. Everything sits on one page now and the
 * sections fold, which is the same shape Within budget / Over budget already had.
 *
 * The count lives in the header rather than only in the tile, so a folded section still says
 * how much is inside it. A section with nothing in it stays foldable and says so - hiding it
 * would make "no exceptions" and "exceptions not computed" look identical.
 */
export const PlanSection = forwardRef<
  HTMLDivElement,
  {
    title: string;
    count?: number | null;
    /** Short note beside the count, e.g. what a decision here means. */
    hint?: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    children: ReactNode;
  }
>(function PlanSection({ title, count, hint, open, onOpenChange, children }, ref) {
  return (
    <div ref={ref} className="scroll-mt-4">
      <Collapsible open={open} onOpenChange={onOpenChange}>
        <Card className="overflow-hidden">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-3 text-start transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            >
              <ChevronDown
                className={cn(
                  'size-4 shrink-0 text-muted-foreground transition-transform',
                  !open && '-rotate-90',
                )}
                aria-hidden
              />
              <span className="text-sm font-semibold">{title}</span>
              {count != null ? (
                <span className="rounded-md bg-muted px-1.5 py-0.5 text-2xs font-medium tabular-nums text-muted-foreground">
                  {fmtInt(count)}
                </span>
              ) : null}
              {hint ? (
                <span className="ms-1 truncate text-2xs font-normal text-muted-foreground">
                  {hint}
                </span>
              ) : null}
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="border-t p-3">{children}</div>
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </div>
  );
});

export default PlanSection;
