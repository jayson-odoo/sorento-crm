'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useQuotationLossReasons,
  useQuotationMutations,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectQuotation,
  QuotationOutcome,
} from '../../_shared/types/project.types';

const OUTCOMES: { value: QuotationOutcome; label: string; hint: string }[] = [
  { value: 'won', label: 'Won', hint: 'The customer accepted this scope.' },
  { value: 'lost', label: 'Lost', hint: 'Somebody else got it, or it was dropped.' },
  { value: 'open', label: 'Still open', hint: 'No decision yet. Reopens the scope.' },
];

/**
 * Record the commercial result of ONE scope.
 *
 * Losing demands a reason, and the reasons come from a lookup set an admin owns rather
 * than free text, because the point of collecting them is to count them later. Winning
 * or reopening clears any reason the server already holds, so a scope that flips from
 * lost to won does not keep explaining a loss that no longer happened.
 *
 * This never touches the project's STATUS (AC-E10a). Status is where the project sits in
 * the funnel; outcome is what happened commercially. The project's own outcome is
 * re-derived server-side from all of its scopes.
 */
export function QuotationOutcomeDialog({
  project,
  quotation,
  onDone,
}: {
  project: Project;
  quotation: ProjectQuotation;
  onDone: () => void;
}) {
  const { decide } = useQuotationMutations(project.id);
  const reasons = useQuotationLossReasons();

  const [outcome, setOutcome] = React.useState<QuotationOutcome>(
    quotation.outcome === 'open' ? 'won' : quotation.outcome,
  );
  const [lossReason, setLossReason] = React.useState(quotation.loss_reason ?? '');

  const needsReason = outcome === 'lost';
  const blocked = needsReason && !lossReason;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>{`Outcome of "${quotation.scope_label}"`}</DialogTitle>
          <DialogDescription>
            Each scope is decided on its own. This project&apos;s overall outcome follows
            from all of them.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            await decide.mutateAsync({
              id: quotation.id,
              body: {
                outcome,
                loss_reason: outcome === 'lost' ? lossReason : null,
              },
            });
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-2">
              {OUTCOMES.map((option) => (
                <label
                  key={option.value}
                  className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                >
                  <input
                    type="radio"
                    name="quotation-outcome"
                    className="mt-0.5"
                    value={option.value}
                    checked={outcome === option.value}
                    onChange={() => setOutcome(option.value)}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{option.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {option.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            {needsReason && (
              <div className="space-y-1.5">
                <Label htmlFor="quotation-loss-reason">
                  Why we lost it <span className="text-destructive">*</span>
                </Label>
                <SearchableSelect
                  id="quotation-loss-reason"
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
            )}
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={blocked || decide.isPending}>
              Save outcome
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
