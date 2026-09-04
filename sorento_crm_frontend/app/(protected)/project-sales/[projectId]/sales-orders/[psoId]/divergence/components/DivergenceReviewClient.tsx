'use client';

import * as React from 'react';
import Link from 'next/link';
import { toast } from '@/lib/toast';
import { ChevronDown, ChevronRight, Download, FileCheck2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { FileDropzone } from '@/components/common/FileDropzone';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useDivergence,
  useDivergenceMutations,
  useOpenDivergenceForOrder,
} from '../../../../../_shared/hooks/useSoDivergence';
import { saveBlobAs } from '../../../../../_shared/services/fileDownload';
import { downloadCorrectiveImportFile } from '../../../../../_shared/services/soDivergenceService';
import {
  DIVERGENCE_FIELD_LABELS,
  PRESENCE_LABELS,
} from '../../../../../_shared/types/soDivergence.types';
import type {
  DivergenceResolution,
  DivergenceRow,
} from '../../../../../_shared/types/soDivergence.types';
import { DivergenceRowDialog } from '../../../../../divergences/components/DivergenceRowDialog';

/** Rendered exactly as compared. Re-deriving a number here is how the screen ends up
 *  disagreeing with the reconciliation it is reporting on. */
function value(row: DivergenceRow, side: 'ours' | 'theirs', field: string) {
  const raw = row[side][field];
  if (raw === null || raw === undefined || raw === '') return null;
  if (field === 'delivery_date') return formatDateInMalaysia(String(raw));
  return String(raw);
}

function fieldsOf(row: DivergenceRow): string[] {
  if (row.differing_fields.length > 0) return row.differing_fields;
  // A row present on one side only has no differing field to name, so everything that
  // side carries is what the reviewer needs to see.
  const side = row.presence === 'theirs_only' ? row.theirs : row.ours;
  return Object.keys(side).filter(
    (key) => !['line_no', 'description', 'product_code'].includes(key),
  );
}

function ComparisonCell({
  label,
  text,
  tone,
}: {
  label: string;
  text: string | null;
  tone: 'ours' | 'theirs';
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`truncate tabular-nums ${tone === 'theirs' ? 'text-amber-700 dark:text-amber-400' : 'font-medium'}`}
        title={text ?? undefined}
      >
        {text ?? <span className="text-muted-foreground">-</span>}
      </p>
    </div>
  );
}

/**
 * The reconciliation screen (AC-N3, AC-N4).
 *
 * Ours, theirs and the difference, per row. Rows that AGREE are collapsed behind a count
 * rather than hidden: "47 lines agree" is the reassurance that makes the four that do not
 * worth reading, and dropping them would leave a reviewer unable to tell a matching
 * document from an unread one.
 *
 * Both actions open a dialog, because every answer carries a reason (AC-N7).
 */
