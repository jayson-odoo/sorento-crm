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
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { ProjectSalesOrderFinding } from '../../_shared/types/projectSalesOrder.types';

/**
 * Records the reason a finding was cleared. The reason is mandatory, it carries the
 * acknowledger's name, and it stays on the sales order for good, so an empty one is refused
 * here as well as by the server. Clearing a hard stop takes a second, explicit confirmation.
 */
export function SalesOrderAcknowledgeDialog({
  finding,
  onDone,
  onConfirm,
  submitting,
}: {
  finding: ProjectSalesOrderFinding;
  onDone: () => void;
  onConfirm: (reason: string) => Promise<unknown>;
  submitting: boolean;
}) {
  const [reason, setReason] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);
  const trimmed = reason.trim();
  const isHard = finding.severity === 'hard';

  const submit = async () => {
    if (!trimmed) return;
    await onConfirm(trimmed);
    onDone();
  };

  if (confirming) {
    return (
      <AlertDialog open onOpenChange={(next) => !next && setConfirming(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Publish past a hard stop?</AlertDialogTitle>
            <AlertDialogDescription>
              {`${finding.detail} Your name and this reason stay on the sales order: "${trimmed}"`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={submitting || !trimmed}
              onClick={async (event) => {
                event.preventDefault();
                await submit();
              }}
            >
              {submitting ? 'Recording…' : 'Override and record'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isHard ? 'Override a hard stop' : 'Clear a warning'}</DialogTitle>
          <DialogDescription>{finding.detail}</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!trimmed) return;
            if (isHard) {
              setConfirming(true);
              return;
            }
            await submit();
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="acknowledge-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="acknowledge-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                placeholder="In your own words"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || submitting}>
              {isHard ? 'Override' : 'Record the reason'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
