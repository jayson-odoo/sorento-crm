'use client';

import * as React from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, CheckCircle2, Stamp } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useProject } from '../../_shared/hooks/useProjects';
import { usePOIntakeController } from '../../_shared/hooks/usePOIntake';
import type { POVersion, POVersionLine } from '../../_shared/types/poIntake.types';
import { describeReadingTime } from '../../_shared/lib/readingTime';
import { POIntakeAnnotationsGrid } from './POIntakeAnnotationsGrid';
import { POIntakeDocumentViewer } from './POIntakeDocumentViewer';
import {
  POIntakeExtractionFailed,
  POIntakeExtractionProgress,
  POIntakeNoLines,
  POIntakePartialBanner,
  POIntakeSkeleton,
} from './POIntakeExtractionStatus';
import { POIntakeHeaderFields } from './POIntakeHeaderFields';
import {
  POIntakeLinesGrid,
  lineNeedsAttention,
  type POIntakeLinesGridHandle,
} from './POIntakeLinesGrid';
import {
  PO_MOCK_PARAM,
  isPOMockScenario,
  usePOIntakeMockController,
} from './POIntakeMocks';
import { POIntakeTotalsBanner } from './POIntakeTotalsBanner';
import { POIntakeUploadDialog } from './POIntakeUploadDialog';

/**
 * "Did I get this right?" for one uploaded customer PO.
 *
 * The order on the screen is the order the question is answered in: the money difference
 * between our sum and the paper first, then the header, then the 52 lines, then the pencil.
 * The page image stays beside all of it and follows whatever is in focus.
 */
