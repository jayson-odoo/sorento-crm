'use client';

import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * SCM uploads - the "Reading the file..." line, in a row that is ALWAYS there.
 *
 * One component for all three upload dialogs, which used to hold three identical copies of
 * this row. Two things about it are load-bearing, and both were found by measuring the real
 * dialog against the captain's 27,192-row book rather than by reading the markup.
 *
 * **The row keeps its height whether or not it is reading.** Mounting it on press grew the
 * dialog by 36px, and `DialogContent` is centred with `translate-y-[-50%]`, so the whole
 * popup jumped up 18px when Test was pressed and back down when the answer arrived. Hidden
 * with `invisible` rather than unmounted: the space stays reserved, and `visibility: hidden`
 * takes it out of the accessibility tree, so nothing announces a file being read when none is.
 *
 * **The spinner is clipped to its own 16px box.** A rotating square's border box grows to
 * `16 * sqrt(2)` = 22.6px at 45 degrees, and a CSS transform still contributes to an ancestor
 * scroll container's SCROLLABLE OVERFLOW. `DialogBody` is `overflow-y-auto` with no padding,
 * so while the spinner turned, its corners pushed the body's `scrollHeight` one pixel past
 * `clientHeight` and back, every animation frame: the body flipped between scrollable and not
 * about sixty times a second. Where the platform draws a classic space-taking scrollbar
 * (Windows, or macOS set to always show them) that is a 15px width change per frame - the
 * body's `clientWidth` was measured flipping 718 <-> 703 - which reflows its contents and
 * shakes the popup. `overflow-hidden` on a fixed-size wrapper clips the rotation away; the
 * icon's ink is a circle inscribed in that box, so nothing visible is lost.
 */
export function UploadReadingIndicator({
  reading,
  className,
}: {
  reading: boolean;
  className?: string;
}) {
  return (
    <div
      data-slot="upload-reading-indicator"
      className={cn(
        'flex min-h-5 items-center gap-2 text-sm text-muted-foreground',
        !reading && 'invisible',
        className,
      )}
    >
      <span className="flex size-4 shrink-0 items-center justify-center overflow-hidden">
        <LoaderCircle className={cn('size-4', reading && 'animate-spin')} aria-hidden />
      </span>
      Reading the file...
    </div>
  );
}

export default UploadReadingIndicator;
