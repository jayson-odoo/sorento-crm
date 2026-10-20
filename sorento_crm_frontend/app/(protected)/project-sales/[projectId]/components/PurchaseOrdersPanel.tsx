'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef, ExpandedState } from '@tanstack/react-table';
import {
  ChevronDown,
  ChevronRight,
  Columns3,
  Pencil,
  Plus,
  Trash2,
  TrendingDown,
  Upload,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { toast } from '@/lib/toast';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  usePurchaseOrderMutations,
  usePurchaseOrders,
} from '../../_shared/hooks/useProjects';
import type { Project, ProjectPurchaseOrder } from '../../_shared/types/project.types';
import { useDeliverySchedules } from '../../_shared/hooks/useDeliverySchedules';
import { useProjectSalesOrders } from '../../_shared/hooks/useProjectSalesOrders';
import type { ProjectSalesOrderRow } from '../../_shared/types/projectSalesOrder.types';
import type { DeliverySchedule } from '../../_shared/types/deliverySchedule.types';
import { DeliveryScheduleUploadDialog } from './DeliveryScheduleUploadDialog';
import { formatUnits } from './POLinesProgressGrid';
import { formatMyr } from './QuotationsPanel';
import { PurchaseOrderDialog } from './PurchaseOrderDialog';
import { POIntakeUploadDialog } from './POIntakeUploadDialog';
import { projectTabOriginHref } from '../../_shared/lib/reviewOrigin';

/** Shared with the PO detail page, so a source reads the same in the list and on the record. */
export const SOURCE_LABELS: Record<string, string> = {
  contractor_direct: 'Contractor direct',
  trading_house: 'Trading house',
};

/** What this PO still needs, from the list row and its sales orders (no extra request). */
export function describeNextStep(
  po: ProjectPurchaseOrder,
  orders: ProjectSalesOrderRow[] = [],
): string {
  if (po.has_document && !po.po_confirmed) return 'Confirm PO';
  if (!po.has_document && po.line_count === 0) return 'Add the lines';
  if (!po.schedule_confirmed) return 'Add or confirm the schedule';
  if (orders.length === 0) return 'Build sales orders';
  const unpublished = orders.filter(
    (order) => !['published', 'amended', 'adopted'].includes(order.status),
  ).length;
  if (unpublished > 0) return `Publish ${unpublished} sales order${unpublished === 1 ? '' : 's'}`;
  return 'Sales orders out';
}

