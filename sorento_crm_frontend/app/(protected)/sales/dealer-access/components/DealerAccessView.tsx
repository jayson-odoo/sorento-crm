'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Filter as FilterIcon, Plus, RefreshCw, Unlink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Container } from '@/components/common/container';
import LoadErrorState from '@/components/common/LoadErrorState';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { PillOverflow } from '@/components/common/PillOverflow';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import type { RecordAction } from '@/components/common/recordActions';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { LandingCardShell } from '@/app/(auth)/portal/components/LandingCardShell';
import { useIsMobile } from '@/hooks/use-mobile';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { toast } from '@/lib/toast';
import { replaceUrlSearch } from '@/lib/urlSearchState';
import type {
  DealerAccessLinkedAccount,
  DealerAccessRole,
  DealerAccessRow,
} from '@/services/dealerAccessService';
import { useDealerAccessRespondRetry } from '../hooks/useDealerAccessMutations';
import {
  DEALER_ACCESS_KEY,
  useDealerAccessCustomerSearch,
  useDealerAccessPeopleQuery,
} from '../hooks/useDealerAccessQuery';
import { useMyDealerCompanies } from '../hooks/useMyDealerCompanies';
import DealerAccessFormDialog, { ACCESS_OPTIONS, notInRespondText } from './DealerAccessFormDialog';

const rowKey = (row: DealerAccessRow) => `${row.contact_id}:${row.company}`;

/** "Not in Respond.io yet" while Respond.io lacks the person (N5.4); nothing otherwise. */
function RespondCell({ row }: { row: DealerAccessRow }) {
  return row.in_respond ? null : (
    <span className="block truncate text-xs text-muted-foreground" title="Not in Respond.io yet">
      Not in Respond.io yet
    </span>
  );
}

/** The Access cell: the owner tag as a pill, or "Employee". The phone card adds the Respond.io marker below. */
function AccessCell({ row, withRespond = false }: { row: DealerAccessRow; withRespond?: boolean }) {
  const label = row.access === 'owner' ? (row.owner_tag ?? 'Business Owner') : 'Employee';
  return (
    <span className="flex min-w-0 flex-col items-start gap-0.5">
      {row.access === 'owner' ? (
        <Badge variant="primary" appearance="light" className="max-w-full truncate" title={label}>
          {label}
        </Badge>
      ) : (
        <span>{label}</span>
      )}
      {withRespond ? <RespondCell row={row} /> : null}
    </span>
  );
}

/** A chip reads the customer's name; two of one row with the same name add their codes (N1.2). */
function chipLabels(accounts: DealerAccessLinkedAccount[]): string[] {
  const count = new Map<string, number>();
  for (const a of accounts) count.set(a.name, (count.get(a.name) ?? 0) + 1);
  return accounts.map((a) => ((count.get(a.name) ?? 0) > 1 ? `${a.name} (${a.code})` : a.name));
}

function AccountPills({ row }: { row: DealerAccessRow }) {
  const labels = chipLabels(row.accounts);
  return (
    <PillOverflow
      ariaLabel={`Customers of ${row.name}`}
      testId={`dealer-accounts-${rowKey(row)}`}
      items={row.accounts.map((a, i) => ({ key: a.id, label: labels[i], title: a.code }))}
      renderPopover={(items) => (
        <ul className="flex flex-col gap-1 text-sm">
          {items.map((item) => (
            <li key={item.key} className="truncate" title={item.title}>
              {/* A twin's label already carries its code (N1.2): the code shows once. */}
              {item.title && !item.label.includes(item.title) ? `${item.label} (${item.title})` : item.label}
            </li>
          ))}
        </ul>
      )}
    />
  );
}

