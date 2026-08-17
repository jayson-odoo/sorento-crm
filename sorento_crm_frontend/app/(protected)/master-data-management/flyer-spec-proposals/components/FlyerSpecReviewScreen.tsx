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
  Search,
  X,
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
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission, usePermissions } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { readable, readableValue } from '@/lib/spec-readable';

import {
  useAddFlyerSpecProposalRow,
  useApplyFlyerSpecProposals,
  useDismissFlyerSpecProposal,
  useEditFlyerSpecProposal,
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
  BULK_SELECTABLE_KINDS,
  OUTCOME_LABEL,
  OutcomePill,
  ProductProposalGroup,
} from './ProductProposalGroup';

/**
 * The batch, product by product, and the one control that writes it.
 *
 * `new` rows arrive ticked - the master says nothing, and gap-filling is the
 * whole point of reading a flyer. `change` AND `conflict` rows arrive unticked
 * but tickable (AC-F.4): ticking a conflict, plus a dialog that names how many
 * values a person set are about to be replaced, IS the confirmation. `unchanged`
 * and `suppressed` cannot be ticked at all - there is nothing to write for the
 * first and a removal to overturn in the second. The server re-checks every one
 * of them against the live spec row before it writes (AC-C.2), so this screen is
 * a convenience over that rule rather than the rule itself.
 *
 * It is also where the whole act happens: a value is corrected in place, a key
 * the flyer stated in a way no rule caught is added, and a row belonging to the
 * neighbouring card is dismissed, without visiting a single product page.
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
  // `useHasPermission` answers false while the permissions are still being
  // fetched, and "not yet known" must not read as "denied": the refusal copy
  // is for a role that has been looked up and found wanting.
  const { isLoading: permissionsLoading } = usePermissions();
  // The route wants the product-master permission as well as the dealer-kit
  // slug, so without it the request can only come back 403: not fired, and the
  // screen says why instead of showing the error the server would have sent.
  const { data, isLoading, isError, error } = useFlyerSpecProposalsQuery(
    readingId,
    { enabled: canWriteMaster },
  );
  const propose = useProposeFlyerSpecs(readingId);
  const apply = useApplyFlyerSpecProposals(readingId);
  const editValue = useEditFlyerSpecProposal(readingId);
  const addRow = useAddFlyerSpecProposalRow(readingId);
  const dismiss = useDismissFlyerSpecProposal(readingId);

  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [shown, setShown] = useState(PRODUCTS_PER_PAGE);
  const [confirming, setConfirming] = useState(false);
  const [search, setSearch] = useState('');
  const [result, setResult] = useState<FlyerSpecApplyResult | null>(null);
  // Which PASS the ticks below belong to, which is not the same thing as which
  // batch. A reading has exactly one batch row (`flyer_reading_id` is unique and
  // `start_batch` wipes it in place), so a re-propose keeps the id and replaces
  // every proposal under it: keyed on the id alone this would never re-seed, and
  // the ticks would go on naming rows the re-propose deleted - a table with
  // nothing ticked over a bar offering to apply forty of them, every one of which
  // comes back `not_in_batch`. The settle stamp is what moves per pass.
  const seededPass = useRef<string | null>(null);

  useEffect(() => {
    if (!data || data.status !== 'proposed') return;
    const key = `${data.id ?? ''}:${data.finished_at ?? data.created_at ?? ''}`;
    if (seededPass.current === key) return;
    seededPass.current = key;
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

  // A tick outlives the row it was put on. An in-place edit that turns a
  // `change` into `unchanged`, a dismissal, an apply from another tab: each of
  // them leaves the batch holding a row that is no longer tickable, or no row
  // at all, under an id the selection still names. Left alone, the sticky bar
  // counts it, Apply sends it and the server refuses it, and the box renders
  // checked-and-disabled with nothing on it that unticks. So the selection is
  // brought back to what the batch as it stands would let anybody tick.
  useEffect(() => {
    setSelected((previous) => {
      const next = new Set(
        [...previous].filter((id) => {
          const row = rowsById.get(id);
          return (
            row !== undefined &&
            row.outcome === null &&
            BULK_SELECTABLE_KINDS.includes(row.kind)
          );
        }),
      );
      return next.size === previous.size ? previous : next;
    });
  }, [rowsById]);

  const groupCount = data?.groups.length ?? 0;
  // The search box only renders over more than one product. A filter typed
  // while there were several, still applied once dismissals leave one, would
  // hide that one behind a "nothing matches" line with no box to clear.
  useEffect(() => {
    if (groupCount <= 1) setSearch('');
  }, [groupCount]);

  const selectedIds = useMemo(() => [...selected], [selected]);
  const replacing = selectedIds
    .map((id) => rowsById.get(id))
    .filter(
      (row): row is FlyerSpecProposal =>
        row?.kind === 'change' || row?.kind === 'conflict',
    );
  // Every ticked row that overwrites something, and the subset of those that
  // overwrite a PERSON. Two numbers because they are two different sizes of
  // decision, and a dialog that named only the total would hide the one that
  // matters (AC-F.4).
  const replaceCount = replacing.length;
  const authoredCount = replacing.filter((row) => row.kind === 'conflict').length;

  /**
   * The groups the search box leaves on screen.
   *
   * Product code, product name and specification label, because those are the
   * three things a reviewer holding the paper knows about the row they are
   * looking for. Client-side: the whole batch is already here, and a round trip
   * per keystroke would be slower than the filter it replaces.
   *
   * **The selection is untouched by it.** Hiding a row is not unticking it - a
   * reviewer who ticks forty rows, searches for the one they want to check and
   * then presses Apply must write the forty, not the one (AC-G.5).
   */
  const visibleGroups = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return data?.groups ?? [];
    return (data?.groups ?? []).filter((group) => {
      if (
        group.product_code.toLowerCase().includes(query) ||
        group.product_name.toLowerCase().includes(query)
      ) {
        return true;
      }
      return group.proposals.some(
        (row) =>
          (row.label || '').toLowerCase().includes(query) ||
          row.spec_key.toLowerCase().includes(query),
      );
    });
  }, [data?.groups, search]);

  /**
   * Narrowing the list starts its paging again from the top.
   *
   * `shown` is a depth into whatever list is on screen, and the filtered list
   * and the whole one are different lengths - so a depth reached inside a
   * filter, carried back out of it, either paints every product in the batch at
   * once or leaves the restored list capped at a number nobody chose with no
   * `Show more` to ask for the rest. The second is what the F+G evidence run
   * caught (plan section 6b, step 8): groups became unreachable without
   * reloading the page. The ticks are untouched either way - they are held by
   * id, not by position.
   */
  const changeSearch = (next: string) => {
    setSearch(next);
    setShown(PRODUCTS_PER_PAGE);
  };

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

  if (permissionsLoading) {
    return (
      <div className="flex flex-col gap-4" data-testid="fsp-loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-5 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!canWriteMaster) {
    return (
      <div className="flex flex-col gap-4">
        <Button variant="ghost" size="sm" className="-ms-2 w-fit" asChild>
          <Link href="/master-data-management/flyer-spec-proposals">
            <ArrowLeft className="size-4" />
            All flyer proposals
          </Link>
        </Button>
        <div
          className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center"
          data-testid="fsp-readonly"
        >
          <ScanLine className="size-6 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">
            Reported only
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Reviewing what a flyer states needs the product master permission,
            which your role does not have.
          </p>
        </div>
      </div>
    );
  }

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
          {proposeButton}
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
          {data.groups.length > 1 && (
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute inset-y-0 start-3 my-auto size-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => changeSearch(event.target.value)}
                placeholder="Search product or specification"
                aria-label="Search product or specification"
                className="ps-9 pe-9"
                data-testid="fsp-search"
              />
              {search !== '' && (
                // One deterministic way back to the whole batch. Emptying the
                // box by hand does the same thing, but a filter that hid the
                // product somebody wants next is a dead end until it is empty,
                // and asking them to select-and-delete is asking them to work
                // out why the list is short.
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute inset-y-0 end-1 my-auto size-7"
                  aria-label="Clear the search"
                  data-testid="fsp-search-clear"
                  onClick={() => changeSearch('')}
                >
                  <X className="size-4" />
                </Button>
              )}
            </div>
          )}

          <div className="flex flex-col gap-4">
            {visibleGroups.slice(0, shown).map((group) => (
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
                onEditValue={
                  canWriteMaster
                    ? (proposalId, value) =>
                        editValue.mutateAsync({ proposalId, value })
                    : undefined
                }
                onDismiss={
                  canWriteMaster
                    ? async (proposalId) => {
                        const summary = await dismiss.mutateAsync(proposalId);
                        // The row is gone from the batch, so a tick naming it
                        // is a tick on nothing: the sticky bar would count it,
                        // and the apply would send an id the server answers
                        // `not_in_batch` for. Pruned only once the delete has
                        // actually happened - a refused dismissal leaves the
                        // row, and its tick, where they were.
                        setSelected((previous) => {
                          if (!previous.has(proposalId)) return previous;
                          const next = new Set(previous);
                          next.delete(proposalId);
                          return next;
                        });
                        return summary;
                      }
                    : undefined
                }
                onAddRow={
                  canWriteMaster
                    ? async (input) => {
                        const row = await addRow.mutateAsync({
                          product_id: group.product_id,
                          ...input,
                        });
                        // Somebody typed this row a second ago, which is a
                        // stronger statement of intent than anything the flyer
                        // said - so it arrives ticked, the way a `new` row the
                        // page loaded with does. The load-time seeding pass
                        // does not run again for this batch, so without this
                        // the row they just added is the one row Apply leaves
                        // out. Unless the value they typed is what the product
                        // already holds, which is not tickable at all.
                        if (BULK_SELECTABLE_KINDS.includes(row.kind)) {
                          setSelected((previous) =>
                            new Set(previous).add(row.id),
                          );
                        }
                        return row;
                      }
                    : undefined
                }
              />
            ))}
          </div>

          {visibleGroups.length === 0 && (
            <p
              className="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground"
              data-testid="fsp-search-empty"
            >
              No product or specification here matches &ldquo;{search}&rdquo;.
              Ticked rows are still ticked.
            </p>
          )}

          {visibleGroups.length > shown && (
            <Button
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={() => setShown((current) => current + PRODUCTS_PER_PAGE)}
              data-testid="fsp-show-more"
            >
              Show more products ({visibleGroups.length - shown} left)
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
                  : `${selected.size} ticked${replaceCount > 0 ? `, ${replaceCount} replacing a value the master holds` : ''}`}
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
                  if (replaceCount > 0) setConfirming(true);
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
              Replace {replaceCount} master value
              {replaceCount === 1 ? '' : 's'}
              {authoredCount > 0
                ? `, ${authoredCount} of them set by a person?`
                : '?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {selected.size} row{selected.size === 1 ? '' : 's'} will be
              written. {replaceCount} of them replace what the product master
              holds today
              {authoredCount > 0
                ? `, and ${authoredCount} replace a value somebody set by hand`
                : ''}
              . This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <ul
            className="flex flex-col gap-2 text-sm"
            data-testid="fsp-replacing"
          >
            {replacing.map((row) => (
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
