'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { ImportFeedbackSections } from '@/components/common/ImportFeedbackSections';
import { useImportJobDrawer } from '@/components/upload-activity/useImportJobDrawer';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';
import { formatDateInMalaysia } from '@/lib/helpers';
import { MAX_SIZE_MB, useTwoStepUpload } from '../hooks/useTwoStepUpload';
import {
  applyOutstandingImport,
  previewOutstandingImport,
  type OutstandingAgentNotice,
  type OutstandingChangeKind,
  type OutstandingCounts,
  type OutstandingImportKind,
  type OutstandingPreview,
  type OutstandingResolutionIssue,
  type OutstandingRowProblem,
  type OutstandingSampleRow,
} from '../services/outstandingImportService';
import { CountTile } from './UploadCountTile';
import { fmtInt } from '../../lib/format';

/**
 * SCM - the upload channel for the open order book, until AutoCount is integrated.
 *
 * Test, then upload - the same three presses as the GRN, SPO and customer importers.
 * Choosing a file runs nothing; Test reads it and shows the diff; Confirm queues the write
 * as an import job and hands the watching to the upload drawer. The whole reorder plan is
 * computed from this data, so a wrong file quietly imported is a week of unpicking.
 *
 * The diff shows a count for every change kind INCLUDING `unchanged` (a diff that
 * shows only changes is indistinguishable from one that silently failed to read the
 * file), sample rows as evidence, the documents the file covers, and every row it
 * could not read or match. None of those problems blocks a file that is otherwise
 * usable - only a header missing required columns does.
 *
 * What the upload DID is not shown here any more: the write happens on the worker, so the
 * counts do not exist when this dialog closes. They land on the job page, which is where
 * every other importer in this system reports its outcome.
 */

const TITLES: Record<OutstandingImportKind, string> = {
  'sales-orders': 'Upload outstanding sales orders',
  'purchase-orders': 'Upload outstanding purchase orders',
};

/** Ordered so the diff always reads the same way, and `unchanged` is always last. */
const CHANGE_LABELS: ReadonlyArray<readonly [OutstandingChangeKind, string]> = [
  ['added', 'Added'],
  ['qty_changed', 'Quantity changed'],
  ['date_moved', 'Date moved'],
  ['date_and_qty_changed', 'Date and quantity changed'],
  ['closed', 'Closed'],
  ['unchanged', 'Unchanged'],
] as const;

/** Everything except `unchanged` - what makes a file worth applying. */
const ACTIONABLE_KINDS: OutstandingChangeKind[] = [
  'added',
  'qty_changed',
  'date_moved',
  'date_and_qty_changed',
  'closed',
];

/** How many scope documents to name before collapsing the rest into a tail count. */
const SCOPE_CHIP_LIMIT = 12;

function countOf(counts: OutstandingCounts, kind: OutstandingChangeKind): number {
  return counts[kind] ?? 0;
}

function num(value: number | null): string {
  return fmtInt(value);
}

function date(value: string | null): string {
  return value ? formatDateInMalaysia(value) : '-';
}

