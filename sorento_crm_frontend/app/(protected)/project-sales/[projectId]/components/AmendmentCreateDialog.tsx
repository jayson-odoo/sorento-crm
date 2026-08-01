'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { AmendmentCreated, AmendmentPreview } from '../../_shared/types/projectSalesOrder.types';

/**
 * Turns a preview into a proposed amendment.
 *
 * Preview writes nothing; this is the step that does, so it takes a reason and states what
 * it leaves behind: an amendment and a change notice, both waiting for review.
 */
export function AmendmentCreateDialog({
  preview,
  onDone,
  onConfirm,
  submitting,
}: {
  preview: AmendmentPreview;
  onDone: () => void;
  onConfirm: (reason: string) => Promise<AmendmentCreated>;
  submitting: boolean;
}) {
  const [reason, setReason] = React.useState('');
  const [created, setCreated] = React.useState<AmendmentCreated | null>(null);
  const trimmed = reason.trim();

  const rowCount = preview.rows.length;
  const verbs = Object.entries(preview.verb_summary).filter(([, count]) => count > 0);

  if (created) {
    return (
      <Dialog open onOpenChange={(next) => !next && onDone()}>
        <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
          <DialogHeader>
            <DialogTitle>Amendment proposed</DialogTitle>
            <DialogDescription>
              {`Change notice ${created.ocn_number} is drafted from this delta. Both wait for review.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" onClick={onDone}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Create the amendment</DialogTitle>
          <DialogDescription>
            {`${rowCount} row${rowCount === 1 ? '' : 's'} from ${
              preview.from.label || `version ${preview.from.version_no}`
            } to ${preview.to.label || `version ${preview.to.version_no}`}.`}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!trimmed) return;
            const result = await onConfirm(trimmed);
            setCreated(result);
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            {verbs.length > 0 && (
              <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                {verbs.map(([verbName, count]) => (
                  <li key={verbName}>{`${verbName}: ${count}`}</li>
                ))}
              </ul>
            )}
            {preview.unmatched.length > 0 && (
              <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40">
                {`${preview.unmatched.length} row${
                  preview.unmatched.length === 1 ? '' : 's'
                } could not be matched and are not in this amendment.`}
              </p>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="amendment-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="amendment-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                placeholder="What the customer asked for"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || submitting}>
              {submitting ? 'Creating…' : 'Create the amendment'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
