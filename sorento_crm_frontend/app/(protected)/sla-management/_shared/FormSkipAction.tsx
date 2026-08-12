'use client';

import { useState } from 'react';
import { CircleCheckBig } from 'lucide-react';

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
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { UseFormSkipResult } from './useFormSkip';

/**
 * Skip-the-next-stage action (UAC-form-sla-skip-stage.md), rendered as a gear-dropdown
 * item plus a sibling confirm dialog.
 *
 * Config-driven on purpose: the item appears whenever the ACTIVE stage config declares a
 * `skip_event` and the viewer holds the entity's permission, with the label coming from
 * `skip_action_label`. A second entity type gets its action by inserting a config row and
 * registering a backend adapter - no new frontend code.
 *
 * The one thing config does NOT supply is `consequence` - the sentence telling the user
 * what taking this action actually means for the customer. That is domain truth, so the
 * calling page passes it. A config-authored string must never be the only thing standing
 * between a user and an irreversible outcome.
 *
 * Split into item + dialog for the same reason as SlaExtendAction: a dialog rendered
 * inside DropdownMenuContent unmounts the moment the menu closes.
 */

export function FormSkipMenuItem({
  skip,
  onSelect,
}: {
  skip: UseFormSkipResult;
  onSelect: () => void;
}) {
  if (!skip.canSkip || !skip.actionLabel) return null;
  return (
    <DropdownMenuItem
      data-testid="form-skip-menu-item"
      disabled={skip.isSubmitting}
      onSelect={(e) => {
        e.preventDefault();
        onSelect();
      }}
    >
      <CircleCheckBig className="size-4" />
      {skip.actionLabel}
    </DropdownMenuItem>
  );
}

export function FormSkipDialog({
  skip,
  open,
  onOpenChange,
  /** Domain sentence: what this means for the customer. Supplied by the page, not config. */
  consequence,
  /** Optional extra line, e.g. naming the stage that will be skipped. */
  detail,
}: {
  skip: UseFormSkipResult;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  consequence: string;
  detail?: string;
}) {
  const [note, setNote] = useState('');
  const label = skip.actionLabel ?? 'Confirm';

  // Reset the note whenever the dialog is re-opened so a cancelled draft never leaks
  // into the next attempt.
  const handleOpenChange = (next: boolean) => {
    if (next) setNote('');
    onOpenChange(next);
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent className="max-h-[90vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>{label}?</AlertDialogTitle>
          <AlertDialogDescription>
            {consequence}
            {detail ? ` ${detail}` : ''} A status update is sent to the contact. This
            action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-1">
          <Label htmlFor="form-skip-note">Message to contact (optional)</Label>
          <Textarea
            id="form-skip-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add an optional note for the customer…"
            rows={3}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={skip.isSubmitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={skip.isSubmitting}
            onClick={(e) => {
              // Keep the dialog mounted while the request is in flight; the caller
              // closes it from onSkipped so a failure leaves the note intact.
              e.preventDefault();
              skip.submit(note.trim() || undefined);
            }}
          >
            {skip.isSubmitting ? 'Saving…' : label}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
