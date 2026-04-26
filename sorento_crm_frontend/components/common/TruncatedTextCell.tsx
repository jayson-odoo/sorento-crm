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
  /** Hide eye icon if text is short enough — defaults to ``80`` chars. */
  expandThreshold?: number;
};

export function TruncatedTextCell({
  text,
  renderLabel,
  dialogTitle = 'Full text',
  className,
  expandThreshold = 80,
}: TruncatedTextCellProps) {
  const [open, setOpen] = React.useState(false);
  const value = (text ?? '').toString();
  if (!value.trim()) return <span className="text-muted-foreground">—</span>;
  const showExpand = value.length > expandThreshold;

  const truncated = (
    <span
      className={cn('block max-w-full truncate align-middle', className)}
      title={value}
    >
      {value}
    </span>
  );

  return (
    <div className="flex min-w-0 items-center gap-1">
      <div className="min-w-0 flex-1">
        {renderLabel ? renderLabel(truncated) : truncated}
      </div>
      {showExpand ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="View full text"
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
    </div>
  );
}
