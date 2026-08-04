'use client';

import { useEffect, useRef, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
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
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  applyOutstandingImport,
  previewOutstandingImport,
  type OutstandingApplyResult,
  type OutstandingChangeKind,
  type OutstandingCounts,
  type OutstandingImportKind,
  type OutstandingPreview,
  type OutstandingResolutionIssue,
  type OutstandingRowProblem,
  type OutstandingSampleRow,
} from '../services/outstandingImportService';

/**
 * SCM - the upload channel for the open order book, until AutoCount is integrated.
 *
 * Two steps, never one click: choosing a file PREVIEWS it (writes nothing) and the
 * user confirms the diff before anything is saved. The whole reorder plan is computed
 * from this data, so a wrong file quietly imported is a week of unpicking.
 *
 * The diff shows a count for every change kind INCLUDING `unchanged` (a diff that
 * shows only changes is indistinguishable from one that silently failed to read the
 * file), sample rows as evidence, the documents the file covers, and every row it
 * could not read or match. None of those problems blocks a file that is otherwise
 * usable - only a header missing required columns does.
 */

const MAX_SIZE_MB = 25;

/**
 * The formats this importer reads, and the authoritative list: a file with any other
 * extension is refused here rather than sent for the backend to refuse. .xlsm is in
 * because macro workbooks are stripped on the way in.
 */
const ACCEPT = '.xlsx,.xlsm';

/** ".xlsx or .xlsm" - for the rejection message, so it can never drift from ACCEPT. */
const ACCEPTED_FORMATS = ACCEPT.split(',').join(' or ');

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
  return value == null ? '-' : value.toLocaleString();
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

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

// ── pieces ──────────────────────────────────────────────────────────────────

