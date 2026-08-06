'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { AlertTriangle, ChevronRight, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
// valid_until is a DATE column: formatDateInMalaysia keeps the civil date
// stable regardless of the viewer's machine timezone.
import { formatDateInMalaysia } from '@/lib/helpers';
import { useBulkDeleteCertificates, useCertificates } from '../hooks/useCertificates';
import {
  EXPIRING_WITHIN_OPTIONS,
  NEEDS_REVIEW_OPTIONS,
  SCHEME_FILTER_OPTIONS,
  STATUS_FILTER_OPTIONS,
  STATUS_LABELS,
  VALIDITY_FILTER_ALL,
  VALIDITY_FILTER_ATTENTION,
  VALIDITY_FILTER_OPTIONS,
  VALIDITY_STATE_LABELS,
} from '../lib/certificateDisplay';
import type { Certificate } from '../types/certificate.types';
import CertificateFormDialog from './CertificateFormDialog';

/**
 * The list opens UNFILTERED. It used to default to "needs attention" + active
 * (FE-3), which made the row count disagree with the number of certification
 * files on file and gave no clue that rows were being withheld - the register
 * has to be countable at a glance before it can be triaged.
 * "Needs attention" is still one click away in the Filters popover.
 */
const DEFAULT_VALIDITY = VALIDITY_FILTER_ALL;
const DEFAULT_STATUS = 'all';

/** `attention` expands to the two states that need a human. */
function validityStateParam(filter: string): string | undefined {
  if (filter === VALIDITY_FILTER_ALL) return undefined;
  if (filter === VALIDITY_FILTER_ATTENTION) return 'expiring_soon,expired';
  return filter;
}

