'use client';

/**
 * One collapsible card used four times by the price tag form (D-P1): Customer,
 * Sales Order & Lines, Price, Additional Information. A header button toggles
 * the body; a collapsed section with values shows a one-line summary (AC-P9).
 *
 * Motion (AC-U1, D-M1, review round 2): section expand/collapse gets NO
 * animation at all - the body appears and disappears instantly, on tap and on
 * Enter / Space alike - the shared Collapsible primitive's height keyframes
 * are switched off here rather than reused as-is (same call
 * `ContainerRequestSection.tsx` made for its own fold).
 */
import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { Card } from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

export function FormSection({
  title,
  titleId,
  summary,
  open,
  onOpenChange,
  children,
  className,
}: {
  title: string;
  /**
   * Id on the rendered title text, for a control inside the section (e.g. a
   * radiogroup) to reference via `aria-labelledby` instead of repeating the
   * section's own name as a second, visible label.
   */
  titleId?: string;
  /** One-line description shown only while collapsed (AC-P9); omitted when empty. */
  summary?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn('overflow-hidden', className)}>
      <Collapsible open={open} onOpenChange={onOpenChange}>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          >
            <span className="min-w-0">
              <span id={titleId} className="block text-base font-semibold">
                {title}
              </span>
              {!open && summary && (
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={summary}
                >
                  {summary}
                </span>
              )}
            </span>
            <ChevronDown
              className={cn(
                'size-4 shrink-0 text-muted-foreground transition-transform',
                open && 'rotate-180',
              )}
              aria-hidden
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-none data-[state=open]:animate-none">
          <div className="space-y-4 border-t px-4 py-4">{children}</div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
