'use client';

/**
 * ACC-COPY-TO-PRODUCTS: copy this product's "Accessories included" list to hand-picked products.
 * The parent mounts it only while open, so every open starts from a clean slate.
 *
 * Plan: documentation/plans/dealer-kit/PLAN-acc-copy-to-products-09nov.md. Two steps in one
 * modal: pick on the system product grid (search, Category / Brand filters, shift / drag ticks,
 * "Select all N"), then a confirm that reads the server's dry run, then one write.
 */

import { useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useCopyProductAccessories } from '../../../accessories/hooks/useAccessories';
import type { AccessoryCopySummary } from '../../../accessories/services/accessoryService';
import {
  CopyCapNote,
  MAX_COPY_TARGETS,
  pickedLine,
  plural,
  useProductTargetPicker,
} from './ProductTargetPicker';

export { MAX_COPY_TARGETS };

/** The confirm step's sentences, from the dry run. */
export function copySummaryLines(summary: AccessoryCopySummary): string[] {
  const lines = [`${plural(summary.targets, 'product')} picked.`];
  const fresh = summary.targets - summary.targets_with_a_list;
  if (fresh > 0) {
    lines.push(
      `${plural(fresh, 'product')} with no list ${fresh === 1 ? 'gets' : 'get'} the whole list.`,
    );
  }
  if (summary.targets_with_a_list > 0) {
    lines.push(
      `${plural(summary.targets_with_a_list, 'product')} already ${summary.targets_with_a_list === 1 ? 'has a list: its' : 'have a list: their'} entries stay, the missing ones are added at the end.`,
    );
  }
  lines.push(
    `${plural(summary.entries_added, 'entry')} will be added` +
      (summary.entries_already_there > 0
        ? `, ${plural(summary.entries_already_there, 'entry')} already there ${summary.entries_already_there === 1 ? 'is' : 'are'} left as ${summary.entries_already_there === 1 ? 'it is' : 'they are'}.`
        : '.'),
  );
  if (summary.box_style_set > 0) {
    lines.push(
      `The box style is set on ${plural(summary.box_style_set, 'product')} that had none.`,
    );
  }
  return lines;
}

export function CopyAccessoriesDialog({
  open,
  onOpenChange,
  sourceProductId,
  entryCount,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  sourceProductId: string;
  /** Entries on the source's saved list, for the title. */
  entryCount: number;
}) {
  const [summary, setSummary] = useState<AccessoryCopySummary | null>(null);
  const { preview, copy } = useCopyProductAccessories(sourceProductId);
  const { picked, overCap, grid } = useProductTargetPicker(sourceProductId);

  const goToConfirm = () => {
    preview.mutate(picked, { onSuccess: setSummary });
  };

  const runCopy = () => {
    copy.mutate(picked, { onSuccess: () => onOpenChange(false) });
  };

  const busy = preview.isPending || copy.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="flex max-h-[90dvh] w-[calc(100vw-2rem)] max-w-5xl flex-col"
        aria-describedby={undefined}
      >
        <DialogHeader>
          {/* pe-8: clear of the close X at 375px (#2280 hand-test leftover). */}
          <DialogTitle className="pe-8">
            {summary
              ? 'Copy accessories'
              : `Copy ${plural(entryCount, 'entry')} to other products`}
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto">
          {summary ? (
            <div
              className="space-y-2 text-sm"
              data-testid="copy-accessories-summary"
            >
              {copySummaryLines(summary).map((line) => (
                <p key={line}>{line}</p>
              ))}
              <CopyCapNote />
            </div>
          ) : (
            grid
          )}
        </DialogBody>
        <DialogFooter className="flex-wrap items-center gap-2">
          {!summary ? (
            <span
              className="mr-auto text-sm text-muted-foreground"
              aria-live="polite"
            >
              {pickedLine(picked.length)}
            </span>
          ) : null}
          {summary ? (
            <Button
              variant="outline"
              onClick={() => setSummary(null)}
              disabled={busy}
            >
              Back
            </Button>
          ) : (
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={busy}
            >
              Cancel
            </Button>
          )}
          {summary ? (
            <Button onClick={runCopy} disabled={busy}>
              {copy.isPending ? (
                <LoaderCircle className="mr-1 size-4 animate-spin" />
              ) : null}
              Copy
            </Button>
          ) : (
            <Button
              onClick={goToConfirm}
              disabled={busy || picked.length === 0 || overCap}
            >
              {preview.isPending ? (
                <LoaderCircle className="mr-1 size-4 animate-spin" />
              ) : null}
              Next
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default CopyAccessoriesDialog;
