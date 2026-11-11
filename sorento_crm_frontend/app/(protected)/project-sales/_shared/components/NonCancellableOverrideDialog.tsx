'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { NonCancellableRefusal } from '../types/project.types';

/**
 * The lines a 409 `non_cancellable_line` refused, with the required Reason. Override retries
 * the same call with that reason; the server decides whether the caller may.
 */
export function NonCancellableOverrideDialog({
  refusal,
  submitting,
  onOverride,
  onCancel,
}: {
  refusal: NonCancellableRefusal;
  submitting: boolean;
  onOverride: (reason: string) => void | Promise<unknown>;
  onCancel: () => void;
}) {
  const [reason, setReason] = React.useState('');
  const trimmed = reason.trim();
  const canSubmit = trimmed.length >= 3 && !submitting;

  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Non-cancellable lines</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (canSubmit) await onOverride(trimmed);
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            <ul className="space-y-1 text-sm">
              {refusal.lines.map((line, index) => (
                <li key={`${line.label}-${index}`} className="flex justify-between gap-3">
                  <span className="min-w-0 truncate" title={line.label}>
                    {line.label}
                  </span>
                  <span className="shrink-0 tabular-nums">{`${line.from_qty} to ${line.to_qty}`}</span>
                </li>
              ))}
            </ul>
            <div className="space-y-1.5">
              <Label htmlFor="non-cancellable-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="non-cancellable-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              Override
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
