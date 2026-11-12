'use client';

/**
 * A quotation line description, read-only (QUOTE-DESC-RICHTEXT). Styled text is the shared rich
 * text editor's HTML and is drawn by `RichTextView` (parsed into React elements, never
 * innerHTML). Plain text shows exactly as typed, angle brackets included, one line per line.
 */

import { RichTextView } from '@/components/dealer-kit/RichTextView';
import { isRich } from '@/lib/dealer-kit/rich-text';
import { cn } from '@/lib/utils';

export function RichDescription({
  value,
  className,
  empty = '-',
}: {
  value: string | null | undefined;
  className?: string;
  /** What an empty description shows. */
  empty?: string;
}) {
  if (!value?.trim()) return empty ? <span className={className}>{empty}</span> : null;
  if (!isRich(value)) {
    return <span className={cn('block whitespace-pre-line break-words', className)}>{value}</span>;
  }
  // RichTextView sets text-sm on its root; the caller's size wins through `className`.
  return <RichTextView value={value} className={cn('space-y-0', className)} />;
}

export default RichDescription;
