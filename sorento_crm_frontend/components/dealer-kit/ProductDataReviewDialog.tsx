'use client';

/**
 * What changed under a tag, and the two things a person can do about it
 * (r9 S5/D18).
 *
 * Old on the left, new on the right, one row per field, because the question
 * being asked is "is this new value the one you want printed" and that cannot
 * be answered without seeing both. Keep current and Update tag are equally
 * legitimate answers - a price that moved after the salesperson approved the
 * proof is often exactly the thing NOT to print - so neither is styled as the
 * safe one.
 */

import { useState } from 'react';
import { Check, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { LineDataChangeSet } from '@/lib/dealer-kit/product-data-changes';

interface ProductDataReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The line under review. Null closes the dialog. */
  changeSet: LineDataChangeSet | null;
  onDecide: (action: 'update' | 'keep') => Promise<void>;
}

export default function ProductDataReviewDialog({
  open,
  onOpenChange,
  changeSet,
  onDecide,
}: ProductDataReviewDialogProps) {
  const [busy, setBusy] = useState<'update' | 'keep' | null>(null);

  const decide = async (action: 'update' | 'keep') => {
    setBusy(action);
    try {
      await onDecide(action);
      onOpenChange(false);
    } finally {
      setBusy(null);
    }
  };

  if (!open || !changeSet) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Product data changed</DialogTitle>
          <DialogDescription>
            {changeSet.code}
            {changeSet.name ? ` / ${changeSet.name}` : ''}
          </DialogDescription>
        </DialogHeader>

        <div
          className="max-h-[60dvh] overflow-y-auto"
          data-testid="product-data-review-rows"
        >
          {changeSet.changes.map((change) => (
            <div
              key={change.field}
              className="grid grid-cols-1 gap-2 border-b py-3 last:border-b-0 sm:grid-cols-[9rem_1fr_1fr] sm:gap-3"
            >
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {change.label}
              </span>
              <div className="min-w-0">
                <p className="text-2xs uppercase tracking-wide text-muted-foreground">
                  On the tag
                </p>
                <ChangeValue
                  value={change.old}
                  imageUrl={change.old_image_url}
                  muted
                />
              </div>
              <div className="min-w-0">
                <p className="text-2xs uppercase tracking-wide text-muted-foreground">
                  Now in the product
                </p>
                <ChangeValue value={change.new} imageUrl={change.new_image_url} />
                {change.note && (
                  <p className="mt-0.5 text-xs text-amber-700">{change.note}</p>
                )}
              </div>
            </div>
          ))}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            disabled={busy !== null}
            onClick={() => void decide('keep')}
          >
            <RotateCcw className="size-4 mr-1" />
            {busy === 'keep' ? 'Keeping...' : 'Keep current'}
          </Button>
          <Button disabled={busy !== null} onClick={() => void decide('update')}>
            <Check className="size-4 mr-1" />
            {busy === 'update' ? 'Updating...' : 'Update tag'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChangeValue({
  value,
  imageUrl,
  muted,
}: {
  value: string | null;
  imageUrl?: string | null;
  muted?: boolean;
}) {
  if (imageUrl !== undefined) {
    return imageUrl ? (
      <img
        src={imageUrl}
        alt={value ?? 'Product photo'}
        className="mt-1 size-16 rounded border object-contain"
      />
    ) : (
      <p className="mt-1 text-sm text-muted-foreground">No photo</p>
    );
  }
  return (
    <p
      className={`mt-1 whitespace-pre-wrap break-words text-sm ${muted ? 'text-muted-foreground line-through' : ''}`}
    >
      {value === null || value === '' ? '-' : value}
    </p>
  );
}
