'use client';

import * as React from 'react';
import {
  AlertTriangle,
  Pencil,
  Plus,
  ReceiptText,
  Trash2,
  TrendingDown,
  Upload,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  usePurchaseOrderMutations,
  usePurchaseOrders,
} from '../../_shared/hooks/useProjects';
import { POToSalesOrderStep } from './POToSalesOrderStep';
import type { Project, ProjectPurchaseOrder } from '../../_shared/types/project.types';
import { formatMyr } from './QuotationsPanel';
import { PurchaseOrderDialog } from './PurchaseOrderDialog';
import { PurchaseOrderLinesEditor } from './PurchaseOrderLinesEditor';
import { POIntakeUploadDialog } from './POIntakeUploadDialog';
import { POIntakeVersionsStrip } from './POIntakeVersionsStrip';

const SOURCE_LABELS: Record<string, string> = {
  contractor_direct: 'Contractor direct',
  trading_house: 'Trading house',
};

/**
 * Customer POs against this project (AC-F8).
 *
 * The two signals AC-F9 and AC-F9a ask for are shown side by side and read differently
 * on purpose: a MISMATCH is an exception worth chasing, while DRIFT from v1 is the
 * expected result of a negotiation and is shown as a plain number. Presenting erosion as
 * an alert would make every successfully negotiated PO look like a problem.
 *
 * This is also the ONE place a customer PO document is uploaded (P4). The scan and the PO
 * row are the same commitment, so a second home for POs would immediately mean two answers
 * to "what did they order".
 */
