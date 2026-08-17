'use client';

import * as React from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle2, ClipboardList, ShieldAlert } from 'lucide-react';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useReconciliationMutations, useSupply } from '../../_shared/hooks/useFulfilmentPlanning';
import { ConfirmSupplyError } from '../../_shared/services/fulfilmentPlanningService';
import type { SupplyFailingLine } from '../../_shared/types/fulfilmentPlanning.types';
import {
  confirmLineFromDraft,
  draftBlockers,
  draftFromLine,
  type DraftLine,
} from '../../_shared/lib/supplyComposition';
import { ConfirmProjectSoDialog } from './ConfirmProjectSoDialog';
import { SupplyLineCard } from './SupplyLineCard';

/**
 * Supply composition: what will meet each line, and the one press that commits all of them
 * (journey steps 1 to 3).
 *
 * The whole sales order is the unit. There is no per-line confirm, no draft that survives
 * the sheet, and no partial state to come back to: a line that does not balance, a borrow
 * without a reason or a discontinued buy without one blocks the single Confirm for the
 * order, and says which line it is.
 *
 * A refused confirmation writes nothing. Its failing lines are shown here, by line number
 * and item code, so the next attempt starts from the line that refused rather than from a
 * toast that has already gone.
 */
export function SupplyCompositionSection({
  psoId,
  reference,
  open,
}: {
  psoId: string;
  /** What the sales order is called on screen: the AutoCount number, or our own. */
  reference: string;
  open: boolean;
}) {
  const supply = useSupply(psoId, open);
  const { confirm } = useReconciliationMutations();

  const proposal = supply.data;
  const decision = proposal?.decision;
  const isConfirmed = proposal?.review_state === 'confirmed' && decision?.state === 'active';

  const [drafts, setDrafts] = React.useState<DraftLine[]>([]);
  const [composingAgain, setComposingAgain] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [failingLines, setFailingLines] = React.useState<SupplyFailingLine[]>([]);

  // Re-seed whenever the proposal itself changes: it is the server's reading of live
  // stock, and keeping a draft on top of an older one would compose against facts that
  // have moved.
  React.useEffect(() => {
    setDrafts((proposal?.lines ?? []).map(draftFromLine));
    setComposingAgain(false);
    setFailingLines([]);
  }, [proposal]);

  const frozen = isConfirmed && !composingAgain;
  const blockers = React.useMemo(() => (frozen ? [] : draftBlockers(drafts)), [frozen, drafts]);
  const lines = proposal?.lines ?? [];

  async function submit() {
    setFailingLines([]);
    try {
      await confirm.mutateAsync({
        psoId,
        body: { lines: drafts.map(confirmLineFromDraft) },
      });
      setConfirming(false);
      setComposingAgain(false);
    } catch (error) {
      setConfirming(false);
      if (error instanceof ConfirmSupplyError) setFailingLines(error.failingLines);
    }
  }

  if (supply.isError) {
    return (
      <section aria-label="Supply composition" className="space-y-3">
        <SectionTitle />
        <Alert variant="destructive" appearance="light">
          <AlertIcon>
            <AlertTriangle />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>The supply composition could not be loaded</AlertTitle>
            <AlertDescription>
              {supply.error instanceof Error
                ? supply.error.message
                : 'Try again in a moment.'}
              <div className="mt-3">
                <Button type="button" size="sm" variant="outline" onClick={() => supply.refetch()}>
                  Try again
                </Button>
              </div>
            </AlertDescription>
          </AlertContent>
        </Alert>
      </section>
    );
  }

  if (supply.isLoading) {
    return (
      <section aria-label="Supply composition" className="space-y-3">
        <SectionTitle />
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }

  return (
    <section aria-label="Supply composition" className="space-y-3">
      <SectionTitle />

      {decision?.state === 'challenged' && (
        <Alert variant="warning" appearance="light">
          <AlertIcon>
            <ShieldAlert />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>{`Revision ${decision.revision_no} no longer matches this sales order`}</AlertTitle>
            <AlertDescription>
              {decision.challenged_reason ||
                'A fact this revision was built on has changed since it was decided.'}
            </AlertDescription>
          </AlertContent>
        </Alert>
      )}

      {decision?.state === 'superseded' && (
        <Alert appearance="light">
          <AlertIcon>
            <ShieldAlert />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>{`Revision ${decision.revision_no} was superseded`}</AlertTitle>
            <AlertDescription>Compose this sales order again to replace it.</AlertDescription>
          </AlertContent>
        </Alert>
      )}

      {isConfirmed && decision && (
        <div className="rounded-lg border border-border px-3 py-2.5">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 text-sm">
              <span className="font-medium">{`Revision ${decision.revision_no}`}</span>
              <span className="text-muted-foreground">
                {decision.confirmed_by_name ? ` by ${decision.confirmed_by_name}` : ''}
                {decision.confirmed_at
                  ? ` on ${formatDateInMalaysia(decision.confirmed_at)}`
                  : ''}
              </span>
            </div>
            {proposal?.project_id && (
              <Button asChild variant="outline" size="sm">
                <Link href={`/project-sales/${proposal.project_id}/order-inquiries`}>
                  <ClipboardList className="size-4" aria-hidden />
                  Open the order inquiry
                </Link>
              </Button>
            )}
          </div>
        </div>
      )}

      {failingLines.length > 0 && (
        <Alert variant="destructive" appearance="light">
          <AlertIcon>
            <AlertTriangle />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>Nothing was written</AlertTitle>
            <AlertDescription asChild>
              <ul className="space-y-1">
                {failingLines.map((failing, index) => (
                  <li key={`${failing.line_no ?? ''}-${failing.item_code ?? ''}-${index}`}>
                    <span className="font-medium">{`${failingSubject(failing)}: `}</span>
                    {failing.reason}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </AlertContent>
        </Alert>
      )}

      {lines.length === 0 ? (
        <div className="rounded-lg border border-border px-3 py-8 text-center">
          <h3 className="text-sm font-semibold">There is nothing to compose</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            This sales order carries no line with an open quantity.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {lines.map((line, index) => {
            const draft = drafts[index];
            if (!draft) return null;
            return (
              <SupplyLineCard
                key={line.project_line_id}
                line={line}
                draft={draft}
                frozen={frozen}
                onChange={(next) =>
                  setDrafts((current) =>
                    current.map((entry, position) => (position === index ? next : entry)),
                  )
                }
              />
            );
          })}
        </div>
      )}

      {lines.length > 0 && (
        <div className="space-y-2 rounded-lg border border-border px-3 py-2.5">
          {frozen ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-hidden />
                {`All ${lines.length} line${lines.length === 1 ? '' : 's'} are held by revision ${
                  decision?.revision_no ?? 1
                }.`}
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setComposingAgain(true)}
              >
                Compose again
              </Button>
            </>
          ) : (
            <>
              {blockers.length > 0 && (
                <ul className="space-y-0.5">
                  {blockers.map((blocker) => (
                    <li key={blocker} className="text-sm text-destructive break-words">
                      {blocker}
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  disabled={blockers.length > 0 || confirm.isPending}
                  onClick={() => setConfirming(true)}
                >
                  Confirm Project SO
                </Button>
                {composingAgain && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setDrafts((proposal?.lines ?? []).map(draftFromLine));
                      setComposingAgain(false);
                    }}
                  >
                    Keep revision {decision?.revision_no}
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {confirming && (
        <ConfirmProjectSoDialog
          reference={reference}
          lineCount={lines.length}
          currentRevision={isConfirmed ? (decision?.revision_no ?? null) : null}
          submitting={confirm.isPending}
          onDone={() => setConfirming(false)}
          onConfirm={() => void submit()}
        />
      )}
    </section>
  );
}

/**
 * How a refused line is named. A refusal about the whole sales order carries no line
 * number, so it says so rather than printing "Line undefined".
 */
function failingSubject(failing: SupplyFailingLine): string {
  if (failing.line_no != null) {
    return `Line ${failing.line_no}${failing.item_code ? `, ${failing.item_code}` : ''}`;
  }
  return failing.item_code || 'This sales order';
}

function SectionTitle() {
  return (
    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      Supply composition
    </div>
  );
}
