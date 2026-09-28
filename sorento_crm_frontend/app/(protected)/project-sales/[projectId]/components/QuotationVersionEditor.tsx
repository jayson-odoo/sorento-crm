'use client';

import * as React from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useQuotationLines,
  useQuotationRecomputeMutation,
  useQuotationVersions,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectQuotation,
  QuotationRecomputeResult,
} from '../../_shared/types/project.types';
import { lineToFormLine } from '../../_shared/lib/quotationLineDraft';
import { QuotationLinesGrid } from './QuotationLinesGrid';
import { ReviseQuotationDialog } from './ReviseQuotationDialog';

/**
 * The versions of one scope, and the lines of whichever version is being looked at.
 *
 * A READ, always (#1341). Editing a scope - its name, its series and its lines - happens only in
 * the quotation form page, opened from Edit quotation in the gear: the owner's words, "Edit
 * quotation means I edit the whole quotation". So there is nothing here to type into, and the
 * lines are the system DataGrid, the same component the Quotations list uses.
 *
 * Only the newest version can change, and the server says which (`is_editable`), never a local
 * guess. Everything below it is history the customer already holds (AC-E3), so an older version
 * states that it is frozen.
 */
export function QuotationVersionEditor({
  project,
  quotation,
}: {
  project: Project;
  quotation: ProjectQuotation;
}) {
  const versions = useQuotationVersions(quotation.id);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [revising, setRevising] = React.useState(false);
  const recompute = useQuotationRecomputeMutation(project.id);
  const [recomputed, setRecomputed] = React.useState<QuotationRecomputeResult | null>(null);

  const rows = React.useMemo(
    () => [...(versions.data ?? [])].sort((a, b) => b.version_no - a.version_no),
    [versions.data],
  );
  const current = rows.find((version) => version.is_current) ?? null;
  const selected = rows.find((version) => version.id === selectedId) ?? current;

  const lines = useQuotationLines(selected?.id);
  const editable = Boolean(selected?.is_editable ?? selected?.is_current) && project.can_edit;
  const formLines = React.useMemo(
    () => [...(lines.data ?? [])].sort((a, b) => a.sort_order - b.sort_order).map(lineToFormLine),
    [lines.data],
  );

  if (versions.isLoading) return <Skeleton className="h-24 w-full" />;

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {rows.map((version) => (
            <button
              key={version.id}
              type="button"
              onClick={() => setSelectedId(version.id)}
              aria-current={selected?.id === version.id}
              className={
                selected?.id === version.id
                  ? 'rounded-md border border-primary bg-primary/10 px-2.5 py-1 text-xs font-medium'
                  : 'rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted'
              }
            >
              {`v${version.version_no}`}
              {version.is_current ? '' : ' (frozen)'}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Re-ask both alerts against today's master data (S19), on the version being looked
              at and only while it is still open: the flags on a frozen version are what was true
              when the customer was sent the paper. */}
          {project.can_edit && editable && selected && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={recompute.isPending}
              title="Re-check every line against the series and price floors as they stand today"
              onClick={async () => {
                try {
                  setRecomputed(await recompute.mutateAsync(selected.id));
                } catch {
                  // The mutation already toasted the reason.
                }
              }}
            >
              <RefreshCw className="size-4" aria-hidden />
              {recompute.isPending ? 'Rechecking...' : 'Recheck alerts'}
            </Button>
          )}

          {project.can_edit && current && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setRevising(true)}
            >
              {`Revise to v${current.version_no + 1}`}
            </Button>
          )}
        </div>
      </div>

      {recomputed && (
        <RecomputeSummary result={recomputed} onDismiss={() => setRecomputed(null)} />
      )}

      {/* No "Issued by / Opened" strip above the table: the owner moved it into the Header tab's
          details ("this one should be in header details", #1341). */}
      {selected?.is_issued && selected.is_current && (
        <p className="text-xs text-muted-foreground">
          {`The customer holds v${selected.version_no}. Edit quotation opens v${selected.version_no + 1} and leaves what was sent untouched.`}
        </p>
      )}

      {selected && !selected.is_current && (
        <p className="text-xs text-muted-foreground">
          {`Frozen. Make changes on ${current ? `v${current.version_no}` : 'the current version'}.`}
        </p>
      )}

      {lines.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <QuotationLinesGrid
          // A fresh grid per version, so a search typed on v2 does not follow the reader to v1.
          key={selected?.id ?? 'none'}
          lines={formLines}
          quotationId={quotation.id}
          seriesId={quotation.series_id ?? null}
        />
      )}

      {revising && current && (
        <ReviseQuotationDialog
          projectId={project.id}
          quotation={quotation}
          currentVersionNo={current.version_no}
          lineCount={formLines.length}
          onDone={(newVersionId) => {
            setRevising(false);
            // Land on the version that was just opened, not the one being read a moment ago.
            if (newVersionId) setSelectedId(newVersionId);
          }}
        />
      )}
    </div>
  );
}