export function POIntakeConfirmClient({
  projectId,
  versionId,
}: {
  projectId: string;
  versionId: string;
}) {
  const searchParams = useSearchParams();
  const rawScenario = searchParams?.get(PO_MOCK_PARAM) ?? null;
  const scenario = isPOMockScenario(rawScenario) ? rawScenario : null;

  // Both controllers are created every render (hooks cannot be conditional); only one runs a
  // query, and the mocked one never talks to the network.
  const live = usePOIntakeController(versionId, { enabled: !scenario });
  const mocked = usePOIntakeMockController(scenario);
  const intake = scenario ? mocked : live;

  const project = useProject(projectId);
  const canEdit = project.data ? project.data.can_edit !== false : true;

  const gridRef = React.useRef<POIntakeLinesGridHandle>(null);
  const notesRef = React.useRef<HTMLDivElement>(null);
  const viewerRef = React.useRef<HTMLDivElement>(null);
  const [page, setPage] = React.useState(1);
  const [focusedLineId, setFocusedLineId] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);

  const version = intake.version;

  /**
   * Takes the reader to the page a note was written on, rather than only loading it.
   *
   * Setting the page is the whole job on a wide screen, where the scan is pinned beside the
   * notes and the change is visible without moving. On a phone the scan is a screen and a
   * half ABOVE the note that was just clicked, so the page would change where nobody could
   * see it. `block: 'nearest'` is what keeps the desktop case still: an element already in
   * view is not scrolled at all. jsdom implements no scrollIntoView, hence the optional call.
   */
  const showPage = React.useCallback((pageNo: number) => {
    setPage(pageNo);
    viewerRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
  }, []);

  const focusLine = React.useCallback((line: POVersionLine) => {
    setFocusedLineId(line.id);
    if (line.page_no) setPage(line.page_no);
  }, []);

  const focusLineNo = React.useCallback(
    (lineNo: number) => {
      const line = version?.lines.find((item) => item.line_no === lineNo);
      if (!line) return;
      gridRef.current?.focusLine(line.id);
      if (line.page_no) setPage(line.page_no);
    },
    [version],
  );

  // Same predicate the grid's filter and its count use, so "the first problem line" is the
  // first of exactly the lines the grid says need attention.
  const jumpToProblem = React.useCallback(() => {
    const target =
      version?.lines.find((line) => !line.is_cancelled && !line.arithmetic_ok) ??
      version?.lines.find(lineNeedsAttention);
    if (target) gridRef.current?.focusLine(target.id);
  }, [version]);

  if (intake.isLoading) return <POIntakeSkeleton />;

  if (intake.isError || !version) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This PO document could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {intake.error instanceof Error
            ? intake.error.message
            : 'It may have been removed, or you may not have access to this project.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}`}>Back to the project</Link>
        </Button>
      </div>
    );
  }

  const stamps = {
    po_number: version.purchase_order?.po_number ?? version.header.po_number,
    status: version.purchase_order?.status ?? null,
    approved_by_name:
      version.purchase_order?.approved_by_name ?? version.approved_by_name ?? null,
    approved_at: version.purchase_order?.approved_at ?? version.approved_at ?? null,
    countersigned_by_name:
      version.purchase_order?.countersigned_by_name ??
      version.countersigned_by_name ??
      null,
    countersigned_at:
      version.purchase_order?.countersigned_at ?? version.countersigned_at ?? null,
  };

  const unreviewed = version.annotations.filter((note) => note.state === 'proposed');
  const confirmed = Boolean(version.confirmed_at);
  const readOnly = !canEdit || confirmed;

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <Button asChild variant="link" size="sm" className="mb-1 h-auto p-0 text-xs">
            <Link href={`/project-sales/${projectId}`}>
              <ArrowLeft className="size-3.5" aria-hidden />
              Back to the project
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{`Version ${version.version_no}`}</Badge>
            <PhaseBadge version={version} />
            {confirmed && <Badge variant="success">Confirmed</Badge>}
            {stamps.approved_at && <Badge variant="secondary">Approved</Badge>}
            {stamps.countersigned_at && <Badge variant="secondary">Countersigned</Badge>}
            {!canEdit && <Badge variant="outline">Read only</Badge>}
            {intake.isMock && <Badge variant="warning">Sample data</Badge>}
          </div>
          <h1 className="mt-1 text-xl font-semibold">
            {stamps.po_number ? `PO ${stamps.po_number}` : 'PO number not read yet'}
          </h1>
          <p className="text-sm text-muted-foreground">
            {[
              version.header.admin_ref,
              version.page_count ? `${version.page_count} pages` : null,
              `${version.lines.length} lines`,
              describeReadingTime(version.extraction_elapsed_ms),
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!readOnly && (
            <div className="flex flex-col items-end gap-1">
              <Button
                type="button"
                disabled={
                  unreviewed.length > 0 ||
                  intake.isConfirming ||
                  version.lines.length === 0
                }
                onClick={() => void intake.confirm()}
              >
                <CheckCircle2 className="size-4" aria-hidden />
                {intake.isConfirming ? 'Confirming…' : 'Confirm this PO'}
              </Button>
              {unreviewed.length > 0 && (
                <span className="flex flex-wrap items-center gap-1 text-right text-xs text-muted-foreground">
                  {`${unreviewed.length} handwritten note${unreviewed.length === 1 ? '' : 's'} still unreviewed`}
                  <Button
                    type="button"
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() =>
                      notesRef.current?.scrollIntoView?.({
                        block: 'start',
                        behavior: 'smooth',
                      })
                    }
                  >
                    Review them
                  </Button>
                </span>
              )}
            </div>
          )}
          {confirmed && !stamps.approved_at && canEdit && (
            <Button
              type="button"
              variant="outline"
              disabled={intake.isStamping}
              onClick={() => void intake.approve()}
            >
              <Stamp className="size-4" aria-hidden />
              Approve
            </Button>
          )}
          {stamps.approved_at && !stamps.countersigned_at && canEdit && (
            <Button
              type="button"
              variant="outline"
              disabled={intake.isStamping}
              onClick={() => void intake.countersign()}
            >
              <Stamp className="size-4" aria-hidden />
              Countersign
            </Button>
          )}
        </div>
      </header>

      <Signatures
        confirmedAt={version.confirmed_at}
        confirmedBy={version.confirmed_by_name ?? null}
        approvedAt={stamps.approved_at}
        approvedBy={stamps.approved_by_name}
        countersignedAt={stamps.countersigned_at}
        countersignedBy={stamps.countersigned_by_name}
      />

      {version.extraction_state === 'failed' ? (
        <POIntakeExtractionFailed
          version={version}
          onReupload={canEdit ? () => setUploading(true) : undefined}
        />
      ) : intake.isPolling ? (
        <POIntakeExtractionProgress version={version} />
      ) : (
        <>
          {intake.phase === 'partial' && (
            <POIntakePartialBanner
              version={version}
              onReupload={canEdit ? () => setUploading(true) : undefined}
            />
          )}

          <POIntakeTotalsBanner version={version} onJumpToProblem={jumpToProblem} />

          <div className="flex min-w-0 flex-col gap-4 lg:flex-row">
            <div ref={viewerRef} className="min-w-0 lg:w-[38%]">
              <POIntakeDocumentViewer
                documentUrl={version.document_url}
                // The version id, so a re-signed URL for the same scan is not treated as
                // a different document and the reader keeps their place.
                documentKey={version.id}
                pageCount={version.page_count}
                page={page}
                onPageChange={setPage}
                className="lg:sticky lg:top-4 lg:h-[calc(100vh-8rem)]"
              />
            </div>

            <div className="min-w-0 flex-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">
                    What the top of the document says
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <POIntakeHeaderFields
                    header={version.header}
                    readOnly={readOnly}
                    saving={intake.isSavingHeader}
                    onSave={intake.updateHeader}
                  />
                </CardContent>
              </Card>

              <Card>
                {/* No count here on purpose: the grid states how many lines need attention,
                    and two counts on one card is how people learn to read neither. */}
                <CardHeader>
                  <CardTitle className="text-sm">Lines</CardTitle>
                </CardHeader>
                <CardContent>
                  {version.lines.length === 0 ? (
                    <POIntakeNoLines
                      onReupload={canEdit ? () => setUploading(true) : undefined}
                    />
                  ) : (
                    <POIntakeLinesGrid
                      ref={gridRef}
                      lines={version.lines}
                      readOnly={readOnly}
                      savingLineIds={intake.savingLineIds}
                      focusedLineId={focusedLineId}
                      onFocusLine={focusLine}
                      onUpdateLine={intake.updateLine}
                    />
                  )}
                </CardContent>
              </Card>

              <div ref={notesRef} className="min-w-0">
                <Card>
                  <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <CardTitle className="text-sm">Handwriting on the paper</CardTitle>
                    {unreviewed.length > 0 && (
                      <Badge variant="warning">{`${unreviewed.length} to review`}</Badge>
                    )}
                  </CardHeader>
                  <CardContent>
                    <POIntakeAnnotationsGrid
                      annotations={version.annotations}
                      lines={version.lines}
                      readOnly={readOnly}
                      savingAnnotationIds={intake.savingAnnotationIds}
                      onShowPage={showPage}
                      onFocusLineNo={focusLineNo}
                      onAccept={intake.acceptAnnotation}
                      onEdit={intake.editAnnotation}
                      onReject={intake.rejectAnnotation}
                    />
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        </>
      )}

      {uploading && (
        <POIntakeUploadDialog
          projectId={projectId}
          purchaseOrderId={version.purchase_order_id}
          purchaseOrderNumber={stamps.po_number}
          onDone={() => setUploading(false)}
        />
      )}
    </div>
  );
}