export function PurchaseOrdersPanel({ project }: { project: Project }) {
  const purchaseOrders = usePurchaseOrders(project.id);
  const { remove } = usePurchaseOrderMutations(project.id);

  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState<ProjectPurchaseOrder | null>(null);
  const [deleting, setDeleting] = React.useState<ProjectPurchaseOrder | null>(null);
  const [openId, setOpenId] = React.useState<string | null>(null);
  // A `po` of null means "a PO we have no row for yet"; a PO means "another version of this
  // one", which is how a re-scanned PO stays one commitment instead of becoming two.
  const [uploadingFor, setUploadingFor] = React.useState<{
    po: ProjectPurchaseOrder | null;
  } | null>(null);

  const rows = React.useMemo(() => purchaseOrders.data ?? [], [purchaseOrders.data]);
  const totalValue = rows.reduce((sum, row) => sum + Number(row.line_total || 0), 0);
  const flagged = rows.filter(
    (row) => row.model_mismatch_count > 0 || row.price_mismatch_count > 0,
  ).length;

  React.useEffect(() => {
    if (!openId && rows.length > 0) setOpenId(rows[0].id);
  }, [openId, rows]);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-sm">Purchase orders</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              What the customer actually ordered, checked against the version they were
              last shown.
            </p>
          </div>
          {project.can_edit && (
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" onClick={() => setUploadingFor({ po: null })}>
                <Upload className="size-4" aria-hidden />
                Upload a PO document
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setCreating(true)}
              >
                <Plus className="size-4" aria-hidden />
                Record a PO
              </Button>
            </div>
          )}
        </CardHeader>

        <CardContent className="space-y-3">
          {rows.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline" className="gap-1">
                <ReceiptText className="size-3" aria-hidden />
                {`${rows.length} PO${rows.length === 1 ? '' : 's'}, ${formatMyr(String(totalValue))}`}
              </Badge>
              {flagged > 0 && (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="size-3" aria-hidden />
                  {`${flagged} with something to check`}
                </Badge>
              )}
            </div>
          )}

          {purchaseOrders.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : purchaseOrders.isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
              <h3 className="text-sm font-semibold text-destructive">
                Purchase orders could not be loaded
              </h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {purchaseOrders.error instanceof Error
                  ? purchaseOrders.error.message
                  : 'Try again shortly.'}
              </p>
            </div>
          ) : rows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
              <h3 className="text-sm font-semibold">No PO received yet</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Recording the first PO moves this project to PO Received. Once a PO exists
                the project can be archived but not deleted.
              </p>
              {project.can_edit && (
                <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                  <Button type="button" onClick={() => setUploadingFor({ po: null })}>
                    <Upload className="size-4" aria-hidden />
                    Upload the PO document
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setCreating(true)}>
                    <Plus className="size-4" aria-hidden />
                    Record it by hand
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <ul className="space-y-2">
              {rows.map((po) => (
                <li key={po.id} className="rounded-lg border border-border">
                  <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-start sm:gap-3">
                    <button
                      type="button"
                      onClick={() =>
                        setOpenId((previous) => (previous === po.id ? null : po.id))
                      }
                      aria-expanded={openId === po.id}
                      className="min-w-0 flex-1 text-left"
                    >
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate text-sm font-medium" title={po.po_number}>
                          {po.po_number}
                        </span>
                        <Badge variant="outline" className="text-[11px]">
                          {SOURCE_LABELS[po.po_source] ?? po.po_source}
                        </Badge>
                        {po.model_mismatch_count > 0 && (
                          <Badge variant="destructive" className="text-[11px]">
                            {`${po.model_mismatch_count} not quoted`}
                          </Badge>
                        )}
                        {po.price_mismatch_count > 0 && (
                          <Badge variant="destructive" className="text-[11px]">
                            {`${po.price_mismatch_count} price differs`}
                          </Badge>
                        )}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">
                          {formatMyr(po.line_total)}
                        </span>
                        {po.issuing_party_name && <span>{po.issuing_party_name}</span>}
                        {po.po_date && <span>{formatDateInMalaysia(po.po_date)}</span>}
                        {po.scope_label && (
                          <span>
                            Against {po.scope_label}
                            {po.version_no ? ` v${po.version_no}` : ''}
                          </span>
                        )}
                        {po.drift_percent && Number(po.drift_percent) !== 0 && (
                          <span className="flex items-center gap-1">
                            <TrendingDown className="size-3" aria-hidden />
                            {describeDrift(po)}
                          </span>
                        )}
                      </span>
                    </button>

                    {project.can_edit && (
                      <div className="flex shrink-0 gap-1">
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setUploadingFor({ po })}
                          aria-label={`Upload a document for ${po.po_number}`}
                        >
                          <Upload className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditing(po)}
                          aria-label={`Edit ${po.po_number}`}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleting(po)}
                          aria-label={`Delete ${po.po_number}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    )}
                  </div>

                  {openId === po.id && project.can_edit && (
                    <POToSalesOrderStep
                      projectId={project.id}
                      purchaseOrder={po}
                      readiness={{
                        poConfirmed: Boolean(po.po_confirmed),
                        scheduleConfirmed: Boolean(po.schedule_confirmed),
                      }}
                    />
                  )}
                  {openId === po.id && (
                    <div className="space-y-3 border-t border-border p-3">
                      <POIntakeVersionsStrip
                        projectId={project.id}
                        poId={po.id}
                        canEdit={Boolean(project.can_edit)}
                        onUpload={() => setUploadingFor({ po })}
                      />
                      <PurchaseOrderLinesEditor project={project} po={po} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {uploadingFor && (
        <POIntakeUploadDialog
          projectId={project.id}
          purchaseOrderId={uploadingFor.po?.id ?? null}
          purchaseOrderNumber={uploadingFor.po?.po_number ?? null}
          onDone={() => setUploadingFor(null)}
        />
      )}

      {(creating || editing) && (
        <PurchaseOrderDialog
          project={project}
          po={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Delete ${deleting.po_number} and its ${deleting.line_count} line${deleting.line_count === 1 ? '' : 's'}? This action cannot be undone. The project stays at PO Received, because it genuinely passed through it.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Purchase order deleted"
      />
    </>
  );
}

/** AC-F9a, as a sentence rather than a flag: erosion is expected, its size is the news. */
export function describeDrift(po: ProjectPurchaseOrder): string {
  if (!po.drift_percent || !po.v1_total) return '';
  const percent = Number(po.drift_percent);
  const direction = percent < 0 ? 'below' : 'above';
  return `${Math.abs(percent).toFixed(1)}% ${direction} v1 (${formatMyr(po.v1_total)})`;
}
