'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { AlertTriangle, ClipboardList, Hammer, Pencil, Trash2, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  useProjectSalesOrders,
  useSalesOrderBuild,
  useSalesOrderDelete,
} from '../../_shared/hooks/useProjectSalesOrders';
import type { Project } from '../../_shared/types/project.types';
import type { ProjectSalesOrderRow } from '../../_shared/types/projectSalesOrder.types';
import { formatMoney, sumMoney } from './SalesOrderMoney';
import { ReviewStatePill } from '../../_shared/components/ReviewStatePill';
import { GroupingOriginNote, SalesOrderStatusPill } from './SalesOrderStatusPill';
import { SalesOrderBuildDialog } from './SalesOrderBuildDialog';

/**
 * Sales orders (P7 and P11, contract sections 5 and 6).
 *
 * The list answers three questions in one pass: what the system proposed, what it refuses
 * to publish, and where each split came from. Grouping origin sits on every row because the
 * area split is a proposal: one real PO produced three sales orders, one of them an early
 * product subset with no area logic in it at all.
 */
export function SalesOrdersPanel({ project }: { project: Project }) {
  const router = useRouter();
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [building, setBuilding] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<ProjectSalesOrderRow | null>(null);

  const params = React.useMemo(
    () => ({ page: pagination.pageIndex + 1, limit: pagination.pageSize }),
    [pagination.pageIndex, pagination.pageSize],
  );
  const salesOrders = useProjectSalesOrders(project.id, params);
  const build = useSalesOrderBuild(project.id);
  const removeOrder = useSalesOrderDelete(project.id);

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
            {row.original.created_at ? formatDateInMalaysia(row.original.created_at) : '—'}
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
                      disabled={published}
                      aria-label={`Delete ${row.original.autocount_doc_no || row.original.provisional_ref}`}
                      title={
                        published
                          ? 'Published orders are amended, not deleted'
                          : 'Delete this draft'
                      }
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
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={salesOrders.isLoading}
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
              <ScrollArea>
                <DataGridTable />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            )}
          </CardTable>

          {total > 0 && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>

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
