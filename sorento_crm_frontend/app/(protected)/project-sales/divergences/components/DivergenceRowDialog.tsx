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
import type {
  DivergenceResolution,
  DivergenceRow,
} from '../../_shared/types/soDivergence.types';

interface DivergenceRowDialogProps {
  row: DivergenceRow;
  resolution: DivergenceResolution;
  submitting: boolean;
  onDone: () => void;
  onResolve: (reason: string) => Promise<unknown>;
}

/**
 * The reason box (AC-N7).
 *
 * Every answer carries one, so this dialog is not skippable for either side. The copy
 * changes with the resolution because accepting theirs and keeping ours have different
 * consequences, and a single neutral sentence would describe neither honestly.
 *
 * The header case is called out explicitly: accepting AutoCount's terms records the
 * decision and changes nothing, because the customer's own document is not AutoCount's to
 * edit. Left unsaid, a reviewer would reasonably expect the PO to be rewritten.
 */
export function DivergenceRowDialog({
  row,
  resolution,
  submitting,
  onDone,
  onResolve,
}: DivergenceRowDialogProps) {
  const [reason, setReason] = React.useState('');
  const acceptingTheirs = resolution === 'accept_theirs';
  const trimmed = reason.trim();

  const consequence = React.useMemo(() => {
    if (!acceptingTheirs) {
      return 'Our values stay as they are, and a corrective file is prepared to send back to AutoCount.';
    }
    if (row.scope === 'header') {
      return 'The decision is recorded. The customer PO is not rewritten: their document is the fact, and AutoCount’s copy of it is not.';
    }
    if (row.presence === 'ours_only') {
      return 'This line is cancelled to zero rather than deleted, so its allocations, claims and purchasing instructions keep their history.';
    }
    if (row.presence === 'theirs_only') {
      return 'This line is added to our sales order, at AutoCount’s quantity, price and delivery date.';
    }
    return 'Our line takes AutoCount’s values and the order total is recalculated.';
  }, [acceptingTheirs, row.presence, row.scope]);

  const subject =
    row.scope === 'header' ? 'the document header' : row.product_code || 'this line';

  return (
    <Dialog open onOpenChange={(open) => (!open ? onDone() : undefined)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {acceptingTheirs ? 'Accept AutoCount' : 'Keep our value'} for {subject}
          </DialogTitle>
          <DialogDescription>{consequence}</DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="divergence-reason">Why does this side win?</Label>
            <Textarea
              id="divergence-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              placeholder={
                acceptingTheirs
                  ? 'e.g. the customer cut the quantity by phone and CS keyed it in AutoCount'
                  : 'e.g. the customer PO says 600, AutoCount was mis-keyed'
              }
            />
            <p className="text-xs text-muted-foreground">
              Recorded against this row with your name and the time, so the decision can be
              read back later.
            </p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDone} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={submitting || trimmed.length === 0}
            onClick={async () => {
              await onResolve(trimmed);
              onDone();
            }}
          >
            {submitting
              ? 'Recording…'
              : acceptingTheirs
                ? 'Accept AutoCount'
                : 'Keep ours'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
