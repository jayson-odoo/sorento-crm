'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { CheckCheck, Unlink } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useDeferredBulkAction } from '@/hooks/useDeferredBulkAction';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { pendingEntityKey, usePendingEntityKeys } from '@/lib/pending-entity-store';

import { useCertificates } from '../hooks/useCertificates';
import {
  CERTIFICATE_LINKS_KEY,
  useCertificateLinks,
  useCheckCertificateLinks,
  useConfirmCertificateLinks,
} from '../hooks/useCertificateLinks';
import type { CertificateLink, CertificateLinkVerdict } from '../types/certificateLink.types';

/** CERT-LINK-CLEANUP card R1-R5: every certificate-product link, judged against the PDF's own text. */

export const VERDICT_LABELS: Record<CertificateLinkVerdict, string> = {
  found: 'Found',
  check: 'Check, number only',
  not_found: 'Not found',
  scanned: 'Scanned, cannot check',
  no_file: 'No file',
  pending: 'Checking',
};

const VERDICT_VARIANT: Record<CertificateLinkVerdict, 'success' | 'warning' | 'destructive' | 'secondary' | 'info'> = {
  found: 'success',
  check: 'warning',
  not_found: 'destructive',
  scanned: 'secondary',
  no_file: 'secondary',
  pending: 'info',
};

const VERDICT_ORDER: CertificateLinkVerdict[] = ['not_found', 'check', 'found', 'scanned', 'no_file', 'pending'];

/** Opens on what needs a person: AI links the text does not back up. */
export const DEFAULT_VERDICTS: CertificateLinkVerdict[] = ['not_found', 'check'];
export const DEFAULT_SOURCE = 'ai';

const SOURCE_OPTIONS = [
  { value: 'ai', label: 'AI' },
  { value: 'manual', label: 'Manual or confirmed' },
];

const POLL_MS = 5000;

function TextCell({ value, className }: { value: string | null | undefined; className?: string }) {
  if (!value) return <span className="text-muted-foreground">-</span>;
  return (
    <div className={`truncate ${className ?? ''}`} title={value}>
      {value}
    </div>
  );
}

