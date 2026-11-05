'use client';

import * as React from 'react';
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
  scopes: scopesOnOpen,
  onDone,
}: {
  projectId: string;
  scopes: ReviseScope[];
  onDone: (newVersionId?: string) => void;
}) {
  const { revise } = useQuotationMutations(projectId);
  /**
   * Areas already revised in THIS dialog. A retry after one area failed must not revise the
   * ones that already moved: that would freeze a second version nobody asked for, and a revise
   * cannot be undone.
   */
  const done = React.useRef(new Map<string, string>());
  // Worded from what the dialog was opened on: after a partial failure the refetched scopes
  // already count the areas that moved, and the wording must not promise them a second step.
  const [scopes] = React.useState(scopesOnOpen);
  const currentVersionNo = Math.max(0, ...scopes.map((scope) => scope.currentVersionNo));
  const lineCount = scopes.reduce((sum, scope) => sum + scope.lineCount, 0);
  const sameVersion = scopes.every((scope) => scope.currentVersionNo === currentVersionNo);
  const title = sameVersion ? `Revise to v${currentVersionNo + 1}` : 'Revise every area';

  let description: string;
  if (scopes.length === 1) {
    description =
      `v${currentVersionNo} of "${scopes[0].quotation.scope_label}" is frozen for good and ` +
      (lineCount === 1 ? 'its 1 line is' : `all ${lineCount} of its lines are`) +
      ` copied into v${currentVersionNo + 1}, which becomes the editable one. This cannot be undone.`;
  } else if (sameVersion) {
    description =
      `v${currentVersionNo} of all ${scopes.length} areas is frozen for good and all ${lineCount} ` +
      `of their lines are copied into v${currentVersionNo + 1}, which becomes the editable one. ` +
      'This cannot be undone.';
  } else {
    // Areas added later sit on a lower number; say what happens to each rather than one number
    // that is true of only some of them.
    description =
      'Each area is frozen for good and its lines are copied into its next version (' +
      scopes
        .map(
          (scope) =>
            `${scope.quotation.scope_label} v${scope.currentVersionNo} to v${scope.currentVersionNo + 1}`,
        )
        .join(', ') +
      '). This cannot be undone.';
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{description}</DialogDescription>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={() => onDone()}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={revise.isPending}
            onClick={async () => {
              try {
                for (const scope of scopes) {
                  if (done.current.has(scope.quotation.id)) continue;
                  const version = await revise.mutateAsync(scope.quotation.id);
                  done.current.set(scope.quotation.id, version.id);
                }
              } catch {
                // The mutation toasted the reason; the dialog stays open to try the rest again.
                return;
              }
              onDone([...done.current.values()].pop());
            }}
          >
            {sameVersion ? `Freeze v${currentVersionNo} and continue` : 'Freeze and continue'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
