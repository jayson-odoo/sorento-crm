'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Filter as FilterIcon, Plus, Unlink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import LoadErrorState from '@/components/common/LoadErrorState';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { PillOverflow, PillOverflowList } from '@/components/common/PillOverflow';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import type { RecordAction } from '@/components/common/recordActions';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { LandingCardShell } from '@/app/(auth)/portal/components/LandingCardShell';
import { useIsMobile } from '@/hooks/use-mobile';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import type { DealerAccessRole, DealerAccessRow } from '@/services/dealerAccessService';
import { DEALER_ACCESS_KEY, useDealerAccessPeopleQuery } from '../hooks/useDealerAccessQuery';
import { useMyDealerCompanies } from '../hooks/useMyDealerCompanies';
import DealerAccessFormDialog, { ACCESS_OPTIONS } from './DealerAccessFormDialog';

const rowKey = (row: DealerAccessRow) => `${row.contact_id}:${row.company}`;

/** The Access cell: the owner tag as a pill, or "Employee", and a hint when another account also links them. */
function AccessCell({ row }: { row: DealerAccessRow }) {
  const label = row.access === 'owner' ? (row.owner_tag ?? 'Business Owner') : 'Employee';
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-1">
      {row.access === 'owner' ? (
        <Badge variant="primary" appearance="light" className="truncate" title={label}>
          {label}
        </Badge>
      ) : (
        <span>{label}</span>
      )}
      {row.other_account ? (
        <span className="text-xs text-muted-foreground">also another account</span>
      ) : null}
    </span>
  );
}

function AccountPills({ row }: { row: DealerAccessRow }) {
  return (
    <PillOverflow
      ariaLabel={`Accounts of ${row.name}`}
      testId={`dealer-accounts-${rowKey(row)}`}
      items={row.accounts.map((a) => ({ key: a.id, label: a.code }))}
      renderPopover={(items) => <PillOverflowList items={items} />}
    />
  );
}

