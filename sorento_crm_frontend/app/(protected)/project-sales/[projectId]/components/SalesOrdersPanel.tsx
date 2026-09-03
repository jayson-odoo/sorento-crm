'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  AlertTriangle,
  ClipboardList,
  Hammer,
  Pencil,
  Trash2,
  TriangleAlert,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  buildSelectColumn,
  selectedRowIds,
} from '@/components/ui/data-grid-select-column';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  useProjectSalesOrders,
  useSalesOrderBuild,
  useSalesOrderBulkDelete,
  useSalesOrderDelete,
} from '../../_shared/hooks/useProjectSalesOrders';
import type { Project } from '../../_shared/types/project.types';
import type { ProjectSalesOrderRow } from '../../_shared/types/projectSalesOrder.types';
import { formatMoney, sumMoney } from './SalesOrderMoney';
import { ReviewStatePill } from '../../_shared/components/ReviewStatePill';
import { GroupingOriginNote, SalesOrderStatusPill } from './SalesOrderStatusPill';
import { SalesOrderBuildDialog } from './SalesOrderBuildDialog';

/**
 * Why one drafted sales order cannot be deleted, or undefined when it can.
 *
 * The SERVER owns this rule and refuses on four separate facts (published or amended, linked
 * to an AutoCount document, carrying a published amendment, supply confirmed). The list row
 * only carries the first two, so this pre-empts those and the other two come back as the
 * bulk call's 409, whose message names each order to un-tick. Deliberately NOT a guess at the
 * two it cannot see: a row wrongly greyed out is worse than one the server refuses with a
 * reason.
 *
 * One function, three readers - the row's Delete button, its selection checkbox, and the
 * count in the bulk strip - so a row can never be tickable and undeletable at the same time.
 */
export function salesOrderDeleteRefusal(
  row: ProjectSalesOrderRow,
): string | undefined {
  if (row.status === 'published' || row.status === 'amended') {
    return 'Published orders are amended, not deleted';
  }
  if (row.autocount_doc_no) {
    return `In AutoCount as ${row.autocount_doc_no}, so it is amended, not deleted`;
  }
  return undefined;
}

/**
 * Sales orders (P7 and P11, contract sections 5 and 6).
 *
 * The list answers three questions in one pass: what the system proposed, what it refuses
 * to publish, and where each split came from. Grouping origin sits on every row because the
 * area split is a proposal: one real PO produced three sales orders, one of them an early
 * product subset with no area logic in it at all.
 *
 * It is also where a bad BUILD is undone. Building is idempotent per (PO version, schedule
 * version), so a batch cut on the wrong key produces a dozen drafts that all have to go
 * before it can be run again - which is why the rows tick and the delete is one call rather
 * than twelve.
 */