/**
 * The project's Orders tab (PM-SIMPLIFY AC-O1, AC-O2): one row per customer PO. A row
 * expands to its schedule and its sales orders; right-click for the row's actions; the PO
 * number opens the PO's own page, where everything about it lives.
 *
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
  const router = useRouter();
  const purchaseOrders = usePurchaseOrders(project.id);
  const { remove } = usePurchaseOrderMutations(project.id);

  const [creating, setCreating] = React.useState(false);
  const [deleting, setDeleting] = React.useState<ProjectPurchaseOrder | null>(null);
  // A `po` of null means "a PO we have no row for yet"; a PO means "another version of this
  // one", which is how a re-scanned PO stays one commitment instead of becoming two.
  const [uploadingFor, setUploadingFor] = React.useState<{
    po: ProjectPurchaseOrder | null;
  } | null>(null);
  const [scheduleFor, setScheduleFor] = React.useState<ProjectPurchaseOrder | null>(null);
  const [expanded, setExpanded] = React.useState<ExpandedState>({});
  const [menuPo, setMenuPo] = React.useState<ProjectPurchaseOrder | null>(null);
  const schedules = useDeliverySchedules(project.id);
  const salesOrders = useProjectSalesOrders(project.id, { page: 1, limit: 1000 });

  const rows = React.useMemo(() => purchaseOrders.data ?? [], [purchaseOrders.data]);
  const schedulesByPo = React.useMemo(() => {
    const out = new Map<string, DeliverySchedule[]>();
    for (const schedule of schedules.data ?? []) {
      out.set(schedule.purchase_order_id, [...(out.get(schedule.purchase_order_id) ?? []), schedule]);
    }
    return out;
  }, [schedules.data]);
  const ordersByPo = React.useMemo(() => {
    const out = new Map<string, ProjectSalesOrderRow[]>();
    for (const order of salesOrders.data?.data ?? []) {
      if (!order.purchase_order_id) continue;
      out.set(order.purchase_order_id, [...(out.get(order.purchase_order_id) ?? []), order]);
    }
    return out;
  }, [salesOrders.data]);

  const columns = React.useMemo<ColumnDef<ProjectPurchaseOrder>[]>(
    () => [
      {
        id: 'expand',
        header: () => <span className="sr-only">Schedule and sales orders</span>,
        cell: ({ row }) => (
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            className="size-6"
            onClick={(event) => {
              event.stopPropagation();
              row.toggleExpanded();
            }}
            aria-label={
              row.getIsExpanded()
                ? `Hide the schedule and sales orders of ${row.original.po_number}`
                : `Show the schedule and sales orders of ${row.original.po_number}`
            }
          >
            {row.getIsExpanded() ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </Button>
        ),
        size: 44,
        enableHiding: false,
        enableResizing: false,
        meta: {
          headerTitle: 'Schedule and sales orders',
          expandedContent: (po: ProjectPurchaseOrder) => (
            <POExpansion
              schedules={schedulesByPo.get(po.id) ?? []}
              orders={ordersByPo.get(po.id) ?? []}
            />
          ),
        },
      },
      {
        id: 'po_number',
        accessorFn: (row) => row.po_number,
        header: ({ column }) => <DataGridColumnHeader title="PO number" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium" title={row.original.po_number}>
            {row.original.po_number}
          </span>
        ),
        // Labels the totals row in the table's own footer. Sits under the first column the
        // way a spreadsheet labels its sum, so the number under Value needs no caption.
        footer: () => <span className="text-muted-foreground">Total</span>,
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
        /**
         * Summed from the rows the table currently holds, so a search narrows the total with
         * the list instead of leaving a project-wide figure under a filtered set.
         */
        footer: ({ table }) =>
          formatMyr(
            String(
              table
                .getCoreRowModel()
                .rows.reduce((sum, row) => sum + Number(row.original.line_total || 0), 0),
            ),
          ),
        size: 140,
        meta: { headerTitle: 'Value' },
      },
      {
        id: 'delivered',
        accessorFn: (row) => Number(row.delivered_units ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Delivered" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm tabular-nums">
            {`${formatUnits(row.original.delivered_units)} of ${formatUnits(row.original.ordered_units)}`}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Delivered' },
      },
      {
        id: 'next_delivery_date',
        accessorFn: (row) => row.next_delivery_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Next delivery" column={column} />,
        cell: ({ row }) =>
          row.original.next_delivery_date ? (
            <span className="truncate text-sm">
              {formatDateInMalaysia(row.original.next_delivery_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Next delivery' },
      },
      {
        id: 'next_step',
        accessorFn: (row) => describeNextStep(row, ordersByPo.get(row.id)),
        header: ({ column }) => <DataGridColumnHeader title="Next step" column={column} />,
        cell: ({ row }) => (
          <span
            className="truncate text-sm"
            title={describeNextStep(row.original, ordersByPo.get(row.original.id))}
          >
            {describeNextStep(row.original, ordersByPo.get(row.original.id))}
          </span>
        ),
        size: 200,
        meta: { headerTitle: 'Next step' },
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
                  {/* Edit is the PO's own PAGE in edit mode, not a modal that collects the
                      same fields a second time. One editing surface per record, and it is the
                      one the reader already knows the layout of. */}
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      router.push(`/project-sales/${project.id}/pos/${row.original.id}?edit=1`)
                    }
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
    [ordersByPo, project.can_edit, project.id, router, schedulesByPo],
  );

  const openPo = (po: ProjectPurchaseOrder) => router.push(`/project-sales/${project.id}/pos/${po.id}`);

  return (
    <>
      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <div
            // Capture phase: a right-click outside a PO row stops here, so the browser's own
            // menu shows instead of an empty one.
            onContextMenuCapture={(event) => {
              const rowEl = (event.target as Element).closest('[data-po-id]');
              const po = rows.find((row) => row.id === rowEl?.getAttribute('data-po-id'));
              if (!po) {
                event.stopPropagation();
                return;
              }
              setMenuPo(po);
            }}
          >
      <PanelDataGrid
        title="Purchase orders"
        // The total is a footer row INSIDE the table now, under the Value column it sums, and
        // the count comes from the standard pagination bar ("1 - 1 of 1"). "N with something to
        // check" is gone outright: it named no PO and led nowhere, and the To check COLUMN
        // already says which row and what about it.
        toolbar={({ table }) => (
          <>
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1.5">
                  <Columns3 className="size-4" aria-hidden />
                  Columns
                </Button>
              }
            />
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
        )}
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        listingKey="projects.projects.view::project-purchase-orders"
        isLoading={purchaseOrders.isLoading}
        error={purchaseOrders.isError ? purchaseOrders.error : undefined}
        emptyTitle="No PO received yet"
        searchPlaceholder="Search POs"
        searchOf={(row) =>
          [row.po_number, row.issuing_party_name, row.scope_label, row.po_source]
            .filter(Boolean)
            .join(' ')
        }
        // The row is the way in, and it goes to the PO's own page. The documents, the
        // readiness step and ninety lines do not belong under a list.
        onRowClick={openPo}
        rowAttributes={(row) => ({ 'data-po-id': row.id })}
        expanded={expanded}
        onExpandedChange={setExpanded}
        initialColumnVisibility={{ po_source: false, scope: false }}
      />
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="w-56">
          {menuPo && (
            <>
              <ContextMenuItem onSelect={() => openPo(menuPo)}>Open purchase order</ContextMenuItem>
              {project.can_edit && (
                <>
                  <ContextMenuItem onSelect={() => setScheduleFor(menuPo)}>
                    Upload delivery schedule
                  </ContextMenuItem>
                  <ContextMenuItem onSelect={() => setUploadingFor({ po: menuPo })}>
                    Upload a new PO version
                  </ContextMenuItem>
                </>
              )}
              <ContextMenuSeparator />
              <ContextMenuItem
                onSelect={() => {
                  void navigator.clipboard
                    ?.writeText(menuPo.po_number)
                    .then(() => toast.success(`${menuPo.po_number} copied`));
                }}
              >
                Copy PO number
              </ContextMenuItem>
            </>
          )}
        </ContextMenuContent>
      </ContextMenu>

      {scheduleFor && (
        <DeliveryScheduleUploadDialog
          project={project}
          purchaseOrder={scheduleFor}
          onDone={() => setScheduleFor(null)}
          originHref={`/project-sales/${project.id}/pos/${scheduleFor.id}?tab=deliveries`}
        />
      )}


      {uploadingFor && (
        <POIntakeUploadDialog
          projectId={project.id}
          purchaseOrderId={uploadingFor.po?.id ?? null}
          purchaseOrderNumber={uploadingFor.po?.po_number ?? null}
          onDone={() => setUploadingFor(null)}
          originHref={projectTabOriginHref(project.id, 'orders')}
        />
      )}

      {creating && (
        <PurchaseOrderDialog project={project} onDone={() => setCreating(false)} />
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

/** The expanded row: the PO's latest schedule and its sales orders, by status. */
function POExpansion({
  schedules,
  orders,
}: {
  schedules: DeliverySchedule[];
  orders: ProjectSalesOrderRow[];
}) {
  const latest = [...schedules].sort((a, b) =>
    (b.created_at ?? '').localeCompare(a.created_at ?? ''),
  )[0];
  const live = orders.filter((order) =>
    ['published', 'amended', 'adopted'].includes(order.status),
  ).length;
  const refs = orders.map((order) => order.autocount_doc_no || order.provisional_ref).sort();
  return (
    <dl className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-2">
      <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">Delivery schedule</dt>
        <dd className="break-words">
          {latest ? (
            <>
              {latest.latest_revision_label ?? `Version ${latest.latest_version_no ?? 1}`}
              {latest.schedule_date ? ` · dated ${formatDateInMalaysia(latest.schedule_date)}` : ''}
              {' · '}
              {latest.confirmed_at ? 'confirmed' : 'not confirmed yet'}
            </>
          ) : (
            <span className="text-muted-foreground">None uploaded yet</span>
          )}
        </dd>
      </div>
      <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">Sales orders</dt>
        <dd className="break-words">
          {orders.length === 0 ? (
            <span className="text-muted-foreground">Not built yet</span>
          ) : (
            <>
              {refs.length > 2 ? `${refs[0]} to ${refs[refs.length - 1]}` : refs.join(', ')}
              {` · ${live} published, ${orders.length - live} not yet`}
            </>
          )}
        </dd>
      </div>
    </dl>
  );
}