function PhaseBadge({ version }: { version: POVersion }) {
  switch (version.extraction_state) {
    case 'queued':
      return <Badge variant="secondary">Waiting to be read</Badge>;
    case 'running':
      return <Badge variant="secondary">Being read</Badge>;
    case 'failed':
      return <Badge variant="destructive">Could not be read</Badge>;
    default:
      return null;
  }
}

/**
 * Confirm, approve and countersign are three separate stamps, and each is shown with the
 * name and the time on it. A section that vanished when empty would leave "was this
 * countersigned?" unanswerable, so every stamp renders either its name or its absence.
 */
function Signatures({
  confirmedAt,
  confirmedBy,
  approvedAt,
  approvedBy,
  countersignedAt,
  countersignedBy,
}: {
  confirmedAt: string | null;
  confirmedBy: string | null;
  approvedAt: string | null;
  approvedBy: string | null;
  countersignedAt: string | null;
  countersignedBy: string | null;
}) {
  const rows: Array<{ label: string; at: string | null; by: string | null }> = [
    { label: 'Confirmed', at: confirmedAt, by: confirmedBy },
    { label: 'Approved', at: approvedAt, by: approvedBy },
    { label: 'Countersigned', at: countersignedAt, by: countersignedBy },
  ];

  return (
    <dl className="grid gap-x-6 gap-y-2 rounded-lg border border-border px-4 py-3 sm:grid-cols-3">
      {rows.map((row) => (
        <div key={row.label} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{row.label}</dt>
          <dd className="truncate text-sm font-medium" title={row.by ?? undefined}>
            {row.at
              ? `${row.by ?? 'Recorded'} · ${formatDateTimeInMalaysia(row.at)}`
              : 'Not yet'}
          </dd>
        </div>
      ))}
    </dl>
  );
}
