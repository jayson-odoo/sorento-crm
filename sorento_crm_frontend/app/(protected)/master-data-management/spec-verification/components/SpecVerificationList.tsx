'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { BadgeCheck, BadgeX, ChevronRight, LoaderCircleIcon, Search, X } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { readable, readableEntry } from '@/lib/spec-readable';
import { statusPillClass, STATUS_PILL_BASE } from '@/lib/status-pill';
import {
  skippedUnverifyCodes,
  skippedVerifyCodes,
  useSpecVerificationMutations,
  useSpecVerificationWorklist,
} from '../hooks/useSpecVerification';
import type {
  SpecVerificationRow,
  VerificationBlock,
  VerificationState,
} from '../types/specVerification.types';

const DEFAULT_PAGE_SIZE = 25;

const STATE_LABEL: Record<VerificationState, string> = {
  verified: 'Verified',
  needs_reverify: 'Needs re-verify',
  unverified: 'Unverified',
};

const STATE_OPTIONS = [
  { value: 'needs_reverify', label: 'Needs re-verify' },
  { value: 'unverified', label: 'Unverified' },
  { value: 'verified', label: 'Verified' },
];

/** What a confirmation counts. "(s)" reads as copy nobody finished writing. */
function productCodeCount(n: number): string {
  return `${n} product code${n === 1 ? '' : 's'}`;
}

/** Who vouched for the code and when, or what moved under the stamp. */
function verificationTitle(block: VerificationBlock): string {
  const stamp =
    block.verified_by_name && block.verified_at
      ? `${block.verified_by_name} on ${formatDateTimeInMalaysia(block.verified_at)}`
      : null;
  if (block.state === 'verified') {
    return stamp ? `Verified by ${stamp}` : 'Verified';
  }
  if (block.state === 'needs_reverify') {
    const changed = block.invalidated_diff?.changed ?? [];
    // The diff carries the stored ENTRIES (`{ value, unit }`), not scalars, and there
    // is no registry to hand here for the labels - `readable` is that fallback.
    const diff = changed
      .map(
        (c) =>
          `${readable(c.spec_key)}: ${readableEntry(c.was) || 'nothing'} to ${
            readableEntry(c.now) || 'nothing'
          }`,
      )
      .join('; ');
    const head = stamp ? `Was verified by ${stamp}.` : 'Was verified.';
    return changed.length ? `${head} ${changed.length} changed - ${diff}` : head;
  }
  if (block.invalidated_reason === 'manual_unverify') {
    const who = block.invalidated_by_name ?? 'someone';
    const when = block.invalidated_at ? formatDateTimeInMalaysia(block.invalidated_at) : '';
    const withdrawn = when ? `Withdrawn by ${who} on ${when}.` : `Withdrawn by ${who}.`;
    return stamp ? `${withdrawn} Originally verified by ${stamp}` : withdrawn;
  }
  return 'Not verified yet';
}