export default function CertificateLinksList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [verdicts, setVerdicts] = useState<string[]>(DEFAULT_VERDICTS);
  const [source, setSource] = useState<string>(DEFAULT_SOURCE);
  const [certificateId, setCertificateId] = useState<string>('');
  const [certificateLabel, setCertificateLabel] = useState<string>('');
  const {
    value: searchInputValue,
    setValue: setSearchInputValue,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const certificateSearch = useDebouncedSearch();

  useResetPageOnFilterChange(setPagination, [verdicts, source, certificateId, searchQuery]);

  const [polling, setPolling] = useState(false);
  const { data, isLoading, isPlaceholderData, isFetching, error, refetch } = useCertificateLinks(
    {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      certificateId: certificateId || undefined,
      verdicts,
      source: source || undefined,
    },
    { refetchInterval: polling ? POLL_MS : false },
  );

  // Links not yet read against their current PDF: ask the worker once per visit, then poll
  // until the counts settle.
  const check = useCheckCertificateLinks();
  const asked = useRef(false);
  const pending = data?.summary?.pending ?? 0;
  useEffect(() => {
    if (pending > 0 && !asked.current) {
      asked.current = true;
      check.mutate();
      setPolling(true);
    }
    if (pending === 0 && polling) setPolling(false);
  }, [pending, polling, check]);

  const register = useCertificates({
    pageIndex: 0,
    pageSize: 50,
    sorting: [],
    searchQuery: certificateSearch.debouncedValue,
  });
  const certificateOptions = useMemo(() => {
    const options = (register.data?.data ?? []).map((c) => ({
      value: c.id,
      label: `${c.scheme} ${c.certificate_number}`,
    }));
    // The picked certificate keeps its label after the search moves on.
    if (certificateId && !options.some((o) => o.value === certificateId)) {
      options.unshift({ value: certificateId, label: certificateLabel });
    }
    return options;
  }, [register.data, certificateId, certificateLabel]);

  const summary = data?.summary;
  const verdictOptions = VERDICT_ORDER.map((v) => ({
    value: v,
    label: summary ? `${VERDICT_LABELS[v]} (${summary[v] ?? 0})` : VERDICT_LABELS[v],
  }));

  const pendingKeys = usePendingEntityKeys();
  const rowPending = (row: CertificateLink) => pendingKeys.has(pendingEntityKey('certificate_link', row.id));

  const removal = useDeferredBulkAction({
    actionKey: 'certificate_link.remove',
    entityType: 'certificate_link',
    verb: 'Removing',
    pastVerb: 'removed',
    describe: (count) => `${count} link${count === 1 ? '' : 's'}`,
    invalidateKeys: [[CERTIFICATE_LINKS_KEY], ['certificates']],
    onStarted: () => setRowSelection({}),
  });
  const confirm = useConfirmCertificateLinks();

  const columns = useMemo<ColumnDef<CertificateLink>[]>(
    () => [
      buildSelectColumn<CertificateLink>(),
      {
        id: 'certificate_number',
        accessorKey: 'certificate_number',
        header: ({ column }) => <DataGridColumnHeader title="Certificate" column={column} />,
        cell: ({ row }) => (
          <TextCell value={`${row.original.scheme} ${row.original.certificate_number}`} className="font-medium" />
        ),
        size: 190,
        minSize: 130,
        meta: { headerTitle: 'Certificate', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'certificate_type',
        accessorKey: 'certificate_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => <TextCell value={row.original.certificate_type} />,
        size: 140,
        minSize: 100,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'product_code',
        accessorKey: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product Code" column={column} />,
        cell: ({ row }) => <TextCell value={row.original.product_code} className="font-medium" />,
        size: 160,
        minSize: 110,
        meta: { headerTitle: 'Product Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'product_name',
        accessorKey: 'product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product Name" column={column} />,
        cell: ({ row }) => <TextCell value={row.original.product_name} />,
        size: 240,
        minSize: 140,
        meta: { headerTitle: 'Product Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'model_code',
        accessorKey: 'model_code',
        header: ({ column }) => <DataGridColumnHeader title="Code on Certificate" column={column} />,
        cell: ({ row }) => <TextCell value={row.original.model_code ?? row.original.check_code} />,
        size: 160,
        minSize: 110,
        meta: { headerTitle: 'Code on Certificate', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'source',
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => <span>{row.original.source === 'ai' ? 'AI' : 'Manual'}</span>,
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Source', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'verdict',
        accessorKey: 'verdict',
        header: ({ column }) => <DataGridColumnHeader title="On Certificate" column={column} />,
        cell: ({ row }) => (
          <Badge variant={VERDICT_VARIANT[row.original.verdict]} appearance="light" size="sm">
            {VERDICT_LABELS[row.original.verdict]}
          </Badge>
        ),
        size: 170,
        minSize: 120,
        meta: { headerTitle: 'On Certificate', skeleton: <Skeleton className="h-5 w-20" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil((data?.pagination.total ?? 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const isDefault =
    source === DEFAULT_SOURCE &&
    !certificateId &&
    verdicts.length === DEFAULT_VERDICTS.length &&
    DEFAULT_VERDICTS.every((v) => verdicts.includes(v));
  const activeFilterCount = (verdicts.length ? 1 : 0) + (source ? 1 : 0) + (certificateId ? 1 : 0);
  const resetFilters = () => {
    setVerdicts(DEFAULT_VERDICTS);
    setSource(DEFAULT_SOURCE);
    setCertificateId('');
    setCertificateLabel('');
  };

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total ?? 0}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      rowPending={rowPending}
      rowHref={(row: CertificateLink) => `/master-data-management/certificates/${row.certificate_id}`}
      standardToolbar={false}
      listingKey="master_data.certificates.view::links"
      tableLayout={{ width: 'fixed', columnsVisibility: true, columnsResizable: true }}
      emptyMessage={
        <div className="flex flex-col items-center gap-1 py-6">
          <span className="font-medium">No links to check</span>
          <span className="text-sm text-muted-foreground">
            Every link in this view is backed by its certificate&apos;s text.
          </span>
        </div>
      }
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInputValue}
                onChange={setSearchInputValue}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search product or certificate..."
                className="w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: !isDefault,
              activeCount: activeFilterCount,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>On certificate</Label>
                    <SearchableMultiSelect
                      value={verdicts}
                      onChange={setVerdicts}
                      options={verdictOptions}
                      placeholder="Every verdict"
                      triggerClassName="mt-1"
                      clearable
                    />
                  </div>
                  <div>
                    <Label>Certificate</Label>
                    <SearchableSelect
                      value={certificateId}
                      onChange={(value) => {
                        setCertificateId(value);
                        setCertificateLabel(certificateOptions.find((o) => o.value === value)?.label ?? '');
                      }}
                      options={certificateOptions}
                      onSearchChange={certificateSearch.setValue}
                      placeholder="Every certificate"
                      triggerClassName="mt-1"
                      clearable
                    />
                  </div>
                  <div>
                    <Label>Source</Label>
                    <SearchableSelect
                      value={source}
                      onChange={setSource}
                      options={SOURCE_OPTIONS}
                      placeholder="AI and manual"
                      triggerClassName="mt-1"
                      clearable
                    />
                  </div>
                  {!isDefault && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={resetFilters}>
                        Reset filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            bulkActions={[
              {
                key: 'confirm',
                label: 'Confirm',
                icon: CheckCheck,
                disabled: confirm.isPending,
                onClick: () =>
                  confirm.mutate(selectedRowIds(table), { onSuccess: () => setRowSelection({}) }),
              },
              {
                key: 'remove',
                label: 'Remove',
                icon: Unlink,
                destructive: true,
                disabled: removal.isStarting,
                onClick: () => removal.run(selectedRowIds(table).map((id) => ({ id }))),
              },
            ]}
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
