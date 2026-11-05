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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useChangeProjectStatus, useQuotationLossReasons } from '../../_shared/hooks/useProjects';

/**
 * Mark lost: the stage move to Lost, with the reason the loss-reasons report counts.
 * Nothing moves until Save, so the project page and a drop on the board's Lost column
 * both mount this with the same three props and Cancel leaves the project where it was.
 */
export function ProjectLossDialog({
  projectId,
  toStatusId,
  onDone,
}: {
  projectId: string;
  toStatusId: string;
  onDone: () => void;
}) {
  const move = useChangeProjectStatus();
  const reasons = useQuotationLossReasons();
  const [lossReason, setLossReason] = React.useState('');

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Mark lost</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            move.mutate(
              { projectId, toStatusId, lossReason },
              { onSuccess: onDone },
            );
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="project-loss-reason">
                Why we lost it <span className="text-destructive">*</span>
              </Label>
              <SearchableSelect
                id="project-loss-reason"
                value={lossReason}
                onChange={setLossReason}
                options={(reasons.data ?? []).map((reason) => ({
                  value: reason.value,
                  label: reason.label,
                }))}
                placeholder="Select a reason"
                emptyMessage="No loss reasons configured"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!lossReason || move.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
