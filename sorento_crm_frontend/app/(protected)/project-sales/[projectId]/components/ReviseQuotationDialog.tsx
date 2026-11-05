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
export type ReviseScope = {
  quotation: ProjectQuotation;
  currentVersionNo: number;
  lineCount: number;
};

/**
 * One scope (the per-scope page) or every area of a proposal at once (the proposal page's gear,
 * PROPOSAL-HEADER-LAYOUT: "version is per quotation / proposal"). Several areas are revised one
 * after another, never in parallel: each revise freezes its scope's current version, and one
 * failing must not leave the rest half-done behind a spinner.
 */
export function ReviseQuotationDialog({
  projectId,
  scopes,
  onDone,
}: {
  projectId: string;
  scopes: ReviseScope[];
  onDone: (newVersionId?: string) => void;
}) {
  const { revise } = useQuotationMutations(projectId);
  const currentVersionNo = Math.max(0, ...scopes.map((scope) => scope.currentVersionNo));
  const lineCount = scopes.reduce((sum, scope) => sum + scope.lineCount, 0);
  const subject =
    scopes.length === 1 ? `"${scopes[0].quotation.scope_label}"` : `all ${scopes.length} areas`;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{`Revise to v${currentVersionNo + 1}`}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {`v${currentVersionNo} of ${subject} is frozen for good and `}
          {scopes.length > 1
            ? `all ${lineCount} of their lines are`
            : lineCount === 1
              ? 'its 1 line is'
              : `all ${lineCount} of its lines are`}
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
              let last: string | undefined;
              try {
                for (const scope of scopes) {
                  last = (await revise.mutateAsync(scope.quotation.id)).id;
                }
              } catch {
                // The mutation toasted the reason; the dialog stays open to try again.
                return;
              }
              onDone(last);
            }}
          >
            {`Freeze v${currentVersionNo} and continue`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
