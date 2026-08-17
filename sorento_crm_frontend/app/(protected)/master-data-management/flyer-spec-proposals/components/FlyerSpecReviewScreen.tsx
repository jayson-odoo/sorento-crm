'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  FileText,
  Loader2,
  ScanLine,
} from 'lucide-react';

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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { readable, readableValue } from '@/lib/spec-readable';

import {
  useApplyFlyerSpecProposals,
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
} from '../hooks/useFlyerSpecProposals';
import { proposalCountsSentence } from '../lib/countsSentence';
import type {
  FlyerSpecApplyResult,
  FlyerSpecProposal,
  FlyerSpecProposals,
} from '../services/flyerSpecProposalService';
import {
  OUTCOME_LABEL,
  OutcomePill,
  ProductProposalGroup,
} from './ProductProposalGroup';

/**
 * The batch, product by product, and the one control that writes it.
 *
 * Everything on this screen is shaped by one rule: a bulk apply must never be
 * able to overwrite something a person decided. So `new` rows arrive ticked -
 * the master says nothing, and gap-filling is the whole point of reading a
 * flyer - `change` rows arrive unticked, and `conflict` / `unchanged` /
 * `suppressed` cannot be ticked at all. The server re-checks every one of them
 * against the live spec row before it writes (AC-C.2), so this screen is a
 * convenience over that rule rather than the rule itself.
 *
 * There is no select-all across products. A flyer can name two hundred of them,
 * and a single tick that queues four hundred writes is a decision nobody made.
 *
 * The result is rendered in full - what was written AND what was not, each with
 * the sentence the server sent. Nobody chases a refusal they were never shown.
 */

/** The slug that authorises a write to the product master, everywhere. */
const MASTER_DATA_EDIT = 'master_data.products.edit';

/**
 * How many product cards render before the rest are asked for.
 *
 * The whole batch is already in the browser, so this is a rendering limit and
 * not a fetch: 200 products x 6 rows is 1200 table rows on one screen, which is
 * a page that takes seconds to paint and nothing anybody reads in one sitting.
 * Ticks survive the button, because the selection is held by id up here.
 */
const PRODUCTS_PER_PAGE = 25;

function pendingRows(batch: FlyerSpecProposals): FlyerSpecProposal[] {
  return batch.groups
    .flatMap((group) => group.proposals)
    .filter((row) => row.outcome === null);
}