/**
 * What a recompute changed, in the words a reader would use (S19).
 *
 * Composed here rather than on the server: the counts are facts, the sentence is copy, and
 * copy belongs on the screen that shows it. "Nothing changed" is a REAL answer and gets its
 * own sentence - a reader has to be able to tell "I checked and it was already right" from
 * "I pressed a button and nothing happened".
 */
export function describeRecompute(result: QuotationRecomputeResult): string {
  const parts: string[] = [];
  if (result.no_longer_non_standard > 0) {
    parts.push(
      `${result.no_longer_non_standard} ${result.no_longer_non_standard === 1 ? 'line is' : 'lines are'} no longer non-standard`,
    );
  }
  if (result.now_non_standard > 0) {
    parts.push(
      `${result.now_non_standard} ${result.now_non_standard === 1 ? 'line is' : 'lines are'} now non-standard`,
    );
  }
  if (result.no_longer_below_floor > 0) {
    parts.push(
      `${result.no_longer_below_floor} ${result.no_longer_below_floor === 1 ? 'line is' : 'lines are'} no longer below floor`,
    );
  }
  if (result.now_below_floor > 0) {
    parts.push(
      `${result.now_below_floor} ${result.now_below_floor === 1 ? 'line is' : 'lines are'} now below floor`,
    );
  }
  if (result.floor_changed > 0) {
    parts.push(
      `${result.floor_changed} ${result.floor_changed === 1 ? 'line' : 'lines'} picked up a different floor`,
    );
  }
  if (parts.length === 0) {
    return `Nothing changed. All ${result.line_count} ${
      result.line_count === 1 ? 'line' : 'lines'
    } already match the series and price floors as they stand today.`;
  }
  return `${parts.join(', ')}.`;
}

/** The report, on the page rather than in a toast that takes it away after four seconds. */
function RecomputeSummary({
  result,
  onDismiss,
}: {
  result: QuotationRecomputeResult;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0">
        <p className="font-medium">{describeRecompute(result)}</p>
        {result.changed_lines.length > 0 && (
          <p className="mt-0.5 break-words text-muted-foreground">
            {result.changed_lines.join(', ')}
          </p>
        )}
        {/* Why some lines could not move. Without this the reader gets "nothing changed"
            over a set of lines naming products this company does not stock, which is true
            and tells them nothing about what to do next. */}
        {result.unresolved_products > 0 && (
          <p className="mt-0.5 text-muted-foreground">
            {`${result.unresolved_products} ${
              result.unresolved_products === 1 ? 'line names a product' : 'lines name products'
            } this company's catalogue does not carry, so ${
              result.unresolved_products === 1 ? 'it stays' : 'they stay'
            } flagged as off-catalog. Re-pick the product to clear it.`}
          </p>
        )}
      </div>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="shrink-0 self-start"
        onClick={onDismiss}
      >
        Dismiss
      </Button>
    </div>
  );
}
