'use client';

import { useState } from 'react';
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

/**
 * Destructive confirm dialog for VOIDING a form (R3). Voiding permanently makes
 * the record read-only, so it follows the AlertDialog destructive-confirm
 * convention (red action button, "cannot be undone" copy) — the same family as
 * the reject / delete dialogs.
 *
 * A void REASON is required (min 3 chars) with inline validation: the error text
 * appears once the field has been touched or a submit is attempted.
 *
 * `onConfirm(reason)` performs the mutation (a promise). On resolve the dialog
 * resets + closes; on reject it stays open (the error toast is surfaced upstream
 * by the mutation hook).
 */
const MIN_REASON = 3;

export interface VoidDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => Promise<unknown> | void;
  /** External pending flag (e.g. mutation.isPending) — disables the controls. */
  isPending?: boolean;
  title?: string;
  description?: React.ReactNode;
}

export function VoidDialog({
  open,
  onOpenChange,
  onConfirm,
  isPending = false,
  title = 'Void this form?',
  description,
}: VoidDialogProps) {
  const [reason, setReason] = useState('');
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const trimmed = reason.trim();
  const tooShort = trimmed.length < MIN_REASON;
  const showError = touched && tooShort;
  const busy = submitting || isPending;

  const reset = () => {
    setReason('');
    setTouched(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (busy) return; // don't allow closing mid-flight
    if (!next) reset();
    onOpenChange(next);
  };

  const handleConfirm = async (e: React.MouseEvent) => {
    e.preventDefault(); // Radix auto-closes AlertDialogAction; keep open until done
    setTouched(true);
    if (tooShort) return;
    setSubmitting(true);
    try {
      await onConfirm(trimmed);
      reset();
      onOpenChange(false);
    } catch {
      // Error already toasted by the mutation hook — keep the dialog open.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>
            {description ??
              'Voiding makes this form permanently read-only. This action cannot be undone.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="void-reason">
            Reason <span className="text-destructive">*</span>
          </Label>
          <Textarea
            id="void-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="Why is this form being voided?"
            rows={4}
            disabled={busy}
            aria-invalid={showError || undefined}
            aria-describedby={showError ? 'void-reason-error' : undefined}
          />
          {showError ? (
            <p id="void-reason-error" className="text-xs text-destructive">
              A reason of at least {MIN_REASON} characters is required.
            </p>
          ) : null}
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy || tooShort}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={handleConfirm}
          >
            {busy ? 'Voiding…' : 'Void form'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
