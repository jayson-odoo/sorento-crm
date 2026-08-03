'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
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
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
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

  const columns = React.useMemo<ColumnDef<ProjectPurchaseOrder>[]>(
    () => [
      {
        id: 'po_number',
        accessorFn: (row) => row.po_number,
        header: ({ column }) => <DataGridColumnHeader title="PO number" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium" title={row.original.po_number}>
            {row.original.po_number}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'PO number' },
      },
      {
        id: 'po_source',
        accessorFn: (row) => row.po_source,
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="light" className="text-[11px]">
            {SOURCE_LABELS[row.original.po_source] ?? row.original.po_source}
          </Badge>
        ),
        size: 140,
        meta: { headerTitle: 'Source' },
      },
      {
        id: 'line_total',
        accessorFn: (row) => Number(row.line_total || 0),
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium">
            {formatMyr(row.original.line_total)}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Value' },
      },
      {
        id: 'issuing_party_name',
        accessorFn: (row) => row.issuing_party_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Issued by" column={column} />,
        cell: ({ row }) =>
          row.original.issuing_party_name ? (
            <span className="truncate text-sm" title={row.original.issuing_party_name}>
              {row.original.issuing_party_name}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 190,
        meta: { headerTitle: 'Issued by' },
      },
      {
        id: 'po_date',
        accessorFn: (row) => row.po_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Dated" column={column} />,
        cell: ({ row }) =>
          row.original.po_date ? (
            <span className="truncate text-sm">
              {formatDateInMalaysia(row.original.po_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 120,
        meta: { headerTitle: 'Dated' },
      },
      {
        id: 'scope',
        accessorFn: (row) => row.scope_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Against" column={column} />,
        cell: ({ row }) =>
          row.original.scope_label ? (
            <span className="truncate text-sm">
              {row.original.scope_label}
              {row.original.version_no ? ` v${row.original.version_no}` : ''}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 170,
        meta: { headerTitle: 'Against' },
      },
      {
        id: 'checks',
        accessorFn: (row) => row.model_mismatch_count + row.price_mismatch_count,
        header: ({ column }) => <DataGridColumnHeader title="To check" column={column} />,
        cell: ({ row }) => {
          const parts: string[] = [];
          if (row.original.model_mismatch_count > 0) {
            parts.push(`${row.original.model_mismatch_count} not quoted`);
          }
          if (row.original.price_mismatch_count > 0) {
            parts.push(`${row.original.price_mismatch_count} price differs`);
          }
          if (parts.length === 0) return <span className="text-muted-foreground">-</span>;
          return (
            <Badge variant="destructive" appearance="light" className="truncate text-[11px]">
              {parts.join(', ')}
            </Badge>
          );
        },
        size: 190,
        meta: { headerTitle: 'To check' },
      },
      {
        id: 'drift',
        accessorFn: (row) => Number(row.drift_percent ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Drift from v1" column={column} />,
        cell: ({ row }) => {
          const described = describeDrift(row.original);
          return described ? (
            <span className="flex min-w-0 items-center gap-1 text-sm" title={described}>
              <TrendingDown className="size-3 shrink-0" aria-hidden />
              <span className="truncate">{described}</span>
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          );
        },
        size: 180,
        meta: { headerTitle: 'Drift from v1' },
      },
      ...(project.can_edit
        ? [
            {
              id: 'actions',
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }: { row: { original: ProjectPurchaseOrder } }) => (
                <div
                  className="flex justify-end gap-1"
                  // The row selects the PO; these are separate intents and must not also
                  // toggle the panel underneath.
                  onClick={(event) => event.stopPropagation()}
                >
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setUploadingFor({ po: row.original })}
                    aria-label={`Upload a document for ${row.original.po_number}`}
                  >
                    <Upload className="size-3.5" />
                  </Button>
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditing(row.original)}
                    aria-label={`Edit ${row.original.po_number}`}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleting(row.original)}
                    aria-label={`Delete ${row.original.po_number}`}
                  >
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                </div>
              ),
              size: 120,
              enableResizing: false,
              meta: { headerTitle: 'Actions' },
            } as ColumnDef<ProjectPurchaseOrder>,
          ]
        : []),
    ],
    [project.can_edit],
  );

  const open = rows.find((row) => row.id === openId) ?? null;

  return (
    <>
      <PanelDataGrid
        title="Purchase orders"
        toolbar={
          <>
            {rows.length > 0 && (
              <Badge variant="secondary" appearance="light" className="gap-1">
                <ReceiptText className="size-3" aria-hidden />
                {`${rows.length} PO${rows.length === 1 ? '' : 's'}, ${formatMyr(String(totalValue))}`}
              </Badge>
            )}
            {flagged > 0 && (
              <Badge variant="destructive" appearance="light" className="gap-1">
                <AlertTriangle className="size-3" aria-hidden />
                {`${flagged} with something to check`}
              </Badge>
            )}
            {project.can_edit && (
              <>
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
              </>
            )}
          </>
        }
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        listingKey="projects.projects.view::project-purchase-orders"
        isLoading={purchaseOrders.isLoading}
        error={purchaseOrders.isError ? purchaseOrders.error : undefined}
        emptyTitle="No PO received yet"
        // Selecting a row opens its lines below, rather than expanding inside the table:
        // a versions strip and a line editor cannot live inside a fixed-width cell.
        onRowClick={(row) => setOpenId((previous) => (previous === row.id ? null : row.id))}
      />

      {open && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{open.po_number}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {project.can_edit && (
              <POToSalesOrderStep
                projectId={project.id}
                purchaseOrder={open}
                readiness={{
                  poConfirmed: Boolean(open.po_confirmed),
                  scheduleConfirmed: Boolean(open.schedule_confirmed),
                }}
              />
            )}
            <POIntakeVersionsStrip
              projectId={project.id}
              poId={open.id}
              canEdit={Boolean(project.can_edit)}
              onUpload={() => setUploadingFor({ po: open })}
            />
            <PurchaseOrderLinesEditor project={project} po={open} />
          </CardContent>
        </Card>
      )}

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
