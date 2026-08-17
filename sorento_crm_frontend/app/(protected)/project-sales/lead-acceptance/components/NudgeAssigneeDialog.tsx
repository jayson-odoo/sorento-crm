'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

/**
 * Ask again.
 *
 * The consequence is stated rather than explained: the notification goes out a second
 * time and the wait starts over, which is the one thing a person needs to know before
 * pressing it.
 */
export function NudgeAssigneeDialog({
  leadCode,
  assigneeName,
  submitting,
  onDone,
  onConfirm,
}: {
  leadCode: string;
  assigneeName?: string | null;
  submitting?: boolean;
  onDone: () => void;
  onConfirm: (note: string | null) => Promise<void>;
}) {
  const [note, setNote] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const pending = busy || Boolean(submitting);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Nudge {assigneeName ?? 'the assignee'}</DialogTitle>
          <DialogDescription>
            {leadCode} is notified again and the waiting time restarts.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            try {
              await onConfirm(note.trim() || null);
              onDone();
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            {/* Same as assign: it rides the notification and is not kept on the lead. */}
            <div className="space-y-1.5">
              <Label htmlFor="nudge-note">Message to them</Label>
              <Textarea
                id="nudge-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                placeholder="e.g. Tender closes Friday"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              Nudge
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