function CountTile({ label, value }: { label: string; value: number }) {
  return (
    <div data-slot="count-tile" className="rounded-lg border border-border px-3 py-2">
      <div className="text-lg font-semibold tabular-nums leading-tight">
        {value.toLocaleString()}
      </div>
      <div className="text-2xs text-muted-foreground">{label}</div>
    </div>
  );
}

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
}: {
  unmappedHeaders: string[];
  rowProblems: OutstandingRowProblem[];
  resolutionIssues: OutstandingResolutionIssue[];
}) {
  if (!unmappedHeaders.length && !rowProblems.length && !resolutionIssues.length) return null;

  return (
    <div className="space-y-3">
      {unmappedHeaders.length ? (
        <div className="rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold">
            Columns we did not recognise ({unmappedHeaders.length})
          </h4>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {unmappedHeaders.map((header) => (
              <span
                key={header}
                className="rounded bg-muted px-1.5 py-0.5 text-2xs text-muted-foreground"
              >
                {header}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {rowProblems.length ? (
        <div className="rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold">
            Rows we could not read ({rowProblems.length})
          </h4>
          <ul className="mt-1.5 space-y-1">
            {rowProblems.map((problem) => (
              <li
                key={`${problem.row_number}-${problem.reason}`}
                className="flex flex-wrap items-baseline gap-x-1.5 text-2xs text-muted-foreground"
              >
                <span className="font-medium text-foreground">Row {problem.row_number}</span>
                <span>{problem.reason}</span>
                {problem.value ? (
                  <span className="rounded bg-muted px-1 py-0.5 font-mono">{problem.value}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {resolutionIssues.length ? (
        <div className="rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold">
            Rows we could not match ({resolutionIssues.length})
          </h4>
          <ul className="mt-1.5 space-y-1">
            {resolutionIssues.map((issue) => (
              <li
                key={`${issue.row_number}-${issue.field}-${issue.value}`}
                className="flex flex-wrap items-baseline gap-x-1.5 text-2xs text-muted-foreground"
              >
                <span className="font-medium text-foreground">Row {issue.row_number}</span>
                <span>{issue.field}</span>
                <span className="rounded bg-muted px-1 py-0.5 font-mono">{issue.value}</span>
                <span>{issue.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

// ── dialog ──────────────────────────────────────────────────────────────────

export interface OutstandingUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: OutstandingImportKind;
  /** Fired once the write succeeds, so the page can refresh what it derives from it. */
  onApplied?: (result: OutstandingApplyResult) => void;
}

export function OutstandingUploadDialog({
  open,
  onOpenChange,
  kind,
  onApplied,
}: OutstandingUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<OutstandingPreview | null>(null);
  const [result, setResult] = useState<OutstandingApplyResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A second pick while the first preview is still in flight must not have the older
  // response land on top of the newer one.
  const seq = useRef(0);

  useEffect(() => {
    if (!open) return;
    seq.current += 1;
    setFile(null);
    setPreview(null);
    setResult(null);
    setPreviewing(false);
    setApplying(false);
    setError(null);
  }, [open]);

  const choose = async (next: File | null) => {
    const token = ++seq.current;
    setFile(next);
    setPreview(null);
    setResult(null);
    setError(null);
    if (!next) return;

    setPreviewing(true);
    try {
      const previewed = await previewOutstandingImport(kind, next);
      if (seq.current !== token) return;
      setPreview(previewed);
    } catch (e) {
      if (seq.current !== token) return;
      setError(messageOf(e, 'Failed to read the file.'));
    } finally {
      if (seq.current === token) setPreviewing(false);
    }
  };

  const reject = (rejected: File, reason: 'type' | 'size' | 'extra') => {
    // Single-file zone: the first file is already previewing, the rest are noise.
    if (reason === 'extra') return;
    if (reason === 'size') {
      setError(`${rejected.name} is larger than ${MAX_SIZE_MB} MB.`);
      return;
    }
    // 'type': ACCEPT is this importer's authoritative format list, so refuse it now.
    // Uploading it to be told what the extension already said would cost the user a
    // round trip, and forwarding a file the dropzone rejected would make its filter
    // mean nothing.
    setError(`${rejected.name} is not a ${ACCEPTED_FORMATS} file.`);
  };

  const applyUpload = async () => {
    if (!file) return;
    setApplying(true);
    setError(null);
    try {
      const applied = await applyOutstandingImport(kind, file);
      setResult(applied);
      onApplied?.(applied);
    } catch (e) {
      setError(messageOf(e, 'Failed to apply the upload.'));
    } finally {
      setApplying(false);
    }
  };

  const usable = !!preview && preview.ok;
  const hasChanges = !!preview && ACTIONABLE_KINDS.some((k) => countOf(preview.counts, k) > 0);
  const canConfirm = !!file && usable && hasChanges && !previewing && !applying;

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
          <DialogDescription>Nothing is saved until you confirm the changes.</DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {result ? (
            <div className="space-y-3">
              <p className="text-sm font-medium">Upload applied.</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <CountTile label="Added" value={result.applied.added} />
                <CountTile label="Updated" value={result.applied.updated} />
                <CountTile label="Closed" value={result.applied.closed} />
                <CountTile label="Unchanged" value={result.applied.unchanged} />
              </div>
              <p className="text-2xs text-muted-foreground">
                {result.scope_documents.length.toLocaleString()}{' '}
                {plural(result.scope_documents.length, 'document', 'documents')} in this file.
              </p>
              <ProblemSections
                unmappedHeaders={[]}
                rowProblems={result.row_problems}
                resolutionIssues={result.resolution_issues}
              />
            </div>
          ) : (
            <>
              <FileDropzone
                files={file ? [file] : []}
                onFilesChange={(next) => void choose(next[0] ?? null)}
                onReject={reject}
                accept={ACCEPT}
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
                      {preview.total_rows.toLocaleString()} rows read
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
                      Covers {scopeCount.toLocaleString()}{' '}
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
                          +{(scopeCount - SCOPE_CHIP_LIMIT).toLocaleString()} more
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
                        {Math.max(group.total, group.rows.length).toLocaleString()})
                      </h4>
                      <SampleTable rows={group.rows} />
                    </div>
                  ))}

                  <ProblemSections
                    unmappedHeaders={preview.unmapped_headers}
                    rowProblems={preview.row_problems}
                    resolutionIssues={preview.resolution_issues}
                  />
                </div>
              ) : null}
            </>
          )}
        </DialogBody>

        <DialogFooter>
          {result ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={applying}
              >
                Cancel
              </Button>
              <Button onClick={() => void applyUpload()} disabled={!canConfirm}>
                {applying ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
                Confirm upload
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default OutstandingUploadDialog;
