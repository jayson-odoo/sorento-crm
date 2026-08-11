'use client';

import { useEffect, useState } from 'react';

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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { FormUndoEligibility } from './formAction';

/**
 * Post-grace undo confirmation. Names every consequence in plain terms and requires a
 * reason - an undo without one is unexplainable a month later (AC-PG-5).
 *
 * The consequence list is built from what the server told us about the action rather
 * than hardcoded per form, so a new registered action gets correct copy for free.
 */
export function UndoActionDialog({
  open,
  onOpenChange,
  eligibility,
  entityLabel,
  onConfirm,
  isSubmitting = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  eligibility: FormUndoEligibility;
  /** Human reference for the form, e.g. "SF26-0326". */
  entityLabel: string;
  onConfirm: (reason: string) => void;
  isSubmitting?: boolean;
}) {
  const [reason, setReason] = useState('');
  const [touched, setTouched] = useState(false);

  // A stale reason must not survive into the next undo on the same page.
  useEffect(() => {
    if (!open) {
      setReason('');
      setTouched(false);
    }
  }, [open]);

  const trimmed = reason.trim();
  const invalid = touched && !trimmed;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="undo-action-dialog">
        {/* AlertDialogHeader defaults to `text-center sm:text-left` - centred copy on a
            phone and left-aligned on a desktop is the same dialog reading two different
            ways. Pin it left at every width. */}
        <AlertDialogHeader className="text-left">
          <AlertDialogTitle>Undo the last action on {entityLabel}?</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>This will:</p>
              <ul className="list-disc space-y-1 pl-5">
                <li>Reverse the last action taken on this form.</li>
                <li>Void the task it created for the next stage, and tell whoever held it.</li>
                <li>Return the form to the person who acted, and restart their SLA clock.</li>
                {eligibility.tells_contact ? (
                  <li>
                    Send the contact a correction - they were already told this form had
                    moved on, and that message cannot be unsent.
                  </li>
                ) : null}
              </ul>
              <p>This action cannot be undone.</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="undo-reason">
            Reason <span className="text-destructive">*</span>
          </Label>
          <Textarea
            id="undo-reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="Why is this being reversed?"
            aria-invalid={invalid || undefined}
            data-testid="undo-reason-input"
          />
          {invalid ? (
            <p className="text-xs text-destructive" data-testid="undo-reason-error">
              A reason is required.
            </p>
          ) : null}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isSubmitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            disabled={!trimmed || isSubmitting}
            onClick={(e) => {
              // Keep the dialog open on an invalid submit so the error is visible.
              e.preventDefault();
              setTouched(true);
              if (!trimmed) return;
              onConfirm(trimmed);
            }}
            data-testid="undo-confirm"
          >
            {isSubmitting ? 'Undoing…' : 'Undo'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default UndoActionDialog;
