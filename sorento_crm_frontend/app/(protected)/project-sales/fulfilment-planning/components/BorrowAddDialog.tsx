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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { BorrowCandidate } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * Borrowing takes exactly one approval: the CS actor who confirms the sales order, with
 * the donor's impact in front of them and a reason nobody can skip (AC-B09, AC-B10). So
 * the reason is mandatory here as well as at the Confirm gate, the same way the finding
 * acknowledgement takes one before it will submit.
 *
 * The donor is named by warehouse code or by project reference. The quantity offered is
 * what is free right now; taking all of it is allowed, and the card then shows what that
 * leaves the donor with.
 */
export function BorrowAddDialog({
  lineNo,
  itemCode,
  candidates,
  onDone,
  onAdd,
}: {
  lineNo: number;
  itemCode?: string | null;
  candidates: BorrowCandidate[];
  onDone: () => void;
  onAdd: (candidate: BorrowCandidate, qty: string, reason: string) => void;
}) {
  const [selectedKey, setSelectedKey] = React.useState(
    candidates[0] ? candidateKey(candidates[0]) : '',
  );
  const [qty, setQty] = React.useState(candidates[0]?.free_qty ?? '');
  const [reason, setReason] = React.useState('');

  const selected =
    candidates.find((candidate) => candidateKey(candidate) === selectedKey) ?? candidates[0];
  const trimmed = reason.trim();
  const amount = Number.parseFloat(qty);
  const valid = Boolean(selected) && Number.isFinite(amount) && amount > 0 && Boolean(trimmed);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Borrow for line {lineNo}</DialogTitle>
          <DialogDescription>{itemCode ?? 'This item'}</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!valid || !selected) return;
            onAdd(selected, qty.trim(), trimmed);
            onDone();
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            <fieldset className="space-y-2">
              <legend className="mb-1.5 text-sm font-medium">Source</legend>
              {candidates.map((candidate) => {
                const key = candidateKey(candidate);
                const donor =
                  candidate.source === 'other_project'
                    ? (candidate.donor_project_ref ?? 'Another project')
                    : candidate.warehouse_code;
                return (
                  <label
                    key={key}
                    htmlFor={`borrow-${lineNo}-${key}`}
                    className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 ${
                      key === selectedKey ? 'border-primary' : 'border-border'
                    }`}
                  >
                    <input
                      id={`borrow-${lineNo}-${key}`}
                      type="radio"
                      name={`borrow-source-${lineNo}`}
                      className="mt-1"
                      checked={key === selectedKey}
                      onChange={() => {
                        setSelectedKey(key);
                        setQty(candidate.free_qty);
                      }}
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium" title={donor}>
                        {donor}
                      </span>
                      <span className="block text-sm text-muted-foreground">
                        {candidate.source === 'other_project'
                          ? `Held at ${candidate.warehouse_code}. ${candidate.free_qty} free, ${candidate.donor_impact.committed_qty} committed.`
                          : `${candidate.free_qty} free, ${candidate.donor_impact.committed_qty} committed.`}
                      </span>
                      <span className="block text-sm text-muted-foreground">
                        {`Borrowing all of it leaves ${candidate.donor_impact.free_after_full_borrow} free.`}
                      </span>
                    </span>
                  </label>
                );
              })}
            </fieldset>

            <div className="space-y-1.5">
              <Label htmlFor={`borrow-qty-${lineNo}`}>Quantity</Label>
              <Input
                id={`borrow-qty-${lineNo}`}
                type="number"
                min="0"
                step="any"
                value={qty}
                onChange={(event) => setQty(event.target.value)}
                className="h-9 w-40 tabular-nums"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor={`borrow-reason-${lineNo}`}>
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id={`borrow-reason-${lineNo}`}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                placeholder="In your own words"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid}>
              Add the borrow
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function candidateKey(candidate: BorrowCandidate): string {
  return `${candidate.source}-${candidate.warehouse_code}-${candidate.donor_project_ref ?? ''}`;
}
