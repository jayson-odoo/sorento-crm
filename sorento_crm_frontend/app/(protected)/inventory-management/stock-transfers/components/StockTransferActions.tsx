'use client';

import * as React from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useStockTransferMutations } from '../hooks/useStockTransfers';
import type { StockTransfer } from '../types/stockTransfer.types';

const MIN_REASON = 3;

/** Which of the three verbs a transfer in this state can still be given. */
export function availableActions(state: StockTransfer['state']): {
  approve: boolean;
  markMoved: boolean;
  cancel: boolean;
} {
  return {
    approve: state === 'proposed',
    markMoved: state === 'approved',
    cancel: state === 'proposed' || state === 'approved',
  };
}

export type TransferAction = 'approve' | 'mark-moved' | 'cancel';

/**
 * The three deliberate verbs, as three dialogs.
 *
 * ONE component for the row actions and the detail header, so the two cannot word an
 * approval two ways. Every verb confirms first: approving is a person telling a warehouse
 * to carry stock across the country, and one-click is exactly what the captain's ruling
 * ("a person needs to deliberately approve the transfer") rules out.
 */
export function StockTransferActionDialogs({
  transfer,
  action,
  onClose,
}: {
  transfer: StockTransfer | null;
  action: TransferAction | null;
  onClose: () => void;
}) {
  const { approve, markMoved, cancel } = useStockTransferMutations(transfer?.id);
  const [autocountRef, setAutocountRef] = React.useState('');
  const [reason, setReason] = React.useState('');
  const [touched, setTouched] = React.useState(false);

  React.useEffect(() => {
    if (!action) return;
    setAutocountRef('');
    setReason('');
    setTouched(false);
  }, [action, transfer?.id]);

  if (!transfer || !action) return null;

  const movement = `${transfer.qty} ${transfer.item_code ?? ''} ${transfer.from_location ?? '?'} to ${
    transfer.to_location ?? '?'
  }`.trim();

  if (action === 'approve') {
    return (
      <AlertDialog open onOpenChange={(next) => !next && onClose()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{`Approve ${transfer.transfer_no}?`}</AlertDialogTitle>
            <AlertDialogDescription>{movement}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={approve.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={approve.isPending}
              onClick={(event) => {
                event.preventDefault();
                approve.mutate(transfer.id, { onSuccess: onClose });
              }}
            >
              {approve.isPending ? 'Approving…' : 'Approve'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  if (action === 'mark-moved') {
    const ref = autocountRef.trim();
    return (
      <Dialog open onOpenChange={(next) => !next && onClose()}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{`Mark ${transfer.transfer_no} moved`}</DialogTitle>
            <DialogDescription>{movement}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="transfer-autocount-ref">
              AutoCount transfer number <span className="text-destructive">*</span>
            </Label>
            <Input
              id="transfer-autocount-ref"
              value={autocountRef}
              onChange={(event) => setAutocountRef(event.target.value)}
              onBlur={() => setTouched(true)}
              placeholder="e.g. ST-2026/08-0042"
              disabled={markMoved.isPending}
              aria-invalid={(touched && !ref) || undefined}
              aria-describedby={touched && !ref ? 'transfer-autocount-ref-error' : undefined}
            />
            {touched && !ref ? (
              <p id="transfer-autocount-ref-error" className="text-xs text-destructive">
                The AutoCount transfer number is required.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={onClose} disabled={markMoved.isPending}>
              Cancel
            </Button>
            <Button
              disabled={markMoved.isPending || !ref}
              onClick={() => {
                setTouched(true);
                if (!ref) return;
                markMoved.mutate(
                  { id: transfer.id, autocountRef: ref },
                  { onSuccess: onClose },
                );
              }}
            >
              {markMoved.isPending ? 'Saving…' : 'Mark moved'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  const trimmed = reason.trim();
  const tooShort = trimmed.length < MIN_REASON;
  return (
    <AlertDialog open onOpenChange={(next) => !next && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{`Cancel ${transfer.transfer_no}?`}</AlertDialogTitle>
          <AlertDialogDescription>{movement}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="transfer-cancel-reason">
            Reason <span className="text-destructive">*</span>
          </Label>
          <Textarea
            id="transfer-cancel-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="Why is this movement being called off?"
            rows={4}
            disabled={cancel.isPending}
            aria-invalid={(touched && tooShort) || undefined}
            aria-describedby={touched && tooShort ? 'transfer-cancel-reason-error' : undefined}
          />
          {touched && tooShort ? (
            <p id="transfer-cancel-reason-error" className="text-xs text-destructive">
              {`A reason of at least ${MIN_REASON} characters is required.`}
            </p>
          ) : null}
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={cancel.isPending}>Keep it</AlertDialogCancel>
          <AlertDialogAction
            disabled={cancel.isPending || tooShort}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={(event) => {
              event.preventDefault();
              setTouched(true);
              if (tooShort) return;
              cancel.mutate({ id: transfer.id, reason: trimmed }, { onSuccess: onClose });
            }}
          >
            {cancel.isPending ? 'Cancelling…' : 'Cancel transfer'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default StockTransferActionDialogs;