export function FlyerSpecReviewScreen({ readingId }: { readingId: string }) {
  const canWriteMaster = useHasPermission(MASTER_DATA_EDIT);
  const { data, isLoading, isError, error } =
    useFlyerSpecProposalsQuery(readingId);
  const propose = useProposeFlyerSpecs(readingId);
  const apply = useApplyFlyerSpecProposals(readingId);

  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [shown, setShown] = useState(PRODUCTS_PER_PAGE);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<FlyerSpecApplyResult | null>(null);
  // Which batch the ticks below belong to. A re-propose replaces every row, so
  // ticks carried across it would name ids that no longer exist.
  const seededBatch = useRef<string | null>(null);

  useEffect(() => {
    if (!data || data.status !== 'proposed') return;
    const key = data.id ?? '';
    if (seededBatch.current === key) return;
    seededBatch.current = key;
    setShown(PRODUCTS_PER_PAGE);
    setResult(null);
    // Only `new`, and only what has not already been through an apply (AC-D.3):
    // the default is gap-filling, which is the one thing a flyer can do without
    // arguing with anybody.
    setSelected(
      new Set(
        pendingRows(data)
          .filter((row) => row.kind === 'new')
          .map((row) => row.id),
      ),
    );
  }, [data]);

  const rowsById = useMemo(() => {
    const index = new Map<string, FlyerSpecProposal>();
    for (const group of data?.groups ?? []) {
      for (const row of group.proposals) index.set(row.id, row);
    }
    return index;
  }, [data]);

  const selectedIds = useMemo(() => [...selected], [selected]);
  const changeCount = selectedIds.filter(
    (id) => rowsById.get(id)?.kind === 'change',
  ).length;

  const write = () => {
    setConfirming(false);
    apply.mutate(selectedIds, {
      onSuccess: (answer) => {
        setResult(answer);
        // The rows have moved: what applied is now what the master holds, and a
        // held tick would re-send it on the next click.
        setSelected(new Set());
      },
    });
  };

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="fsp-error">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not open these proposals</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          <span>
            {error instanceof Error
              ? error.message
              : 'Something went wrong. Try again.'}
          </span>
          <Button variant="outline" size="sm" asChild>
            <Link href="/master-data-management/flyer-spec-proposals">
              All flyer proposals
            </Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-4" data-testid="fsp-loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-5 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const proposeButton = canWriteMaster ? (
    <Button
      size="sm"
      disabled={propose.isPending || data.status === 'proposing'}
      onClick={() => propose.mutate()}
      data-testid="fsp-propose"
    >
      <ScanLine className="size-4" />
      {data.status === 'none'
        ? 'Propose specs from this flyer'
        : 'Propose again'}
    </Button>
  ) : null;

  const meta = [
    data.read_at ? `read ${formatDateTimeInMalaysia(data.read_at)}` : null,
    data.finished_at
      ? `proposed ${formatDateTimeInMalaysia(data.finished_at)}`
      : null,
    data.applied_at
      ? `applied ${formatDateTimeInMalaysia(data.applied_at)}${data.applied_by_name ? ` by ${data.applied_by_name}` : ''}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Button variant="ghost" size="sm" className="-ms-2 w-fit" asChild>
          <Link href="/master-data-management/flyer-spec-proposals">
            <ArrowLeft className="size-4" />
            All flyer proposals
          </Link>
        </Button>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-2">
            <FileText className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <h1
                className="min-w-0 break-words text-lg font-semibold"
                data-testid="fsp-filename"
              >
                {data.filename}
              </h1>
              {meta && <p className="text-sm text-muted-foreground">{meta}</p>}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href={`/dealer-kit/flyer-readings/${readingId}`}>
                Open the flyer reading
              </Link>
            </Button>
            {data.status !== 'none' && proposeButton}
          </div>
        </div>
      </div>

      {data.status === 'proposed' && data.proposal_count > 0 && (
        <p className="text-sm text-muted-foreground" data-testid="fsp-counts">
          {proposalCountsSentence(data)}
        </p>
      )}

      {data.status === 'none' && (
        <div
          className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center"
          data-testid="fsp-none"
        >
          <ScanLine className="size-6 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">
            This flyer has no spec proposals yet
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Reading it proposes values for the products it names. Nothing is
            written until you tick rows and apply them.
          </p>
          {proposeButton ?? (
            <p className="text-sm text-muted-foreground">
              Proposing needs the product master permission, which your role
              does not have.
            </p>
          )}
        </div>
      )}

      {data.status === 'proposing' && (
        <div
          className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center"
          data-testid="fsp-proposing"
        >
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">
            Reading this flyer
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            The proposals appear here when it is done.
          </p>
        </div>
      )}

      {data.status === 'failed' && (
        <Alert variant="destructive" data-testid="fsp-failed">
          <AlertCircle className="size-4" />
          <AlertTitle>
            The specifications could not be read from this flyer
          </AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>
              {data.error_message ||
                'The pass did not finish, and no reason was recorded.'}
            </span>
            {canWriteMaster && (
              <Button
                variant="outline"
                size="sm"
                disabled={propose.isPending}
                onClick={() => propose.mutate()}
                data-testid="fsp-retry"
              >
                Try again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {data.status === 'proposed' && data.groups.length === 0 && (
        <div
          className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center"
          data-testid="fsp-empty"
        >
          <CheckCircle2 className="size-6 text-green-600" />
          <p className="text-sm font-medium text-foreground">
            The flyer stated nothing the master does not already hold
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Nothing to review, and nothing to write.
          </p>
        </div>
      )}

      {data.status === 'proposed' && data.groups.length > 0 && (
        <>
          {!canWriteMaster && (
            <p
              className="rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground"
              data-testid="fsp-readonly"
            >
              Reported only. Writing a specification to the product master needs
              the product master permission, which your role does not have.
            </p>
          )}

          <div className="flex flex-col gap-4">
            {data.groups.slice(0, shown).map((group) => (
              <ProductProposalGroup
                key={group.product_id}
                group={group}
                selectedIds={selected}
                disabled={!canWriteMaster || apply.isPending}
                onSelectionChange={(idsForThisProduct) => {
                  const own = new Set(group.proposals.map((row) => row.id));
                  setSelected((previous) => {
                    const next = new Set(
                      [...previous].filter((id) => !own.has(id)),
                    );
                    for (const id of idsForThisProduct) next.add(id);
                    return next;
                  });
                }}
              />
            ))}
          </div>

          {data.groups.length > shown && (
            <Button
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={() => setShown((current) => current + PRODUCTS_PER_PAGE)}
              data-testid="fsp-show-more"
            >
              Show more products ({data.groups.length - shown} left)
            </Button>
          )}

          {result && <ApplyResult result={result} />}

          {canWriteMaster && (
            // Sticky, because the count of what is about to be written has to
            // stay in front of somebody scrolling forty product cards.
            <div className="sticky bottom-0 z-10 flex flex-col gap-2 border-t border-border bg-background/95 py-3 backdrop-blur sm:flex-row sm:items-center sm:justify-between">
              <p
                className="text-sm text-muted-foreground"
                data-testid="fsp-selection-count"
              >
                {selected.size === 0
                  ? 'Nothing ticked'
                  : `${selected.size} ticked${changeCount > 0 ? `, ${changeCount} replacing a value the master holds` : ''}`}
              </p>
              <Button
                size="sm"
                className="shrink-0"
                disabled={selected.size === 0 || apply.isPending}
                data-testid="fsp-apply"
                onClick={() => {
                  // Only a replacement needs confirming. A selection of gaps
                  // destroys nothing, and a dialog over it is a click that
                  // teaches people to click through dialogs.
                  if (changeCount > 0) setConfirming(true);
                  else write();
                }}
              >
                {apply.isPending
                  ? 'Writing to the master'
                  : `Apply ${selected.size} selected`}
              </Button>
            </div>
          )}
        </>
      )}

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle>
              Replace {changeCount} master value{changeCount === 1 ? '' : 's'}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {selected.size} row{selected.size === 1 ? '' : 's'} will be
              written as flyer values. {changeCount} of them replace what the
              product master holds today. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <ul
            className="flex flex-col gap-2 text-sm"
            data-testid="fsp-replacing"
          >
            {selectedIds
              .map((id) => rowsById.get(id))
              .filter((row): row is FlyerSpecProposal => row?.kind === 'change')
              .map((row) => (
                <li key={row.id} className="flex flex-col">
                  <span className="text-foreground">
                    {row.label || readable(row.spec_key)}
                  </span>
                  <span className="text-muted-foreground">
                    {readableValue(
                      row.stored_value,
                      row.stored_unit ?? undefined,
                    ) || 'Not recorded'}{' '}
                    becomes {readableValue(row.value, row.unit ?? undefined)}
                  </span>
                </li>
              ))}
          </ul>

          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={write}
              data-testid="fsp-confirm"
            >
              Replace and apply
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/**
 * What was written, and what was not.
 *
 * The refusals are the half that matters: a screen reporting "12 applied" over
 * three rows that silently did not land leaves three products wrong for as long
 * as it takes somebody to notice, which is usually never.
 */
function ApplyResult({ result }: { result: FlyerSpecApplyResult }) {
  const wrote = result.applied.length > 0;

  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-border px-3 py-3 text-sm"
      data-testid="fsp-result"
    >
      <p className="flex items-start gap-2 font-medium text-foreground">
        {wrote ? (
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-600" />
        ) : (
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-600" />
        )}
        {wrote
          ? `${result.applied.length} specification value${result.applied.length === 1 ? '' : 's'} written to the product master`
          : 'Nothing was written to the product master'}
      </p>

      {result.applied.length > 0 && (
        <ul className="flex flex-col gap-1 text-muted-foreground">
          {result.applied.map((entry) => (
            <li key={entry.proposal_id} className="min-w-0 break-words">
              <span className="font-mono text-foreground">
                {entry.product_code}
              </span>{' '}
              {readable(entry.spec_key)} {readableValue(entry.value)}
            </li>
          ))}
        </ul>
      )}

      {result.refused.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="font-medium text-foreground">
            {result.refused.length} not written
          </p>
          <ul className="flex flex-col gap-1.5 text-muted-foreground">
            {result.refused.map((entry) => (
              <li
                key={entry.proposal_id}
                className="flex flex-wrap items-center gap-2"
              >
                <span className="font-mono text-foreground">
                  {entry.product_code || '-'}
                </span>
                <span>{entry.spec_key ? readable(entry.spec_key) : ''}</span>
                <OutcomePill outcome={entry.reason} />
                <span className="min-w-0 break-words">
                  {entry.message || OUTCOME_LABEL[entry.reason]}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