export default function SpecVerificationList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Filters live in the URL, so a link is a shareable slice and a refresh
  // resumes in place (AC-D.17b). Seeded once, written back on every change.
  const [pagination, setPagination] = useState<PaginationState>(() => {
    const page = parseInt(searchParams.get('page') ?? '1', 10);
    const limit = parseInt(searchParams.get('limit') ?? String(DEFAULT_PAGE_SIZE), 10);
    return {
      pageIndex: Number.isNaN(page) ? 0 : Math.max(0, page - 1),
      pageSize: Number.isNaN(limit) || limit < 1 ? DEFAULT_PAGE_SIZE : Math.min(limit, 100),
    };
  });
  const [sorting, setSorting] = useState<SortingState>(() => {
    const sort = searchParams.get('sort');
    return sort && sort !== 'default'
      ? [{ id: sort, desc: searchParams.get('dir') === 'desc' }]
      : [];
  });
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('query') ?? '');
  const [searchInput, setSearchInput] = useState(() => searchParams.get('query') ?? '');
  const [stateFilter, setStateFilter] = useState(() => searchParams.get('state') ?? '');
  const [classFilter, setClassFilter] = useState(() => searchParams.get('class_label') ?? '');
  const [includeDiscontinued, setIncludeDiscontinued] = useState(
    () => searchParams.get('include_discontinued') === 'true',
  );
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  // The dialog carries the codes it was opened for, so a row-level Unverify and a bulk
  // Unverify are the same confirmation with a different count (PRINCIPLES: confirm
  // before every destructive or detach action, never one-click).
  const [confirmTarget, setConfirmTarget] = useState<{
    action: 'verify' | 'unverify';
    codes: string[];
  } | null>(null);

  // Deps are primitives, and an unchanged URL is not rewritten: `sorting` /
  // `pagination` are fresh objects on some table renders, and replacing the URL
  // with itself remounts this subtree, which restarts the query forever.
  const sortField = sorting[0]?.id ?? '';
  const sortDesc = sorting[0]?.desc ?? false;
  const { pageIndex, pageSize } = pagination;
  useEffect(() => {
    const next = new URLSearchParams();
    if (searchQuery) next.set('query', searchQuery);
    if (stateFilter) next.set('state', stateFilter);
    if (classFilter) next.set('class_label', classFilter);
    if (includeDiscontinued) next.set('include_discontinued', 'true');
    if (sortField) {
      next.set('sort', sortField);
      next.set('dir', sortDesc ? 'desc' : 'asc');
    }
    if (pageIndex > 0) next.set('page', String(pageIndex + 1));
    if (pageSize !== DEFAULT_PAGE_SIZE) next.set('limit', String(pageSize));
    const qs = next.toString();
    const target = qs ? `${pathname}?${qs}` : pathname;
    if (`${window.location.pathname}${window.location.search}` === target) return;
    router.replace(target, { scroll: false });
  }, [
    router,
    pathname,
    searchQuery,
    stateFilter,
    classFilter,
    includeDiscontinued,
    sortField,
    sortDesc,
    pageIndex,
    pageSize,
  ]);

  const { data, isLoading, isError, error, refetch, isFetching } = useSpecVerificationWorklist({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    state: (stateFilter || '') as VerificationState | '',
    class_label: classFilter,
    include_discontinued: includeDiscontinued,
  });
  const { verify, unverify } = useSpecVerificationMutations();
  const pending = verify.isPending || unverify.isPending;

  const rows = useMemo(() => data?.data ?? [], [data]);
  const summary = data?.summary;
  // The class facet rides the worklist response, so no second call is made for it.
  // Held in a ref across refetches so the dropdown does not blink empty while the page
  // it just filtered is still loading.
  const classOptionsRef = useRef<string[]>([]);
  if (data?.classes?.length) classOptionsRef.current = data.classes;
  const classOptions = classOptionsRef.current;
  const filtersActive = Boolean(searchQuery || stateFilter || classFilter || includeDiscontinued);

  const clearFilters = () => {
    setSearchQuery('');
    setSearchInput('');
    setStateFilter('');
    setClassFilter('');
    setIncludeDiscontinued(false);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  /**
   * Anything skipped stays selected so it can be dealt with; everything acted on
   * is released (AC-D.11). A row button never selects a row that was not already
   * selected - it acts on one code, it does not start a selection.
   */
  const settleSelection = (codes: string[], skipped: string[]) => {
    setRowSelection((prev) => {
      const next: RowSelectionState = { ...prev };
      for (const code of codes) {
        if (skipped.includes(code) && prev[code]) next[code] = true;
        else delete next[code];
      }
      return next;
    });
  };

  const runVerify = async (codes: string[]) => {
    const items = rows
      .filter((row) => codes.includes(row.product_code))
      .map((row) => ({ product_code: row.product_code, values_hash: row.values_hash }));
    if (!items.length) return;
    const response = await verify.mutateAsync(items);
    settleSelection(codes, skippedVerifyCodes(response.results));
  };

  const runUnverify = async (codes: string[]) => {
    if (!codes.length) return;
    const response = await unverify.mutateAsync(codes);
    settleSelection(codes, skippedUnverifyCodes(response.results));
  };

  const columns = useMemo<ColumnDef<SpecVerificationRow>[]>(
    () => [
      buildSelectColumn<SpecVerificationRow>({ size: 44 }),
      {
        accessorKey: 'product_code',
        id: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => (
          <span className="font-medium text-sm truncate block" title={row.original.product_code}>
            {row.original.product_code}
          </span>
        ),
        size: 120,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-24" /> },
        enableSorting: true,
        enableHiding: false,
      },
      {
        accessorKey: 'product_name',
        id: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="text-sm truncate block" title={row.original.product_name}>
            {row.original.product_name}
          </span>
        ),
        size: 165,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-48" /> },
        enableSorting: false,
      },
      {
        accessorKey: 'class_label',
        id: 'class',
        header: ({ column }) => <DataGridColumnHeader title="Class" column={column} />,
        cell: ({ row }) => (
          <span
            className="text-sm truncate block"
            title={row.original.class_label ?? 'Not classified'}
          >
            {row.original.class_label ?? 'Not classified'}
          </span>
        ),
        size: 95,
        meta: { headerTitle: 'Class', skeleton: <Skeleton className="h-4 w-20" /> },
        enableSorting: false,
      },
      {
        accessorKey: 'brand_name',
        id: 'brand',
        header: ({ column }) => <DataGridColumnHeader title="Brand" column={column} />,
        cell: ({ row }) => (
          <span className="text-sm truncate block" title={row.original.brand_name ?? '-'}>
            {row.original.brand_name ?? '-'}
          </span>
        ),
        size: 90,
        meta: { headerTitle: 'Brand', skeleton: <Skeleton className="h-4 w-20" /> },
        enableSorting: false,
      },
      {
        accessorKey: 'coverage',
        id: 'coverage',
        header: ({ column }) => <DataGridColumnHeader title="Coverage" column={column} />,
        cell: ({ row }) => {
          const { have, applicable } = row.original.coverage;
          return (
            <span
              className="text-sm tabular-nums"
              title={`${have} of ${applicable} applicable keys hold a value`}
            >
              {have} / {applicable}
            </span>
          );
        },
        size: 90,
        meta: { headerTitle: 'Coverage', skeleton: <Skeleton className="h-4 w-12" /> },
        enableSorting: true,
      },
      {
        accessorKey: 'open_exceptions',
        id: 'open_exceptions',
        header: ({ column }) => <DataGridColumnHeader title="Exceptions" column={column} />,
        cell: ({ row }) => {
          const count = row.original.open_exceptions;
          if (!count) return <span className="text-sm text-muted-foreground">0</span>;
          return (
            <Badge variant="warning" appearance="light" title="Verify is refused while open">
              {count}
            </Badge>
          );
        },
        size: 100,
        meta: { headerTitle: 'Exceptions', skeleton: <Skeleton className="h-4 w-8" /> },
        enableSorting: false,
      },
      {
        accessorKey: 'verification',
        id: 'verification',
        header: ({ column }) => <DataGridColumnHeader title="Verification" column={column} />,
        cell: ({ row }) => {
          const block = row.original.verification;
          return (
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(block.state)}`}
              title={verificationTitle(block)}
            >
              {STATE_LABEL[block.state]}
            </span>
          );
        },
        size: 125,
        meta: { headerTitle: 'Verification', skeleton: <Skeleton className="h-5 w-20" /> },
        enableSorting: false,
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const item = row.original;
          const isVerified = item.verification.state === 'verified';
          return (
            <div
              className="flex items-center justify-end gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              {isVerified ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={pending}
                  onClick={() =>
                    setConfirmTarget({ action: 'unverify', codes: [item.product_code] })
                  }
                >
                  Unverify
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={pending}
                  onClick={() => void runVerify([item.product_code])}
                >
                  Verify
                </Button>
              )}
              <ChevronRight className="text-muted-foreground/70 size-3.5" />
            </div>
          );
        },
        size: 130,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-7 w-20" /> },
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pending, rows],
  );

  const [columnOrder, setColumnOrder] = useState<string[]>(() =>
    columns.map((column) => column.id as string),
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((data?.pagination.total ?? 0) / pagination.pageSize),
    getRowId: (row: SpecVerificationRow) => row.product_code,
    state: { pagination, sorting, columnOrder, rowSelection },
    columnResizeMode: 'onChange',
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onColumnOrderChange: setColumnOrder,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  // Selection is page-scoped (AC-D.10), so it is dropped when the page changes: a
  // code the user can no longer see must not be carried into a bulk action.
  useEffect(() => {
    table.resetRowSelection();
  }, [table, pageIndex, pageSize]);

  // Read off the table's own selected rows rather than the raw selection map. The map
  // can still hold a code from a page the user has left, which would make the
  // toolbar's count disagree with what a bulk action actually sends. Not memoised:
  // the row model is memoised inside the table, and this is only read in a click
  // handler.
  const selectedCodes = table
    .getSelectedRowModel()
    .rows.map((selected) => selected.original.product_code);

  const confirmRun = async () => {
    const target = confirmTarget;
    setConfirmTarget(null);
    if (!target) return;
    if (target.action === 'verify') await runVerify(target.codes);
    else await runUnverify(target.codes);
  };

  const bulkActions: ToolbarAction[] = [
    {
      key: 'verify',
      label: 'Verify selected',
      icon: BadgeCheck,
      disabled: pending,
      onClick: () => setConfirmTarget({ action: 'verify', codes: selectedCodes }),
    },
    {
      key: 'unverify',
      label: 'Unverify selected',
      icon: BadgeX,
      disabled: pending,
      onClick: () => setConfirmTarget({ action: 'unverify', codes: selectedCodes }),
    },
  ];

  const applySearch = () => {
    setSearchQuery(searchInput);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  if (isError) {
    return (
      <Card>
        <CardTable>
          <div className="p-8 text-center text-muted-foreground">
            <p className="font-medium text-destructive">Failed to load the verification worklist.</p>
            <p className="text-sm mt-1">
              {error instanceof Error ? error.message : 'Please try again.'}
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => void refetch()}>
              Retry
            </Button>
          </div>
        </CardTable>
      </Card>
    );
  }

  const confirmCount = confirmTarget?.codes.length ?? 0;
  const confirmCopy =
    confirmTarget?.action === 'verify'
      ? {
          title: 'Confirm verify',
          description: `Verify ${productCodeCount(confirmCount)}? A code with open exceptions, or one whose values moved while you were reviewing, is reported back as skipped.`,
          actionLabel: 'Verify',
        }
      : {
          title: 'Confirm unverify',
          description: `Withdraw the verification on ${productCodeCount(confirmCount)}? ${
            confirmCount === 1 ? 'It reads' : 'They read'
          } as unverified again and the history keeps who vouched.`,
          actionLabel: 'Unverify',
        };

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total ?? 0}
        isLoading={isLoading}
        onRowClick={(row) =>
          router.push(
            `/master-data-management/products/${row.product_id}?tab=specifications`,
          )
        }
        listingKey="master_data.products.view::spec-verification"
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        tableClassNames={{ edgeCell: 'px-5' }}
        emptyMessage={
          <div className="py-6 text-center">
            <p className="font-medium">Nothing to review here.</p>
            <p className="text-sm text-muted-foreground mt-1">
              {filtersActive
                ? 'No product code matches these filters.'
                : 'No product code is waiting for verification.'}
            </p>
            {filtersActive ? (
              <Button variant="outline" size="sm" className="mt-4" onClick={clearFilters}>
                Clear filters
              </Button>
            ) : (
              <Button variant="outline" size="sm" className="mt-4" asChild>
                <Link href="/master-data-management/products">Go to products</Link>
              </Button>
            )}
          </div>
        }
      >
        <Card>
          <CardHeader className="block space-y-3">
            <div className="text-sm text-muted-foreground" data-testid="verification-progress">
              {summary ? (
                <>
                  Verified {summary.verified.toLocaleString()} of{' '}
                  {summary.total.toLocaleString()} {includeDiscontinued ? 'codes' : 'live codes'}
                </>
              ) : (
                <Skeleton className="h-4 w-56" />
              )}
            </div>
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search code or name"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && applySearch()}
                    disabled={isLoading}
                    className="ps-9 w-full sm:w-40 md:w-64"
                  />
                  {searchQuery.length > 0 && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                      onClick={() => {
                        setSearchInput('');
                        setSearchQuery('');
                        setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                      }}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: Boolean(stateFilter || classFilter || includeDiscontinued),
                activeCount:
                  (stateFilter ? 1 : 0) + (classFilter ? 1 : 0) + (includeDiscontinued ? 1 : 0),
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="spec-verification-state">Verification</Label>
                      <SearchableSelect
                        id="spec-verification-state"
                        value={stateFilter}
                        clearable
                        placeholder="Any state"
                        options={STATE_OPTIONS}
                        onChange={(value) => {
                          setStateFilter(value);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="spec-verification-class">Class</Label>
                      <SearchableSelect
                        id="spec-verification-class"
                        value={classFilter}
                        clearable
                        placeholder="Any class"
                        options={classOptions.map((label) => ({
                          value: label,
                          label,
                        }))}
                        onChange={(value) => {
                          setClassFilter(value);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor="spec-verification-discontinued">Include discontinued</Label>
                      <Switch
                        id="spec-verification-discontinued"
                        checked={includeDiscontinued}
                        onCheckedChange={(checked) => {
                          setIncludeDiscontinued(checked);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                      />
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={clearFilters}
                    >
                      Clear filters
                    </Button>
                  </div>
                ),
              }}
              exportConfig={false}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching}
              bulkActions={bulkActions}
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
      </DataGrid>

      <AlertDialog
        open={confirmTarget !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmCopy.title}</AlertDialogTitle>
            <AlertDialogDescription>{confirmCopy.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void confirmRun();
              }}
              disabled={pending}
            >
              {pending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  {confirmCopy.actionLabel}...
                </>
              ) : (
                confirmCopy.actionLabel
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
