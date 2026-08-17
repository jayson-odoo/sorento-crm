'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

/**
 * Pressing Edit on a quotation the customer already holds.
 *
 * The client chose this over the two alternatives, and the reasons are worth keeping: leaving
 * Edit disabled is what they were already complaining about ("i don't know when can i edit and
 * when i cannot ... idk why it can't edit"), and branching silently would mint a revision nobody
 * asked for. So Edit stays pressable, and it says what it is about to do.
 *
 * One confirm reaches an editable copy. What was sent is untouched, which is the sentence that
 * actually answers the worry behind the question.
 */
export function ReviseToEditDialog({
  open,
  onOpenChange,
  scopeLabels,
  nextVersionLabel,
  isRevising,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The scopes that are frozen, named rather than counted: a person recognises the names. */
  scopeLabels: string[];
  /** What the copy will be called, e.g. "v3". Null when the scopes disagree about their number. */
  nextVersionLabel: string | null;
  isRevising: boolean;
  onConfirm: () => Promise<void>;
}) {
  const scopes =
    scopeLabels.length === 0
      ? 'this quotation'
      : scopeLabels.length === 1
        ? `"${scopeLabels[0]}"`
        : `${scopeLabels.length} scopes`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>This version is with the customer</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {`Editing opens the next version of ${scopes}${
            nextVersionLabel ? ` (${nextVersionLabel})` : ''
          } and carries the lines across. What was already sent stays exactly as it was sent.`}
        </DialogDescription>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={isRevising} onClick={() => void onConfirm()}>
            {isRevising ? 'Opening...' : 'Open a new version and edit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
