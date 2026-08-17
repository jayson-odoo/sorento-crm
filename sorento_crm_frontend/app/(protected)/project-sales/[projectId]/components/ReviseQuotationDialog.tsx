'use client';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useQuotationMutations } from '../../_shared/hooks/useProjects';
import type { ProjectQuotation } from '../../_shared/types/project.types';

/**
 * Confirms a revise, because it is one-way.
 *
 * Revising freezes the version on screen forever and opens a copy above it (AC-E3). It
 * is not a delete, so it does not use the delete dialog, but it is not undoable either,
 * so it does not happen on a single click. The copy carries the lines over, which is the
 * part worth stating: the user is not about to lose their pricing.
 */
export function ReviseQuotationDialog({
  projectId,
  quotation,
  currentVersionNo,
  lineCount,
  onDone,
}: {
  projectId: string;
  quotation: ProjectQuotation;
  currentVersionNo: number;
  lineCount: number;
  onDone: (newVersionId?: string) => void;
}) {
  const { revise } = useQuotationMutations(projectId);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{`Revise to v${currentVersionNo + 1}`}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {`v${currentVersionNo} of "${quotation.scope_label}" is frozen for good and `}
          {lineCount === 1 ? 'its 1 line is' : `all ${lineCount} of its lines are`}
          {` copied into v${currentVersionNo + 1}, which becomes the editable one. This cannot be undone.`}
        </DialogDescription>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={() => onDone()}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={revise.isPending}
            onClick={async () => {
              const version = await revise.mutateAsync(quotation.id);
              onDone(version.id);
            }}
          >
            {`Freeze v${currentVersionNo} and continue`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