export function SalesOrdersPanel({ project }: { project: Project }) {
  const router = useRouter();
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [building, setBuilding] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<ProjectSalesOrderRow | null>(null);
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const [confirmBulkDelete, setConfirmBulkDelete] = React.useState(false);

  const params = React.useMemo(
    () => ({ page: pagination.pageIndex + 1, limit: pagination.pageSize }),
    [pagination.pageIndex, pagination.pageSize],
  );
  const salesOrders = useProjectSalesOrders(project.id, params);
  const build = useSalesOrderBuild(project.id);
  const removeOrder = useSalesOrderDelete(project.id);
  const removeSelected = useSalesOrderBulkDelete(project.id);

  const rows = React.useMemo(() => salesOrders.data?.data ?? [], [salesOrders.data]);
  const total = salesOrders.data?.total ?? 0;

  // Summed as decimal strings: 99 line values added as floats drift, and this figure is
  // read next to the printed sales order.
  const committedValue = React.useMemo(
    () => sumMoney(rows.map((row) => row.total_amount)),
    [rows],
  );
  const blockedCount = rows.filter((row) => row.hard_findings > 0).length;

  const columns = React.useMemo<ColumnDef<ProjectSalesOrderRow>[]>(
    () => [
      // The shared selection column, never a hand-rolled Set: it binds to react-table's own
      // `rowSelection` so the ids read out of it here are the ids the grid thinks are ticked.
      // Only for someone who may edit - a reader has nothing to do with a selection.
      ...(project.can_edit
        ? [
            buildSelectColumn<ProjectSalesOrderRow>({
              enableRow: (row) => salesOrderDeleteRefusal(row.original) === undefined,
              disabledReason: (row) => salesOrderDeleteRefusal(row.original),
              rowLabel: (row) =>
                `Select ${row.original.autocount_doc_no || row.original.provisional_ref}`,
            }),
          ]
        : []),
      {
        accessorKey: 'provisional_ref',
        header: ({ column }) => <DataGridColumnHeader title="Reference" column={column} />,
        cell: ({ row }) => {
          const reference = row.original.autocount_doc_no || row.original.provisional_ref;
          return (
            <div className="min-w-0">
              <span className="block truncate font-medium" title={reference}>
                {reference}
              </span>
              <span className="flex flex-wrap gap-1">
                {row.original.is_pre_order && (
                  <Badge variant="secondary" appearance="light" size="sm">
                    Pre-order
                  </Badge>
                )}
                {row.original.is_sponsorship && (
                  <Badge variant="secondary" appearance="light" size="sm">
                    Sponsorship
                  </Badge>
                )}
              </span>
            </div>
          );
        },
        size: 170,
        minSize: 130,
        meta: { headerTitle: 'Reference', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'area_group',
        header: ({ column }) => <DataGridColumnHeader title="Area group" column={column} />,
        cell: ({ row }) => {
          const area = row.original.area_group || 'No area';
          return (
            <div className="min-w-0">
              <span className="block truncate" title={area}>
                {area}
              </span>
              <GroupingOriginNote origin={row.original.grouping_origin} />
            </div>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Area group', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        // The review state sits under the status rather than in a column of its own: it is
        // absent on every order that has not been published, and an empty column reads as a
        // broken one. Renders nothing until the backend derives it.
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col items-start gap-1">
            <SalesOrderStatusPill status={row.original.status} />
            {/* No exception count here: the count is the fulfilment planning worklist's
                instruction, and it does not fit beside a status in this grid. */}
            <ReviewStatePill state={row.original.review_state} />
          </div>
        ),
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'findings',
        header: ({ column }) => <DataGridColumnHeader title="To review" column={column} />,
        cell: ({ row }) => {
          const { hard_findings: hard, warn_findings: warn } = row.original;
          if (hard === 0 && warn === 0) {
            return <span className="text-muted-foreground">Nothing flagged</span>;
          }
          return (
            <span className="flex flex-wrap gap-1">
              {hard > 0 && (
                <Badge variant="destructive" appearance="light" size="sm">
                  {`${hard} blocking`}
                </Badge>
              )}
              {warn > 0 && (
                <Badge variant="warning" appearance="light" size="sm">
                  {`${warn} warning${warn === 1 ? '' : 's'}`}
                </Badge>
              )}
            </span>
          );
        },
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'To review', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.line_count.toLocaleString()}</span>
        ),
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Lines', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        accessorKey: 'total_amount',
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        cell: ({ row }) => {
          const value = formatMoney(row.original.total_amount);
          return (
            <span className="block truncate tabular-nums" title={value}>
              {value}
            </span>
          );
        },
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Value', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="Customer PO" column={column} />,
        cell: ({ row }) => {
          const value = row.original.po_number || '-';
          return (
            <span className="block truncate" title={value}>
              {value}
            </span>
          );
        },
        size: 160,
        minSize: 120,
        meta: { headerTitle: 'Customer PO', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Billed to" column={column} />,
        cell: ({ row }) => {
          const value = row.original.customer_name || '-';
          return (
            <span className="block truncate" title={value}>
              {value}
            </span>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Billed to', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Drafted" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {row.original.created_at ? formatDateInMalaysia(row.original.created_at) : '-'}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Drafted', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      // Deleting a draft is what makes building one repeatable: the build is idempotent per
      // (PO version, schedule version), so a draft that came out wrong is removed here and
      // built again from the toolbar. Only on a draft - a published order is in AutoCount and
      // is amended, never deleted - and the button says so rather than vanishing.
      ...(project.can_edit
        ? [
            {
              id: 'actions',
              header: '',
              cell: ({ row }: { row: { original: ProjectSalesOrderRow } }) => {
                const published =
                  row.original.status === 'published' || row.original.status === 'amended';
                // The SAME rule the checkbox beside it obeys, so a row can never be tickable
                // and undeletable at once.
                const refusal = salesOrderDeleteRefusal(row.original);
                const reference =
                  row.original.autocount_doc_no || row.original.provisional_ref;
                return (
                  <div className="flex justify-end">
                    {/* Edit is the order's own PAGE in edit mode, not a modal collecting the
                        same fields a second time. One editing surface per record, and it is the
                        one the reader already knows the layout of - the same move the customer
                        PO list makes. */}
                    <Button
                      type="button"
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      disabled={published}
                      aria-label={`Edit ${reference}`}
                      title={
                        published
                          ? 'Published orders are amended, not edited'
                          : 'Correct this draft'
                      }
                      onClick={(event) => {
                        event.stopPropagation();
                        router.push(
                          `/project-sales/${project.id}/sales-orders/${row.original.id}?edit=1`,
                        );
                      }}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      type="button"
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      disabled={Boolean(refusal)}
                      aria-label={`Delete ${reference}`}
                      title={refusal ?? 'Delete this draft'}
                      onClick={(event) => {
                        // The row itself navigates to the order. Without this the dialog and
                        // the detail page would both open on one click.
                        event.stopPropagation();
                        setPendingDelete(row.original);
                      }}
                    >
                      <Trash2 className="size-3.5 text-destructive" />
                    </Button>
                  </div>
                );
              },
              size: 100,
              minSize: 84,
              enableResizing: false,
              meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-4 w-4" /> },
            } as ColumnDef<ProjectSalesOrderRow>,
          ]
        : []),
    ],
    [project.can_edit, project.id, router],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize) || 0,
    getRowId: (row) => row.id,
    state: { pagination, rowSelection },
    /**
     * The gate is HERE, on the table, and the same predicate is handed to the column above.
     *
     * Both, and it is not belt-and-braces: `row.getCanSelect()` - which is what greys the box
     * out - reads this TABLE option, while the column's copy is what the cell renders from.
     * The two existing callers of `buildSelectColumn` (the spec proposal review and the flyer
     * dimension review) pass the pair the same way.
     */
    enableRowSelection: (row) => salesOrderDeleteRefusal(row.original) === undefined,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
  });

  // Read off the TABLE, not off `rowSelection`, so a row that has since left the page (a
  // refetch, a page change) cannot leave its id behind in the request.
  const selectedIds = selectedRowIds(table);

  return (
    <>
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={salesOrders.isLoading}
        isPlaceholderData={salesOrders.isPlaceholderData}
        listingKey="projects.projects.view::project-sales-orders"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(row) =>
          router.push(`/project-sales/${project.id}/sales-orders/${row.id}`)
        }
      >
        <Card>
          <CardHeader className="block space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 break-words">
                <p className="text-sm font-medium">Sales orders</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {/* Publishing raises the order inquiry, so the way to what purchasing
                    was told sits beside the thing that told them. */}
                <Button asChild variant="outline" size="sm">
                  <Link href={`/project-sales/${project.id}/order-inquiries`}>
                    <ClipboardList className="size-4" aria-hidden />
                    Order inquiry
                  </Link>
                </Button>
                {project.can_edit && (
                  <Button type="button" size="sm" onClick={() => setBuilding(true)}>
                    <Hammer className="size-4" aria-hidden />
                    Build drafts
                  </Button>
                )}
              </div>
            </div>

            {/* The bulk strip, in the toolbar's own grammar: a count badge, the destructive
                action, then Clear. It REPLACES the counts row rather than appearing under it,
                so the header states one thing at a time - what the list holds, or what is
                selected. */}
            {selectedIds.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="h-8 gap-1 px-2.5 text-sm">
                  {`${selectedIds.length} selected`}
                </Badge>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5 text-destructive hover:text-destructive"
                  disabled={removeSelected.isPending}
                  onClick={() => setConfirmBulkDelete(true)}
                >
                  <Trash2 className="size-4" aria-hidden />
                  {`Delete ${selectedIds.length} sales order${
                    selectedIds.length === 1 ? '' : 's'
                  }`}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="gap-1.5 text-muted-foreground"
                  onClick={() => setRowSelection({})}
                >
                  <X className="size-4" aria-hidden />
                  Clear
                </Button>
              </div>
            ) : (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline">
                {`${total.toLocaleString()} sales order${total === 1 ? '' : 's'}`}
              </Badge>
              {rows.length > 0 && (
                <Badge variant="outline">{`${formatMoney(committedValue)} on this page`}</Badge>
              )}
              {blockedCount > 0 && (
                <Badge variant="destructive" appearance="light" className="gap-1">
                  <TriangleAlert className="size-3" aria-hidden />
                  {`${blockedCount} cannot publish yet`}
                </Badge>
              )}
            </div>
            )}
          </CardHeader>

          <CardTable>
            {salesOrders.isError ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  Sales orders could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {salesOrders.error instanceof Error
                    ? salesOrders.error.message
                    : 'Try again shortly.'}
                </p>
              </div>
            ) : !salesOrders.isLoading && total === 0 ? (
              <div className="px-6 py-10 text-center">
                <AlertTriangle
                  className="mx-auto size-5 text-muted-foreground"
                  aria-hidden
                />
                {/* One way in, in the toolbar (ADR 1d). The centred duplicate is gone. */}
                <h3 className="mt-2 text-sm font-semibold">No sales order drafted yet</h3>
              </div>
            ) : (
              <DataGridTable />
            )}
          </CardTable>

          {total > 0 && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>

      {/* The bulk confirmation. It names the COUNT, because that is the only thing the
          reviewer can check before pressing it - thirteen references would not fit and would
          not be read - and it says what survives, since the whole point of deleting a batch
          is to build it again. */}
      <ConfirmDeleteDialog
        open={confirmBulkDelete}
        onOpenChange={setConfirmBulkDelete}
        title="Confirm delete"
        description={
          selectedIds.length === 1
            ? 'Delete 1 sales order and its lines? This action cannot be undone. The purchase order and its delivery schedule are untouched, so the draft can be built again.'
            : `Delete ${selectedIds.length} sales orders and their lines? This action cannot be undone. The purchase orders and their delivery schedules are untouched, so the drafts can be built again.`
        }
        onDelete={async () => {
          await removeSelected.mutateAsync(selectedIds);
        }}
        // Cleared only on success. A refusal leaves the selection exactly as it was, which is
        // what makes the server's "un-tick these two and retry" actionable.
        onSuccess={() => {
          setRowSelection({});
          setConfirmBulkDelete(false);
        }}
        successMessage={`${selectedIds.length} sales order${
          selectedIds.length === 1 ? '' : 's'
        } deleted`}
      />

      <ConfirmDeleteDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(next) => !next && setPendingDelete(null)}
        title="Confirm delete"
        description={
          pendingDelete
            ? `Delete ${pendingDelete.autocount_doc_no || pendingDelete.provisional_ref} and its ${
                pendingDelete.line_count
              } line${pendingDelete.line_count === 1 ? '' : 's'}? This action cannot be undone. The purchase order and its delivery schedule are untouched, so the drafts can be built again.`
            : ''
        }
        onDelete={async () => {
          if (!pendingDelete) return;
          await removeOrder.mutateAsync(pendingDelete.id);
        }}
        onSuccess={() => setPendingDelete(null)}
        successMessage="Sales order deleted"
      />

      {building && (
        <SalesOrderBuildDialog
          projectId={project.id}
          onDone={() => setBuilding(false)}
          building={build.isPending}
          onBuild={(input) => build.mutateAsync(input)}
        />
      )}
    </>
  );
}
