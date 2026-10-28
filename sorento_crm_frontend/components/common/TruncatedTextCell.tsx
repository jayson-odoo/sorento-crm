'use client';

import * as React from 'react';
import { Eye } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

/**
 * Single-line truncated cell with an eye icon to open the full text in a dialog.
 *
 * Use for any potentially-long text in DataGrid or `<table>` cells (project title,
 * lead title, quotation title, descriptions). Keeps row height tight; user can
 * click the icon to see the full content. Click events on the icon don't
 * propagate to the surrounding row.
 */
export type TruncatedTextCellProps = {
  text: string | null | undefined;
  /** Optional wrapper for the visible label (e.g. red `RecordLink`). When provided, the wrapper renders the truncated text. */
  renderLabel?: (truncated: React.ReactNode) => React.ReactNode;
  /** Title shown at the top of the dialog. Defaults to "Full text". */
  dialogTitle?: string;
  /** Override className on the truncated label span. */
  className?: string;
  /** Visible lines before the text clamps: 1 (default) or 2. */
  lines?: 1 | 2;
};

export function TruncatedTextCell({
  text,
  renderLabel,
  dialogTitle = 'Full text',
  className,
  lines = 1,
}: TruncatedTextCellProps) {
  const [open, setOpen] = React.useState(false);
  const [clamped, setClamped] = React.useState(false);
  const labelRef = React.useRef<HTMLSpanElement | null>(null);
  const value = (text ?? '').toString();
  const hasValue = value.trim().length > 0;

  React.useLayoutEffect(() => {
    const el = labelRef.current;
    if (!el) return;
    const measure = () =>
      setClamped(el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [value, lines, hasValue]);

  if (!hasValue) return <span className="text-muted-foreground"> - </span>;
  const showExpand = clamped;

  const truncated = (
    <span
      ref={labelRef}
      className={cn(
        'block max-w-full align-middle',
        lines === 2 ? 'line-clamp-2 break-words' : 'truncate',
        className,
      )}
      title={value}
    >
      {value}
    </span>
  );

  return (
    <span className="flex min-w-0 items-center gap-1">
      <span className="block min-w-0 flex-1">
        {renderLabel ? renderLabel(truncated) : truncated}
      </span>
      {showExpand ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Show full title"
          className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
        >
          <Eye className="size-4" />
        </Button>
      ) : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
          </DialogHeader>
          <p className="whitespace-pre-wrap break-words text-sm text-foreground">{value}</p>
        </DialogContent>
      </Dialog>
    </span>
  );
}