export default function CertificatesList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'valid_until', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [validityFilter, setValidityFilter] = useState<string>(DEFAULT_VALIDITY);
  const [expiringWithin, setExpiringWithin] = useState<string>('any');
  const [schemeFilter, setSchemeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>(DEFAULT_STATUS);
  const [needsReviewFilter, setNeedsReviewFilter] = useState<string>('any');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [formOpen, setFormOpen] = useState(false);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  const bulkDeleteMutation = useBulkDeleteCertificates();

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [validityFilter, expiringWithin, schemeFilter, statusFilter, needsReviewFilter, searchQuery]);

  const { data, isLoading, refetch, isFetching } = useCertificates({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    validity_state: validityStateParam(validityFilter),
    expiring_within_days: expiringWithin !== 'any' ? Number(expiringWithin) : undefined,
    scheme: schemeFilter !== 'all' ? schemeFilter : undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    needs_review: needsReviewFilter === 'true' ? true : undefined,
  });

  // Counted against "unfiltered", which is now also the default - so the badge
  // reads 0 on arrival and any non-zero count means the user narrowed the list
  // themselves.
  const activeFilterCount =
    (validityFilter !== VALIDITY_FILTER_ALL ? 1 : 0) +
    (expiringWithin !== 'any' ? 1 : 0) +
    (schemeFilter !== 'all' ? 1 : 0) +
    (statusFilter !== 'all' ? 1 : 0) +
    (needsReviewFilter !== 'any' ? 1 : 0);

  const clearFilters = () => {
    setValidityFilter(VALIDITY_FILTER_ALL);
    setExpiringWithin('any');
    setSchemeFilter('all');
    setStatusFilter('all');
    setNeedsReviewFilter('any');
  };

  const columns = useMemo<ColumnDef<Certificate>[]>(
    () => [
      buildSelectColumn<Certificate>(),
      {
        accessorKey: 'scheme',
        header: ({ column }) => <DataGridColumnHeader title="Scheme" column={column} />,
        cell: ({ row }) => (
          <div className="truncate" title={row.original.scheme}>
            {row.original.scheme}
          </div>
        ),
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Scheme', skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        accessorKey: 'certificate_number',
        header: ({ column }) => <DataGridColumnHeader title="Number" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.certificate_number}>
            {row.original.certificate_number}
          </div>
        ),
        size: 180,
        minSize: 120,
        meta: { headerTitle: 'Number', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'certifying_body',
        header: ({ column }) => <DataGridColumnHeader title="Certifying Body" column={column} />,
        cell: ({ row }) => (
          <div className="truncate" title={row.original.certifying_body}>
            {row.original.certifying_body}
          </div>
        ),
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Certifying Body', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'covered_product_count',
        header: ({ column }) => <DataGridColumnHeader title="Covered Products" column={column} />,
        cell: ({ row }) => {
          const count = row.original.covered_product_count;
          if (count === 0) {
            return <span className="text-muted-foreground">None</span>;
          }
          return <span>{count}</span>;
        },
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Covered Products', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        accessorKey: 'valid_until',
        header: ({ column }) => <DataGridColumnHeader title="Valid Until" column={column} />,
        cell: ({ row }) => {
          const validUntil = row.original.valid_until;
          if (!validUntil) return <span className="text-muted-foreground">Not recorded</span>;
          return (
            <div className="truncate" title={formatDateInMalaysia(validUntil)}>
              {formatDateInMalaysia(validUntil)}
            </div>
          );
        },
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Valid Until', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'validity_state',
        header: ({ column }) => <DataGridColumnHeader title="Validity" column={column} />,
        cell: ({ row }) => {
          const state = row.original.validity_state;
          const days = row.original.days_until_expiry;
          const label = VALIDITY_STATE_LABELS[state];
          const suffix =
            state === 'expiring_soon' && days != null
              ? `${days} day${days === 1 ? '' : 's'} left`
              : state === 'expired' && days != null
                ? `${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} ago`
                : null;
          return (
            <div className="flex flex-col gap-0.5">
              <span className={`${STATUS_PILL_BASE} w-fit ${statusPillClass(state)}`}>{label}</span>
              {suffix && <span className="text-xs text-muted-foreground">{suffix}</span>}
            </div>
          );
        },
        size: 150,
        minSize: 120,
        enableSorting: false,
        meta: { headerTitle: 'Validity', skeleton: <Skeleton className="h-5 w-20" /> },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.status)}`}>
            {STATUS_LABELS[row.original.status]}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        accessorKey: 'needs_review',
        header: ({ column }) => <DataGridColumnHeader title="Review" column={column} />,
        cell: ({ row }) =>
          row.original.needs_review ? (
            <Badge variant="warning" appearance="light" size="sm">
              <AlertTriangle className="size-3" />
              Needs review
            </Badge>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 140,
        minSize: 110,
        enableSorting: false,
        meta: { headerTitle: 'Review', skeleton: <Skeleton className="h-5 w-24" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const selectedCount = selectedRowIds(table).length;

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={(row: Certificate) => router.push(`/master-data-management/certificates/${row.id}`)}
      standardToolbar={false}
      // Column preferences are keyed on the RBAC view slug, not the route path:
      // the column-config endpoint authorizes by treating everything before `::`
      // as a permission slug, and a pathname is not one.
      listingKey="master_data.certificates.view"
      tableLayout={{ width: 'fixed', columnsVisibility: true, columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search by number..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            filters={{
              kind: 'custom',
              active: activeFilterCount > 0,
              activeCount: activeFilterCount,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Validity</Label>
                    <SearchableSelect
                      value={validityFilter}
                      onChange={setValidityFilter}
                      options={VALIDITY_FILTER_OPTIONS}
                      placeholder="Validity"
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Expiring within</Label>
                    <SearchableSelect
                      value={expiringWithin}
                      onChange={setExpiringWithin}
                      options={EXPIRING_WITHIN_OPTIONS}
                      placeholder="Any expiry date"
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Scheme</Label>
                    <SearchableSelect
                      value={schemeFilter}
                      onChange={setSchemeFilter}
                      options={SCHEME_FILTER_OPTIONS}
                      placeholder="All schemes"
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Status</Label>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={setStatusFilter}
                      options={STATUS_FILTER_OPTIONS}
                      placeholder="All statuses"
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Review</Label>
                    <SearchableSelect
                      value={needsReviewFilter}
                      onChange={setNeedsReviewFilter}
                      options={NEEDS_REVIEW_OPTIONS}
                      placeholder="Reviewed and unreviewed"
                      triggerClassName="mt-1"
                    />
                  </div>
                  {activeFilterCount > 0 && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={clearFilters}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'certificates_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button onClick={() => setFormOpen(true)}>
                <Plus />
                Add Certificate
              </Button>
            }
            bulkActions={[
              {
                key: 'delete',
                label: 'Delete',
                icon: Trash2,
                destructive: true,
                onClick: () => setBulkDeleteOpen(true),
              },
            ]}
          />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      {/* Mounted only while open so the form state resets between openings. */}
      {formOpen && <CertificateFormDialog open={formOpen} onOpenChange={setFormOpen} />}

      <ConfirmDeleteDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title="Confirm delete"
        description={
          <>
            Delete {selectedCount} certificate{selectedCount === 1 ? '' : 's'}, including every
            revision and covered-product link. This action cannot be undone.
          </>
        }
        successMessage={`${selectedCount} certificate${selectedCount === 1 ? '' : 's'} deleted`}
        onDelete={async () => {
          await bulkDeleteMutation.mutateAsync(selectedRowIds(table));
        }}
        onSuccess={() => setRowSelection({})}
        queryKeysToInvalidate={[['certificates']]}
      />
    </DataGrid>
  );
}
