'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * The chevrons and the counter, and nothing else.
 *
 * Where a record is walked by URL, `ListPager` owns the position and hands it
 * here (that is every detail page). Where it is walked IN PLACE - a dialog
 * stepping through the rows it was opened over, or a record whose id is a pair
 * rather than a row id - the caller computes the position from the rows it
 * already holds and hands it here directly.
 *
 * Both chevrons are `type="button"`: the five edit forms render the pager inside
 * their `<form>`, and an untyped `<button>` there is a SUBMIT button, so Next
 * saved the record and followed the form's onSuccess instead of stepping.
 *
 * Until S3 this component also knew how to fetch neighbours from the backend and
 * how to walk a whole list itself. Both went with the `/neighbours` endpoints:
 * a pager that resolves its own set is a pager that can disagree with the list
 * the reader is looking at.
 */
export interface RecordNavigationProps {
  /** 1-based position on the page, or null when it is not known yet. */
  index: number | null;
  /** Rows on the page being walked. */
  total: number;
  hasPrevious: boolean;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  isLoading?: boolean;
  /** e.g. "delivery order" - used for the chevrons' accessible names. */
  ariaLabel?: string;
  className?: string;
  /**
   * Stays mounted, both chevrons inert. For the one caller that keeps the pager
   * on screen while it no longer means anything to click - a client-side route
   * change fires no `beforeunload` and would drop an in-progress edit draft.
   */
  disabled?: boolean;
}

export default function RecordNavigation({
  index,
  total,
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  isLoading = false,
  ariaLabel = 'record',
  className,
  disabled = false,
}: RecordNavigationProps) {
  const counterLabel =
    isLoading && index == null
      ? total > 0
        ? `… / ${total}`
        : '…'
      : total > 0
        ? index != null && index > 0
          ? `${index} / ${total}`
          : `- / ${total}`
        : null;

  return (
    <div
      className={['flex items-center gap-2', className].filter(Boolean).join(' ')}
      aria-label={`${ariaLabel} navigation`}
    >
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={`Previous ${ariaLabel}`}
        disabled={disabled || !hasPrevious}
        onClick={onPrevious}
      >
        <ChevronLeft className="size-4" />
      </Button>
      {counterLabel != null && (
        <span
          className="min-w-[3rem] text-center text-sm text-muted-foreground tabular-nums"
          aria-label={
            index != null && index > 0
              ? `${index} of ${total} records`
              : `Position unknown within ${total} records on this page`
          }
        >
          {counterLabel}
        </span>
      )}
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={`Next ${ariaLabel}`}
        disabled={disabled || !hasNext}
        onClick={onNext}
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