export default function DealerAccessView() {
  const params = useSearchParams();
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch(params.get('q') ?? '');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  // Every filter lives in the address bar (N2.7); "My customers" is on unless `mine=0`.
  const [mine, setMineState] = useState(() => params.get('mine') !== '0');
  const [companies, setCompaniesState] = useState<string[]>(() => splitMulti(params.get('company')));
  const [access, setAccessState] = useState<DealerAccessRole[]>(
    () => splitMulti(params.get('access')) as DealerAccessRole[],
  );
  const [customers, setCustomersState] = useState<string[]>(() => splitMulti(params.get('customer')));
  const [customerNames, setCustomerNames] = useState<Record<string, string>>({});
  const setMine = (value: boolean) => {
    setMineState(value);
    replaceUrlSearch({ mine: value ? '' : '0' });
  };
  const setCompanies = (value: string[]) => {
    setCompaniesState(value);
    replaceUrlSearch({ company: joinMulti(value) });
  };
  const setAccess = (value: DealerAccessRole[]) => {
    setAccessState(value);
    replaceUrlSearch({ access: joinMulti(value) });
  };
  const setCustomers = (value: string[]) => {
    setCustomersState(value);
    replaceUrlSearch({ customer: joinMulti(value) });
  };
  const searchCustomers = useDealerAccessCustomerSearch(mine, companies);
  // The settled search text rides the address bar too, as `q`.
  useEffect(() => {
    replaceUrlSearch({ q: debouncedSearch });
  }, [debouncedSearch]);
  const [form, setForm] = useState<{ open: boolean; person: DealerAccessRow | null }>({
    open: false,
    person: null,
  });
  const isMobile = useIsMobile();
  const { options: companyOptions } = useMyDealerCompanies();

  // The API takes one access level; both picked is the same as none.
  const accessFilter = access.length === 1 ? access[0] : '';
  useResetPageOnFilterChange(setPagination, [
    debouncedSearch,
    companies.join(','),
    accessFilter,
    mine,
    customers.join(','),
  ]);

  const { data, isLoading, isFetching, isPlaceholderData, isError, error, refetch } =
    useDealerAccessPeopleQuery({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      searchQuery: debouncedSearch,
      companies,
      access: accessFilter,
      mine,
      customers,
    });
  const rows = useMemo<DealerAccessRow[]>(() => data?.data ?? [], [data]);
  // A picked customer's chip reads its name: from the search that offered it, else from a row that lists it.
  const selectedCustomers = customers.map((id) => {
    const fromRows = rows.flatMap((r) => r.accounts).find((a) => a.id === id);
    const label = customerNames[id] ?? (fromRows ? `${fromRows.name} (${fromRows.code})` : 'A customer');
    return { value: id, label };
  });
  const fetchCustomerOptions = async (query: string) => {
    const found = await searchCustomers(query);
    const options = found.map((c) => ({ value: c.id, label: `${c.name} (${c.code})` }));
    setCustomerNames((prev) => ({ ...prev, ...Object.fromEntries(options.map((o) => [o.value, o.label])) }));
    return options;
  };
  const total = data?.pagination.total ?? 0;

  const unlink = useDeferredRowAction({
    actionKey: 'dealer_access_link.unlink',
    entityType: 'dealer_access_link',
    verb: 'Unlinking',
    successMessage: 'Access removed.',
    invalidateKeys: [[...DEALER_ACCESS_KEY]],
  });

  const respondRetry = useDealerAccessRespondRetry();

  const openEdit = (person: DealerAccessRow) => setForm({ open: true, person });

  // A person I may not change has no actions; clicking them opens the dialog read-only (N2.5).
  const actionsFor = (row: DealerAccessRow): RecordAction[] =>
    row.editable
      ? [
          { key: 'edit', label: 'Edit', run: () => openEdit(row) },
          ...(row.in_respond
            ? []
            : [
                {
                  key: 'respond',
                  label: 'Try again in Respond.io',
                  icon: RefreshCw,
                  run: () =>
                    respondRetry.mutate(row.contact_id, {
                      onSuccess: (result) => {
                        if (result.respond === 'failed') toast.error(notInRespondText(result.respond_error));
                      },
                    }),
                } satisfies RecordAction,
              ]),
          ...row.accounts
            .filter((a) => a.mine && a.link_id)
            .map(
              (a): RecordAction => ({
                key: `unlink-${a.link_id}`,
                label: `Unlink from ${a.name} (${a.code})`,
                icon: Unlink,
                kind: 'destructive',
                run: () => unlink.run({ id: String(a.link_id), subject: `${row.name} from ${a.name}` }),
              }),
            ),
        ]
      : [];

  const columns = useMemo<ColumnDef<DealerAccessRow>[]>(
    () => [
      {
        id: 'name',
        header: 'Person',
        size: 180,
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
        size: 140,
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
        size: 100,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.company_name}>
            {row.original.company_name}
          </span>
        ),
        meta: { headerTitle: 'Company', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'accounts',
        header: 'Customers',
        size: 240,
        cell: ({ row }) => <AccountPills row={row.original} />,
        meta: { headerTitle: 'Customers', skeleton: <Skeleton className="h-5 w-32" /> },
      },
      {
        id: 'access',
        header: 'Access',
        size: 200,
        cell: ({ row }) => <AccessCell row={row.original} />,
        meta: { headerTitle: 'Access', skeleton: <Skeleton className="h-5 w-24" /> },
      },
      {
        id: 'respond',
        header: 'Respond.io',
        size: 160,
        cell: ({ row }) => <RespondCell row={row.original} />,
        meta: { headerTitle: 'Respond.io', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'actions',
        header: '',
        size: 48,
        enableResizing: false,
        cell: ({ row }) => {
          const actions = actionsFor(row.original);
          return actions.length ? <RowActionsMenu actions={actions} ariaLabel={row.original.name} /> : null;
        },
        meta: { skeleton: <Skeleton className="size-6" /> },
      },
    ],
    // `unlink.run` and `respondRetry.mutate` are stable; `actionsFor` only closes over them and `setForm`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [unlink.run, respondRetry.mutate],
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

  const filterCount = companies.length + access.length + customers.length + (mine ? 0 : 1);
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
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="dealer-access-mine">My customers</Label>
                  <Switch
                    id="dealer-access-mine"
                    aria-label="My customers"
                    size="sm"
                    checked={mine}
                    onCheckedChange={(v) => setMine(v === true)}
                  />
                </div>
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
                  <Label className="text-xs text-muted-foreground">Customer</Label>
                  <SearchableMultiSelect
                    aria-label="Customer"
                    value={customers}
                    onChange={setCustomers}
                    fetchOptions={fetchCustomerOptions}
                    selectedOptions={selectedCustomers}
                    clearable
                    size="sm"
                    placeholder="Any customer"
                  />
                </div>
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
                      setCompaniesState([]);
                      setAccessState([]);
                      setCustomersState([]);
                      setMineState(true);
                      replaceUrlSearch({ mine: '', company: '', access: '', customer: '' });
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
              {actionsFor(row).length ? (
                <RowActionsMenu actions={actionsFor(row)} ariaLabel={row.name} />
              ) : null}
            </div>
            <div className="mt-1.5">
              <AccessCell row={row} withRespond />
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