export function DivergenceReviewClient({
  projectId,
  psoId,
}: {
  projectId: string;
  psoId: string;
}) {
  const open = useOpenDivergenceForOrder(psoId);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const divergenceId = selectedId ?? open.divergence?.id;

  // Pin the id the moment it is known, because the OPEN lookup stops returning it the
  // instant the last row is answered. Without this, finishing a reconciliation replaced
  // the "Reconciled" confirmation with "no difference is on record" - telling the
  // reviewer their work had vanished at exactly the moment it succeeded.
  React.useEffect(() => {
    if (!selectedId && open.divergence?.id) setSelectedId(open.divergence.id);
  }, [open.divergence?.id, selectedId]);
  const detail = useDivergence(divergenceId);
  const { ingestFile, resolveRow } = useDivergenceMutations(divergenceId);

  const [files, setFiles] = React.useState<File[]>([]);
  const [showAgreeing, setShowAgreeing] = React.useState(false);
  const [answering, setAnswering] = React.useState<{
    row: DivergenceRow;
    resolution: DivergenceResolution;
  } | null>(null);

  const data = detail.data;
  const rows = data?.rows ?? [];
  const outstanding = rows.filter((row) => row.needs_answer && !row.resolution);
  const answered = rows.filter((row) => row.needs_answer && row.resolution);
  const agreeing = rows.filter((row) => !row.needs_answer);

  const upload = async () => {
    const file = files[0];
    if (!file) return;
    const result = await ingestFile.mutateAsync(file);
    setFiles([]);
    if (result.divergence_id) setSelectedId(result.divergence_id);
  };

  const download = async () => {
    if (!divergenceId) return;
    try {
      const blob = await downloadCorrectiveImportFile(divergenceId);
      saveBlobAs(blob, `${data?.provisional_ref ?? 'corrective'}.csv`);
      await detail.refetch();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to build the file');
    }
  };

  // ------------------------------------------------------------------ loading

  if (open.isLoading || (divergenceId && detail.isLoading)) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  // ---------------------------------------------------- no reconciliation yet
  //
  // Rendered as a section with its own next step rather than hidden, per the CRUD
  // standard: this is also the screen a CS reaches to UPLOAD the export in the first
  // place, so an empty state that offers nothing would be a dead end.

  const uploadCard = (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Read an AutoCount export back</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Export this sales order from AutoCount and drop it here. Every line is compared
          against what we published: product, quantity, unit price and delivery date, plus
          the header terms. Nothing of ours is overwritten.
        </p>
        <FileDropzone
          accept=".csv,.xlsx"
          maxSizeMb={10}
          files={files}
          onFilesChange={setFiles}
          disabled={ingestFile.isPending}
          title="Drop the AutoCount export"
          hint="CSV or XLSX"
          aria-label="AutoCount sales order export"
          onReject={(file, reason) =>
            toast.error(
              reason === 'size'
                ? `${file.name} is larger than 10 MB`
                : reason === 'type'
                  ? `${file.name} is not a CSV or XLSX export`
                  : `${file.name} was not read: one file at a time`,
            )
          }
        />
        <Button type="button" onClick={upload} disabled={!files.length || ingestFile.isPending}>
          {ingestFile.isPending ? 'Comparing…' : 'Compare against AutoCount'}
        </Button>
      </CardContent>
    </Card>
  );

  if (!divergenceId || !data) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="min-w-0 text-xl font-semibold break-words">AutoCount comparison</h2>
          <Button asChild variant="outline">
            <Link href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
              Back to the sales order
            </Link>
          </Button>
        </div>
        <Alert>
          <FileCheck2 className="size-4" />
          <AlertTitle>No difference is on record for this sales order</AlertTitle>
          <AlertDescription>
            Either AutoCount agrees with what we published, or its document has not been
            read back yet.
          </AlertDescription>
        </Alert>
        {uploadCard}
      </div>
    );
  }

  // ------------------------------------------------------------------ content

  const resolved = data.status === 'resolved';

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold break-words">
            AutoCount comparison
            {data.autocount_doc_no ? ` - ${data.autocount_doc_no}` : ''}
          </h2>
          <p className="text-sm text-muted-foreground break-words">
            {data.project_title} · {data.provisional_ref}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.corrective_publish_required && (
            <Button type="button" variant="outline" onClick={download}>
              <Download className="size-4" />
              Corrective file
            </Button>
          )}
          <Button asChild variant="outline">
            <Link href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
              Back to the sales order
            </Link>
          </Button>
        </div>
      </div>

      {resolved ? (
        <Alert variant="success">
          <FileCheck2 className="size-4" />
          <AlertTitle>Reconciled</AlertTitle>
          <AlertDescription>
            Every difference has been answered, so this sales order can be amended again.
            {data.corrective_publish_required
              ? ' A corrective file is ready to send back to AutoCount.'
              : ''}
          </AlertDescription>
        </Alert>
      ) : (
        <Alert variant="warning">
          <AlertTitle>
            {outstanding.length} difference{outstanding.length === 1 ? '' : 's'} still to answer
          </AlertTitle>
          <AlertDescription>
            Amendments on this sales order are blocked until they are. Our values are
            unchanged: each row below asks which side is right.
          </AlertDescription>
        </Alert>
      )}

      {/* Counts first, because "how much of this document is fine" is the question a
          reviewer opens the screen with. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Rows compared', value: data.compared_count },
          { label: 'Agree', value: data.agreeing_count },
          { label: 'Differ', value: data.differing_count },
          { label: 'Unanswered', value: data.unresolved_count },
        ].map((tile) => (
          <Card key={tile.label}>
            <CardContent className="pt-6">
              <p className="text-xs text-muted-foreground">{tile.label}</p>
              <p className="text-2xl font-semibold tabular-nums">{tile.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Differences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {outstanding.length === 0 && answered.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing differs on this document.
            </p>
          ) : (
            [...outstanding, ...answered].map((row) => (
              <div
                key={row.id}
                className="rounded-lg border p-3 sm:p-4"
                data-testid={`divergence-row-${row.id}`}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      {row.scope === 'header'
                        ? 'Document header'
                        : row.product_code || 'Line without a product code'}
                      {row.line_no ? ` · line ${row.line_no}` : ''}
                    </p>
                    <Badge
                      variant={row.presence === 'both' ? 'warning' : 'destructive'}
                      appearance="light"
                      size="sm"
                      className="mt-1 w-fit"
                    >
                      {PRESENCE_LABELS[row.presence]}
                    </Badge>
                  </div>

                  {row.resolution ? (
                    <div className="min-w-0 sm:text-right">
                      <Badge variant="success" appearance="light" size="sm" className="w-fit">
                        {row.resolution === 'accept_theirs' ? 'AutoCount won' : 'Ours kept'}
                      </Badge>
                      {row.reason && (
                        <p
                          className="mt-1 break-words text-xs text-muted-foreground"
                          title={row.reason}
                        >
                          {row.reason}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setAnswering({ row, resolution: 'accept_theirs' })}
                      >
                        Accept AutoCount
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => setAnswering({ row, resolution: 'keep_ours' })}
                      >
                        Keep ours
                      </Button>
                    </div>
                  )}
                </div>

                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2 rounded-md bg-muted/40 p-3">
                    <p className="text-xs font-medium uppercase text-muted-foreground">Ours</p>
                    {fieldsOf(row).map((field) => (
                      <ComparisonCell
                        key={field}
                        label={DIVERGENCE_FIELD_LABELS[field] ?? field}
                        text={value(row, 'ours', field)}
                        tone="ours"
                      />
                    ))}
                  </div>
                  <div className="space-y-2 rounded-md bg-amber-50/60 p-3 dark:bg-amber-950/20">
                    <p className="text-xs font-medium uppercase text-muted-foreground">
                      AutoCount
                    </p>
                    {fieldsOf(row).map((field) => (
                      <ComparisonCell
                        key={field}
                        label={DIVERGENCE_FIELD_LABELS[field] ?? field}
                        text={value(row, 'theirs', field)}
                        tone="theirs"
                      />
                    ))}
                  </div>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Collapsed, not absent (AC-N3). */}
      {agreeing.length > 0 && (
        <Card>
          <CardHeader>
            <button
              type="button"
              className="flex w-full items-center gap-2 text-left"
              onClick={() => setShowAgreeing((current) => !current)}
              aria-expanded={showAgreeing}
            >
              {showAgreeing ? (
                <ChevronDown className="size-4" aria-hidden />
              ) : (
                <ChevronRight className="size-4" aria-hidden />
              )}
              <CardTitle className="text-base">
                {agreeing.length} row{agreeing.length === 1 ? ' agrees' : 's agree'}
              </CardTitle>
            </button>
          </CardHeader>
          {showAgreeing && (
            <CardContent className="space-y-1">
              {agreeing.map((row) => (
                <p key={row.id} className="truncate text-sm text-muted-foreground">
                  {row.scope === 'header'
                    ? 'Document header'
                    : `${row.product_code ?? 'Line'}${row.line_no ? ` · line ${row.line_no}` : ''}`}
                </p>
              ))}
            </CardContent>
          )}
        </Card>
      )}

      {/* Re-reading the export after somebody fixes it in AutoCount is how a difference
          is retired without anyone having to pretend they answered it. */}
      {!resolved && uploadCard}

      {answering && (
        <DivergenceRowDialog
          row={answering.row}
          resolution={answering.resolution}
          submitting={resolveRow.isPending}
          onDone={() => setAnswering(null)}
          onResolve={(reason) =>
            resolveRow.mutateAsync({
              rowId: answering.row.id,
              resolution: answering.resolution,
              reason,
            })
          }
        />
      )}
    </div>
  );
}