/** "+14 days" / "-7 days" - the sign is the whole point, so it is never dropped. */
function moved(days: number | null): string {
  if (days == null) return '-';
  const unit = Math.abs(days) === 1 ? 'day' : 'days';
  return `${days > 0 ? '+' : ''}${days} ${unit}`;
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

// ── pieces ──────────────────────────────────────────────────────────────────

function SampleTable({ rows }: { rows: OutstandingSampleRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[46rem] text-2xs">
        <thead className="bg-muted/50 text-muted-foreground">
          <tr>
            <th className="px-2 py-1.5 text-start font-medium">Document</th>
            <th className="px-2 py-1.5 text-start font-medium">Item</th>
            <th className="px-2 py-1.5 text-start font-medium">Location</th>
            <th className="px-2 py-1.5 text-end font-medium">Qty before</th>
            <th className="px-2 py-1.5 text-end font-medium">Qty after</th>
            <th className="px-2 py-1.5 text-start font-medium">Date before</th>
            <th className="px-2 py-1.5 text-start font-medium">Date after</th>
            <th className="px-2 py-1.5 text-start font-medium">Moved</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`${row.doc_number}-${row.item_code}-${row.location}-${index}`}
              className="border-t border-border align-top"
            >
              <td className="px-2 py-1.5">
                <div className="font-medium">{row.doc_number}</div>
                {row.label ? (
                  <div
                    className="max-w-[10rem] truncate text-muted-foreground"
                    title={row.label}
                  >
                    {row.label}
                  </div>
                ) : null}
              </td>
              <td className="px-2 py-1.5 font-medium">{row.item_code}</td>
              <td className="px-2 py-1.5">{row.location || '-'}</td>
              <td className="px-2 py-1.5 text-end tabular-nums">{num(row.qty_before)}</td>
              <td className="px-2 py-1.5 text-end tabular-nums">{num(row.qty_after)}</td>
              <td className="px-2 py-1.5 tabular-nums">{date(row.date_before)}</td>
              <td className="px-2 py-1.5 tabular-nums">{date(row.date_after)}</td>
              <td className="px-2 py-1.5 tabular-nums">{moved(row.days_moved)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProblemSections({
  unmappedHeaders,
  rowProblems,
  resolutionIssues,
  unmappedAgents,
}: {
  unmappedHeaders: string[];
  rowProblems: OutstandingRowProblem[];
  resolutionIssues: OutstandingResolutionIssue[];
  unmappedAgents: OutstandingAgentNotice[];
}) {
  /**
   * An adapter onto the shared rendering, not a panel of its own: the GRN, SPO and customer
   * import dialogs show the same four kinds of thing and had four different-looking ways of
   * showing them.
   *
   * `skippedCount` is deliberately NOT passed. This channel's row problems are a mixture -
   * a row the reader could not use IS dropped, but "this document states no order type" is
   * a document that imported perfectly well - so a heading claiming N rows skipped would be
   * wrong for half the list. The count that IS a skip count lives on the job.
   */
  return (
    <ImportFeedbackSections
      unrecognisedColumns={unmappedHeaders}
      rejectedRows={rowProblems.map((problem) => ({
        row: problem.row_number || null,
        reason: problem.reason,
        value: problem.value || null,
      }))}
      notices={[
        {
          key: 'resolution',
          title: 'Rows we could not match',
          items: resolutionIssues.map((issue, index) => ({
            key: `${issue.row_number}-${issue.field}-${issue.value}-${index}`,
            lead: `Row ${issue.row_number}`,
            code: issue.value,
            text: `${issue.field}: ${issue.reason}`,
          })),
        },
        {
          key: 'agents',
          // Worded as the backend words it, and kept OUT of the rejected rows: nothing was
          // skipped and no row failed, so listing these among the failures would make a
          // clean file read as a broken one.
          title: 'Agents with no demand class',
          // No hint line under it: the title says what the list is and each row carries the
          // backend's own reason, so a sentence explaining the consequence is teaching text
          // in a report screen.
          items: unmappedAgents.map((agent) => ({
            key: agent.code,
            code: agent.code,
            text: agent.reason,
          })),
        },
      ]}
    />
  );
}

// ── dialog ──────────────────────────────────────────────────────────────────

export interface OutstandingUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: OutstandingImportKind;
  /** Fired once the job is queued, so a page can react to the upload having started. */
  onQueued?: (queued: ImportQueuedResult) => void;
}

export function OutstandingUploadDialog({
  open,
  onOpenChange,
  kind,
  onQueued,
}: OutstandingUploadDialogProps) {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();
  const upload = useTwoStepUpload<OutstandingPreview, ImportQueuedResult>({
    open,
    preview: (f) => previewOutstandingImport(kind, f),
    apply: (f) => applyOutstandingImport(kind, f),
    onApplied: (queued) => {
      // The work is not tied to this tab: open the drawer, close the dialog, and let the
      // job be followed there.
      notifyImportQueued();
      onOpenChange(false);
      toast.success('Upload queued. Processing in the background.', {
        duration: 6000,
        action: {
          label: 'View job',
          onClick: () => router.push(`/system-management/import-jobs/${queued.job_id}`),
        },
      });
      onQueued?.(queued);
    },
  });
  const { file, preview, previewing, applying, error } = upload;

  const hasChanges = !!preview && ACTIONABLE_KINDS.some((k) => countOf(preview.counts, k) > 0);
  /**
   * Confirmable once a file is picked. Deliberately NOT "once it has been tested and shows
   * changes": Test is a tool, not a gate, and the same rule holds in every other import
   * dialog. A file already tested and known to change nothing is the one case worth
   * blocking, because there is nothing for the job to do.
   */
  const canConfirm = upload.canConfirm && (!preview || hasChanges);

  const sampleGroups = preview
    ? CHANGE_LABELS.map(([key, label]) => ({
        key,
        label,
        rows: preview.samples[key] ?? [],
        total: countOf(preview.counts, key),
      })).filter((group) => group.rows.length > 0)
    : [];

  const scopeCount = preview?.scope_documents.length ?? 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{TITLES[kind]}</DialogTitle>
          {/* One line, and it earns its place twice over: it is the promise the two-step
              flow makes, and it is the dialog's accessible description. Without a
              description Radix warns that the content has no `aria-describedby`. */}
          <DialogDescription>Test reads the file. Confirm queues the upload.</DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <FileDropzone
            files={file ? [file] : []}
            onFilesChange={(next) => upload.choose(next[0] ?? null)}
            onReject={upload.reject}
            accept={upload.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={previewing || applying}
            aria-label="Outstanding orders file"
          />

          {previewing ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
              Reading the file...
            </div>
          ) : null}

          {preview && !preview.ok ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3">
              <p className="text-sm font-medium">This file is missing required columns.</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {preview.missing_columns.map((column) => (
                  <span
                    key={column}
                    className="rounded bg-muted px-1.5 py-0.5 text-2xs font-mono"
                  >
                    {column}
                  </span>
                ))}
              </div>
              <p className="mt-1.5 text-2xs text-muted-foreground">
                Add them to the export, then upload it again.
              </p>
            </div>
          ) : null}

          {preview && preview.ok ? (
            <div className="space-y-4">
              <div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {CHANGE_LABELS.map(([key, label]) => (
                    <CountTile key={key} label={label} value={countOf(preview.counts, key)} />
                  ))}
                </div>
                <p className="mt-1.5 text-2xs text-muted-foreground">
                  {fmtInt(preview.total_rows)} rows read
                  {file ? ` from ${file.name}` : ''}.
                </p>
                {!hasChanges ? (
                  <p className="mt-1.5 text-sm font-medium">
                    Nothing would change - every line already matches what we hold.
                  </p>
                ) : null}
              </div>

              <section aria-label="Scope" className="rounded-lg border border-border p-3">
                <h4 className="text-xs font-semibold">
                  Covers {fmtInt(scopeCount)}{' '}
                  {plural(scopeCount, 'document', 'documents')}
                </h4>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {preview.scope_documents.slice(0, SCOPE_CHIP_LIMIT).map((doc) => (
                    <span
                      key={doc}
                      className="rounded bg-muted px-1.5 py-0.5 text-2xs font-medium"
                    >
                      {doc}
                    </span>
                  ))}
                  {scopeCount > SCOPE_CHIP_LIMIT ? (
                    <span className="px-1.5 py-0.5 text-2xs text-muted-foreground">
                      +{fmtInt(scopeCount - SCOPE_CHIP_LIMIT)} more
                    </span>
                  ) : null}
                </div>
                <p className="mt-1.5 text-2xs text-muted-foreground">
                  Orders not in this file are untouched.
                </p>
              </section>

              {sampleGroups.map((group) => (
                <div key={group.key} className="space-y-1.5">
                  <h4 className="text-xs font-semibold">
                    {group.label} (showing {group.rows.length} of{' '}
                    {fmtInt(Math.max(group.total, group.rows.length))})
                  </h4>
                  <SampleTable rows={group.rows} />
                </div>
              ))}

              <ProblemSections
                unmappedHeaders={preview.unmapped_headers}
                rowProblems={preview.row_problems}
                resolutionIssues={preview.resolution_issues}
                unmappedAgents={preview.unmapped_agents ?? []}
              />
            </div>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void upload.runTest()}
            disabled={!file || previewing || applying || upload.testing}
          >
            {upload.testing ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <TestTube className="size-4" aria-hidden />
            )}
            Test
          </Button>
          <Button onClick={() => void upload.confirm()} disabled={!canConfirm}>
            {applying ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
            Confirm upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default OutstandingUploadDialog;