export default function DealerAccessView() {
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [companies, setCompanies] = useState<string[]>([]);
  const [access, setAccess] = useState<DealerAccessRole[]>([]);
  const [form, setForm] = useState<{ open: boolean; person: DealerAccessRow | null }>({
    open: false,
    person: null,
  });
  const isMobile = useIsMobile();
  const { options: companyOptions } = useMyDealerCompanies();

  // The API takes one access level; both picked is the same as none.
  const accessFilter = access.length === 1 ? access[0] : '';
  useResetPageOnFilterChange(setPagination, [debouncedSearch, companies.join(','), accessFilter]);

  const { data, isLoading, isFetching, isPlaceholderData, isError, error, refetch } =
    useDealerAccessPeopleQuery({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      searchQuery: debouncedSearch,
      companies,
      access: accessFilter,
    });
  const rows = useMemo<DealerAccessRow[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;

  const unlink = useDeferredRowAction({
    actionKey: 'dealer_access_link.unlink',
    entityType: 'dealer_access_link',
    verb: 'Unlinking',
    successMessage: 'Access removed.',
    invalidateKeys: [[...DEALER_ACCESS_KEY]],
  });

  const openEdit = (person: DealerAccessRow) => setForm({ open: true, person });

  const actionsFor = (row: DealerAccessRow): RecordAction[] => [
    { key: 'edit', label: 'Edit', run: () => openEdit(row) },
    ...row.accounts.map(
      (a): RecordAction => ({
        key: `unlink-${a.link_id}`,
        label: `Unlink from ${a.code} ${a.name}`,
        icon: Unlink,
        kind: 'destructive',
        run: () => unlink.run({ id: a.link_id, subject: `${row.name} from ${a.code}` }),
      }),
    ),
  ];

  const columns = useMemo<ColumnDef<DealerAccessRow>[]>(
    () => [
      {
        id: 'name',
        header: 'Person',
        size: 200,
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        meta: { headerTitle: 'Person', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'phone',
        header: 'Phone',
        size: 150,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.phone}>
            {row.original.phone}
          </span>
        ),
        meta: { headerTitle: 'Phone', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'company',
        header: 'Company',
        size: 130,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.company_name}>
            {row.original.company_name}
          </span>
        ),
        meta: { headerTitle: 'Company', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'accounts',
        header: 'My accounts',
        size: 240,
        cell: ({ row }) => <AccountPills row={row.original} />,
        meta: { headerTitle: 'My accounts', skeleton: <Skeleton className="h-5 w-32" /> },
      },
      {
        id: 'access',
        header: 'Access',
        size: 230,
        cell: ({ row }) => <AccessCell row={row.original} />,
        meta: { headerTitle: 'Access', skeleton: <Skeleton className="h-5 w-24" /> },
      },
      {
        id: 'actions',
        header: '',
        size: 56,
        enableResizing: false,
        cell: ({ row }) => (
          <RowActionsMenu actions={actionsFor(row.original)} ariaLabel={row.original.name} />
        ),
        meta: { skeleton: <Skeleton className="size-6" /> },
      },
    ],
    // `unlink.run` is memoised by the hook; `actionsFor` only closes over it and `setForm`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [unlink.run],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize) || 1,
    getRowId: rowKey,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const filterCount = companies.length + access.length;
  const searching = !!debouncedSearch || filterCount > 0;
  const emptyMessage = searching ? (
    'No people match this search.'
  ) : (
    <div className="flex w-full flex-col items-center gap-1 py-6 text-center">
      <span className="text-sm font-medium">No people have access yet</span>
      <span className="text-sm text-muted-foreground">
        Add people to give them access to your accounts.
      </span>
    </div>
  );

  return (
    <>
      <Container>
        <PageHeader title="Dealer access" />
      </Container>
      <Container>
        <div className="space-y-3">
          <ListSearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            isSettling={isSearchInFlight(isSettling, isFetching, debouncedSearch)}
            placeholder="Search..."
            aria-label="Search people"
            className="w-full"
            inputClassName="h-12 text-base"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button type="button" variant="outline" size="sm" aria-label="Filter" title="Filter">
                  <FilterIcon />
                  {filterCount > 0 && (
                    <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                      {filterCount}
                    </Badge>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-80 space-y-3">
                {companyOptions.length > 1 ? (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Company</Label>
                    <SearchableMultiSelect
                      aria-label="Company"
                      value={companies}
                      onChange={setCompanies}
                      options={companyOptions}
                      clearable
                      size="sm"
                      placeholder="Any company"
                    />
                  </div>
                ) : null}
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Access</Label>
                  <SearchableMultiSelect
                    aria-label="Access"
                    value={access}
                    onChange={(v) => setAccess(v as DealerAccessRole[])}
                    options={ACCESS_OPTIONS}
                    clearable
                    size="sm"
                    placeholder="Any access"
                  />
                </div>
                <div className="flex justify-end pt-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={filterCount === 0}
                    onClick={() => {
                      setCompanies([]);
                      setAccess([]);
                    }}
                  >
                    Clear all
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
            <Button
              type="button"
              size="sm"
              className="shrink-0"
              onClick={() => setForm({ open: true, person: null })}
            >
              <Plus className="shrink-0" />
              <span className="whitespace-nowrap">Add people</span>
            </Button>
          </div>

          {isError && rows.length === 0 ? (
            <LoadErrorState
              title="Could not load people"
              message={error instanceof Error ? error.message : undefined}
              onRetry={() => refetch()}
            />
          ) : isMobile ? (
            <DataGrid
              table={table}
              recordCount={total}
              isLoading={isLoading}
              isPlaceholderData={isPlaceholderData}
              listingKey={null}
              tableLayout={{ width: 'fixed', columnsResizable: true }}
            >
              <PeopleCards rows={rows} loading={isLoading} empty={emptyMessage} actionsFor={actionsFor} onOpen={openEdit} />
              <div className="mt-3">
                <DataGridPagination />
              </div>
            </DataGrid>
          ) : (
            <DataGrid
              table={table}
              recordCount={total}
              isLoading={isLoading}
              isPlaceholderData={isPlaceholderData}
              listingKey={null}
              tableLayout={{ width: 'fixed', columnsResizable: true }}
              emptyMessage={emptyMessage}
              onRowClick={openEdit}
            >
              <Card>
                <CardTable>
                  <DataGridTable />
                </CardTable>
                <CardFooter>
                  <DataGridPagination />
                </CardFooter>
              </Card>
            </DataGrid>
          )}
        </div>
      </Container>
      <DealerAccessFormDialog
        open={form.open}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        person={form.person}
      />
    </>
  );
}

/** The portal's card list, for a phone width. */
function PeopleCards({
  rows,
  loading,
  empty,
  actionsFor,
  onOpen,
}: {
  rows: DealerAccessRow[];
  loading: boolean;
  empty: React.ReactNode;
  actionsFor: (row: DealerAccessRow) => RecordAction[];
  onOpen: (row: DealerAccessRow) => void;
}) {
  if (loading) return <Skeleton className="h-40 w-full" />;
  if (rows.length === 0) return <Card className="p-4 text-center text-sm">{empty}</Card>;
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => (
        <li key={rowKey(row)}>
          <LandingCardShell
            tintClass="bg-card border-border"
            role="button"
            tabIndex={0}
            onClick={() => onOpen(row)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpen(row);
              }
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-base font-semibold" title={row.name}>
                  {row.name}
                </p>
                <p className="text-sm text-muted-foreground">
                  {row.phone} &middot; {row.company_name}
                </p>
              </div>
              <RowActionsMenu actions={actionsFor(row)} ariaLabel={row.name} />
            </div>
            <div className="mt-1.5">
              <AccessCell row={row} />
            </div>
            <div className="mt-1.5">
              <AccountPills row={row} />
            </div>
          </LandingCardShell>
        </li>
      ))}
    </ul>
  );
}
