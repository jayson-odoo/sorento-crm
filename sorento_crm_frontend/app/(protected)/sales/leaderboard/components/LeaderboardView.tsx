'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type PaginationState,
} from '@tanstack/react-table';
import { Loader2, SlidersHorizontal, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { StatCard } from '@/components/scm/StatCard';
import { useSalesLeaderboardOptionsQuery, useSalesLeaderboardQuery } from '@/hooks/useSalesLeaderboardQuery';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { localStore } from '@/lib/storage';
import { cn } from '@/lib/utils';
import type { LeaderboardBasis, LeaderboardBy, LeaderboardRow } from '@/services/salesLeaderboardService';
import { LeaderboardPodium } from './LeaderboardPodium';
import {
  COLUMN_SIZES,
  VIEW_SIZES,
  changeTone,
  codesText,
  formatAmount,
  formatChange,
  formatRm,
  previousLabel,
  targetText,
} from './leaderboardFormat';
import {
  BASES,
  VIEWS,
  hasSetupKeys,
  isRunnable,
  parseSetup,
  queryParams,
  rememberable,
  reportHref,
  serializeSetup,
  topSellingHref,
  defaultPeriod,
  type Period,
  type Setup,
} from './leaderboardState';

const PERIOD_CHIPS: { kind: Period; label: string }[] = [
  { kind: 'this_month', label: 'This month' },
  { kind: 'last_month', label: 'Last month' },
  { kind: 'this_quarter', label: 'This quarter' },
  { kind: 'ytd', label: 'YTD' },
  { kind: 'custom', label: 'Custom' },
];

const BASIS_WORD: Record<LeaderboardBasis, string> = {
  invoiced: 'invoiced',
  delivered: 'delivered',
  ordered: 'ordered',
  outstanding: 'undelivered',
};
const AMOUNT_TITLE: Record<LeaderboardBasis, string> = {
  invoiced: 'Invoiced net (RM)',
  delivered: 'Delivered (RM)',
  ordered: 'Ordered (RM)',
  outstanding: 'Undelivered (RM)',
};
const NAME_TITLE: Record<LeaderboardBy, string> = {
  person: 'Sales person',
  customer: 'Customer',
  product: 'Item',
  brand: 'Brand',
  category: 'Category',
  channel: 'Channel',
};

const MOBILE_PAGE = 50;
const STORAGE_KEY = 'sales-leaderboard-setup';

const NO_CHANNELS = { invoiced: [], delivered: [], ordered: [], outstanding: [] };
const NO_CAN = { invoiced: false, delivered: false, ordered: false, outstanding: false };

const numberCell = (value: number) => <span className="tabular-nums">{value}</span>;
const rightAligned = (title: string, skeleton: string) => ({
  headerTitle: title,
  headerClassName: 'text-end',
  cellClassName: 'text-end',
  skeleton: <Skeleton className={cn('h-4', skeleton)} />,
});

/**
 * Sales > Leaderboard (PLAN-sales-leaderboard-07nov + PLAN-sales-insights-p2-07nov). Read-only: no CTA, no subtitle.
 * One screen, one engine: a basis, a View by, filters and drill chips, all held in the URL.
 */
export default function LeaderboardView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlQuery = searchParams?.toString() ?? '';
  const urlHasState = hasSetupKeys(new URLSearchParams(urlQuery));

  // Option A: with no state in the URL the last setup of this browser opens (read after mount, never on the server).
  const [stored, setStored] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    // `localStore` never throws (a refusing browser falls back to memory).
    setStored(localStore.getItem(STORAGE_KEY));
  }, []);
  const restoring = !urlHasState && stored === undefined;
  const effectiveQuery = urlHasState ? urlQuery : (stored ?? '');

  const optionsQuery = useSalesLeaderboardOptionsQuery();
  const options = optionsQuery.data;
  const can = options?.can ?? NO_CAN;

  // What the user just chose shows at once; the URL (Back, a shared link) takes over when it moves.
  const [local, setLocal] = useState<Setup | null>(null);
  useEffect(() => setLocal(null), [effectiveQuery]);

  const setup = useMemo<Setup>(() => {
    const parsed = local ?? parseSetup(new URLSearchParams(effectiveQuery));
    // A view the caller may not open (a shared link) shows the board instead of a refusal.
    if (options && parsed.by !== 'person' && !can[parsed.basis] && parsed.person.length === 0) {
      return { ...parsed, by: 'person' };
    }
    return parsed;
  }, [local, effectiveQuery, options, can]);

  useEffect(() => {
    if (!urlHasState) return;
    localStore.setItem(STORAGE_KEY, rememberable(setup));
  }, [urlHasState, setup]);

  const navigate = useCallback(
    (patch: Partial<Setup>) => {
      let next: Setup = { ...setup, ...patch };
      if (patch.basis && patch.basis !== setup.basis) {
        if (patch.basis === 'outstanding') next.period = 'all_open';
        else if (next.period === 'all_open') next.period = defaultPeriod(patch.basis);
        const valid = options?.channels?.[patch.basis]?.map((o) => o.value);
        if (valid) next = { ...next, channel: next.channel.filter((c) => valid.includes(c)) };
      }
      setLocal(next);
      router.push(`${pathname}?${serializeSetup(next)}`);
    },
    [setup, options, router, pathname],
  );

  const runnable = isRunnable(setup);
  const { data, isLoading, isFetching, isError, error, isPlaceholderData } = useSalesLeaderboardQuery(
    queryParams(setup),
    runnable && !restoring,
  );

  const rows = useMemo<LeaderboardRow[]>(() => data?.rows ?? [], [data]);
  // The grid follows the answer on screen (the old board stays behind a new request), not the request.
  const dataBy: LeaderboardBy = data?.by ?? setup.by;
  const dataBasis: LeaderboardBasis = data?.basis ?? setup.basis;
  const outstanding = dataBasis === 'outstanding';
  const versus = data ? previousLabel(data.previous_from, data.previous_to) : 'previous period';
  const myRow = rows.find((row) => row.is_me);
  const activeFilters =
    (setup.company ? 1 : 0) + (setup.brand.length ? 1 : 0) + (setup.category.length ? 1 : 0) + (setup.channel.length ? 1 : 0);
  const canOpenRows = Boolean(data?.can_drill_others) || setup.person.length > 0;

  const drillOf = useCallback(
    (row: LeaderboardRow): Partial<Setup> | null => {
      if (dataBy === 'person') {
        if (!(data?.can_drill_others || row.is_me)) return null;
        return { by: 'customer', person: [row.person ?? row.name] };
      }
      if (!canOpenRows) return null;
      if (dataBy === 'channel') return row.key ? { by: 'customer', channel: [row.key] } : null;
      if (row.keys.length === 0) return null; // the "(no brand)" style row stands for nothing to open
      if (dataBy === 'customer') return { by: 'product', customer: row.keys, customerLabel: row.name };
      if (dataBy === 'product') return { by: 'customer', product: row.keys, productLabel: row.name };
      if (dataBy === 'brand') return { by: 'customer', brand: row.keys };
      return { by: 'customer', category: row.keys };
    },
    [dataBy, data?.can_drill_others, canOpenRows],
  );

  const showTarget = dataBy === 'person' && rows.some((row) => row.target);
  const showCodes = dataBy === 'person' && rows.some((row) => codesText(row.person ?? row.name, row.codes ?? []) !== '');

  const columns = useMemo<ColumnDef<LeaderboardRow>[]>(() => {
    const rank: ColumnDef<LeaderboardRow> = {
      accessorKey: 'rank',
      header: ({ column }) => <DataGridColumnHeader title={dataBy === 'person' ? 'Rank' : '#'} column={column} />,
      cell: ({ row }) => <span className="tabular-nums">{row.original.rank}</span>,
      size: COLUMN_SIZES.rank,
      meta: { headerTitle: 'Rank', skeleton: <Skeleton className="h-4 w-6" /> },
    };
    const name: ColumnDef<LeaderboardRow> = {
      id: 'name',
      header: ({ column }) => <DataGridColumnHeader title={NAME_TITLE[dataBy]} column={column} />,
      cell: ({ row }) => {
        const label = row.original.person ?? row.original.name;
        return (
          <span className="block min-w-0">
            <span className="block truncate font-medium" title={label}>
              {label}
              {row.original.is_me ? ' (you)' : ''}
            </span>
            {dataBy === 'customer' && row.original.code ? (
              <span className="block truncate text-xs text-muted-foreground" title={row.original.code}>
                {row.original.code}
              </span>
            ) : null}
          </span>
        );
      },
      size: dataBy === 'customer' ? VIEW_SIZES.customerName : dataBy === 'person' ? COLUMN_SIZES.person : VIEW_SIZES.name,
      meta: { headerTitle: NAME_TITLE[dataBy], skeleton: <Skeleton className="h-4 w-24" /> },
    };
    const text = (id: string, title: string, size: number, read: (r: LeaderboardRow) => string): ColumnDef<LeaderboardRow> => ({
      id,
      header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
      cell: ({ row }) => {
        const value = read(row.original);
        return (
          <span className="block truncate text-muted-foreground" title={value}>
            {value}
          </span>
        );
      },
      size,
      meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-20" /> },
    });
    const amount: ColumnDef<LeaderboardRow> = {
      accessorKey: 'amount',
      header: ({ column }) => <DataGridColumnHeader title={AMOUNT_TITLE[dataBasis]} column={column} />,
      cell: ({ row }) => <span className="tabular-nums">{formatAmount(row.original.amount)}</span>,
      size: COLUMN_SIZES.amount,
      meta: rightAligned(AMOUNT_TITLE[dataBasis], 'w-24'),
    };
    const change: ColumnDef<LeaderboardRow> = {
      accessorKey: 'change_pct',
      header: ({ column }) => <DataGridColumnHeader title="vs last period" column={column} />,
      cell: ({ row }) =>
        outstanding ? null : (
          <span className={cn('tabular-nums', changeTone(row.original.change_pct))}>
            {formatChange(row.original.change_pct)}
          </span>
        ),
      size: COLUMN_SIZES.change,
      meta: rightAligned('vs last period', 'w-12'),
    };
    const count = (id: 'customers' | 'products', title: string): ColumnDef<LeaderboardRow> => ({
      accessorKey: id,
      header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
      cell: ({ row }) => numberCell(row.original[id]),
      size: COLUMN_SIZES.customers,
      meta: rightAligned(title, 'w-8'),
    });
    const qty: ColumnDef<LeaderboardRow> = {
      accessorKey: 'qty',
      header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
      cell: ({ row }) => numberCell(row.original.qty),
      size: VIEW_SIZES.qty,
      meta: rightAligned('Qty', 'w-8'),
    };

    if (dataBy === 'person') {
      return [
        rank,
        name,
        ...(showCodes
          ? [text('codes', 'Codes', showTarget ? VIEW_SIZES.codesNarrow : COLUMN_SIZES.codes, (r) => codesText(r.person ?? r.name, r.codes ?? []))]
          : []),
        amount,
        change,
        count('customers', 'Customers'),
        ...(showTarget
          ? [
              {
                id: 'target',
                header: ({ column }) => <DataGridColumnHeader title="Target" column={column} />,
                cell: ({ row }) => {
                  const target = row.original.target;
                  if (!target) return null;
                  const shown = targetText(target);
                  return (
                    <span
                      className="block truncate tabular-nums"
                      title={`Target ${formatRm(target.target_amount)}, achieved ${formatRm(target.achieved_amount)}`}
                    >
                      {shown}
                    </span>
                  );
                },
                size: VIEW_SIZES.target,
                meta: { headerTitle: 'Target', skeleton: <Skeleton className="h-4 w-24" /> },
              } as ColumnDef<LeaderboardRow>,
            ]
          : []),
      ];
    }
    if (dataBy === 'customer') {
      return [rank, name, text('companies', 'Companies', VIEW_SIZES.companies, (r) => (r.companies ?? []).join(', ')), amount, change, count('products', 'Items')];
    }
    if (dataBy === 'product') {
      return [
        rank,
        name,
        text('brand', 'Brand', VIEW_SIZES.brand, (r) => r.brand ?? ''),
        text('category', 'Category', VIEW_SIZES.brand, (r) => r.category ?? ''),
        qty,
        amount,
        change,
        count('customers', 'Customers'),
      ];
    }
    return [rank, name, amount, change, count('customers', 'Customers'), ...(dataBy === 'channel' ? [] : [count('products', 'Items')])];
  }, [dataBy, dataBasis, outstanding, showCodes, showTarget]);

  // A view can hold a thousand rows (every customer of a month): the grid pages client-side, the server sends all.
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [mobileShown, setMobileShown] = useState(MOBILE_PAGE);
  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    setMobileShown(MOBILE_PAGE);
    // Keyed on what identifies an answer, not the object (a refetch of the same board keeps your page).
  }, [data?.basis, data?.by, data?.total.amount, data?.rows.length]);

  const table = useReactTable({
    columns,
    data: rows,
    state: { pagination },
    onPaginationChange: setPagination,
    getPaginationRowModel: getPaginationRowModel(),
    getRowId: (row) => String(row.rank),
    getCoreRowModel: getCoreRowModel(),
    // The server returns the ranking; the order is the point.
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const filterControls = (idPrefix: string) => (
    <>
      <div className="w-full sm:w-44">
        <Label htmlFor={`${idPrefix}-company`}>Company</Label>
        <SearchableSelect
          id={`${idPrefix}-company`}
          value={setup.company}
          onChange={(company: string) => navigate({ company })}
          options={options?.companies ?? []}
          placeholder="All"
          triggerClassName="mt-1 w-full"
          clearable
        />
      </div>
      <div className="w-full sm:w-56">
        <Label htmlFor={`${idPrefix}-brand`}>Brand</Label>
        <SearchableMultiSelect
          id={`${idPrefix}-brand`}
          value={setup.brand}
          onChange={(brand: string[]) => navigate({ brand })}
          options={options?.brands ?? []}
          placeholder="Any"
          triggerClassName="mt-1 w-full"
        />
      </div>
      <div className="w-full sm:w-56">
        <Label htmlFor={`${idPrefix}-category`}>Category</Label>
        <SearchableMultiSelect
          id={`${idPrefix}-category`}
          value={setup.category}
          onChange={(category: string[]) => navigate({ category })}
          options={options?.categories ?? []}
          placeholder="Any"
          triggerClassName="mt-1 w-full"
        />
      </div>
      <div className="w-full sm:w-56">
        <Label htmlFor={`${idPrefix}-channel`}>Channel</Label>
        <SearchableMultiSelect
          id={`${idPrefix}-channel`}
          value={setup.channel}
          onChange={(channel: string[]) => navigate({ channel })}
          options={(options?.channels ?? NO_CHANNELS)[setup.basis] ?? []}
          placeholder="Any"
          triggerClassName="mt-1 w-full"
        />
      </div>
    </>
  );

  // A new period or filter is loading behind the old board (kept as placeholder data).
  const refreshing = isFetching && Boolean(data);
  const firstLoad = (restoring || runnable) && !data && !isError && (restoring || isLoading || isFetching);
  const empty = runnable && !restoring && !isLoading && !isError && rows.length === 0;

  const visibleViews = VIEWS.filter((v) => v.value === 'person' || v.value === setup.by || can[setup.basis]);
  const periodChips = setup.basis === 'outstanding' ? [{ kind: 'all_open' as Period, label: 'All open' }, ...PERIOD_CHIPS] : PERIOD_CHIPS;

  const chips: { id: string; text: string; remove: () => void }[] = [
    ...setup.person.map((label) => ({
      id: `person:${label}`,
      text: `Sales person: ${label}`,
      remove: () => navigate({ person: setup.person.filter((p) => p !== label) }),
    })),
    ...(setup.customer.length
      ? [{
          id: 'customer',
          text: setup.customerLabel ? `Customer: ${setup.customerLabel}` : 'Customer',
          remove: () => navigate({ customer: [], customerLabel: '' }),
        }]
      : []),
    ...(setup.product.length
      ? [{
          id: 'product',
          text: setup.productLabel ? `Product: ${setup.productLabel}` : 'Product',
          remove: () => navigate({ product: [], productLabel: '' }),
        }]
      : []),
  ];

  const openRow = (row: LeaderboardRow) => {
    const patch = drillOf(row);
    if (patch) navigate(patch);
  };

  const mobileAll = dataBy === 'person' ? rows.slice(3) : rows;
  const mobileRows = mobileAll.slice(0, mobileShown);
  const showReportLinks = Boolean(data) || runnable;

  return (
    <>
      <Container>
        <PageHeader title="Sales leaderboard" />
        {data?.as_of ? (
          <p className="mt-1 text-xs text-muted-foreground" data-testid="leaderboard-as-of">
            Data as of {formatDateTimeInMalaysia(data.as_of)}
          </p>
        ) : null}
      </Container>
      <Container>
        <div className="space-y-4 pb-20 md:pb-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Basis">
              {BASES.map((b) => (
                <Button
                  key={b.value}
                  type="button"
                  size="sm"
                  variant={setup.basis === b.value ? 'primary' : 'outline'}
                  aria-pressed={setup.basis === b.value}
                  className="h-7 px-2.5"
                  onClick={() => navigate({ basis: b.value })}
                >
                  {b.label}
                </Button>
              ))}
            </div>
            {showReportLinks ? (
              <div className="flex items-center gap-3 text-sm">
                {setup.basis === 'invoiced' && setup.by === 'product' ? (
                  <Link href={topSellingHref(setup)} className="text-primary hover:underline">
                    Open in Top selling items
                  </Link>
                ) : null}
                <Link href={reportHref(setup)} className="text-primary hover:underline">
                  Open as report
                </Link>
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Period">
              {periodChips.map((chip) => (
                <Button
                  key={chip.kind}
                  type="button"
                  size="sm"
                  variant={setup.period === chip.kind ? 'primary' : 'outline'}
                  aria-pressed={setup.period === chip.kind}
                  className="h-7 px-2.5"
                  onClick={() => navigate({ period: chip.kind })}
                >
                  {chip.label}
                </Button>
              ))}
            </div>
            {refreshing ? (
              <span role="status" data-testid="leaderboard-loading" className="flex h-7 items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Updating board
              </span>
            ) : null}
            <div className="hidden flex-wrap items-end gap-3 md:flex">{filterControls('lb')}</div>
            <div className="md:hidden">
              <Popover>
                <PopoverTrigger asChild>
                  <Button type="button" size="sm" variant="outline" className="h-7 px-2.5">
                    <SlidersHorizontal className="size-3.5" />
                    Filters{activeFilters ? ` (${activeFilters})` : ''}
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-72 space-y-3">
                  {filterControls('lb-m')}
                </PopoverContent>
              </Popover>
            </div>
          </div>

          {setup.period === 'custom' ? (
            <div className="w-full sm:w-72">
              <Label htmlFor="lb-range">Dates</Label>
              <DateRangePicker
                id="lb-range"
                aria-label="Custom date range"
                from={setup.from}
                to={setup.to}
                onChange={(next) => navigate({ from: next.from ?? '', to: next.to ?? '' })}
                className="mt-1"
              />
            </div>
          ) : null}

          <Tabs value={setup.by} onValueChange={(by) => navigate({ by: by as LeaderboardBy })}>
            <TabsList variant="line">
              {visibleViews.map((v) => (
                <TabsTrigger key={v.value} value={v.value}>
                  {v.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {chips.length ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {chips.map((chip) => (
                <Badge key={chip.id} variant="secondary" appearance="light" className="gap-1">
                  <span>{chip.text}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${chip.text}`}
                    className="rounded-sm opacity-60 hover:opacity-100"
                    onClick={chip.remove}
                  >
                    <X className="size-3" />
                  </button>
                </Badge>
              ))}
            </div>
          ) : null}

          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load the leaderboard.'}
            </div>
          ) : null}

          {setup.period === 'custom' && !runnable ? (
            <div
              data-testid="leaderboard-pick-range"
              className="flex flex-col items-center gap-1 rounded-lg border border-border py-10 text-center"
            >
              <span className="text-sm font-medium">Pick a date range</span>
              <span className="text-sm text-muted-foreground">Choose a start and an end date.</span>
            </div>
          ) : null}

          {firstLoad ? (
            <div className="space-y-4" data-testid="leaderboard-skeleton" aria-busy="true">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))}
              </div>
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          ) : null}

          <div
            data-testid="leaderboard-board"
            aria-busy={refreshing}
            className={cn('space-y-4', refreshing && 'opacity-50 transition-opacity')}
          >
          {data ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="leaderboard-kpis">
              <StatCard
                label={`Total ${BASIS_WORD[dataBasis]}`}
                value={formatRm(data.total.amount)}
                sub={
                  data.total.change_pct === null || data.total.change_pct === undefined ? undefined : (
                    <span className={changeTone(data.total.change_pct)}>
                      {formatChange(data.total.change_pct)} vs {versus} ({formatRm(data.total.prev_amount ?? 0)})
                    </span>
                  )
                }
              />
              {dataBy === 'person' ? (
                <StatCard
                  label="Sales persons ranked"
                  value={rows.length}
                  sub={`plus ${formatRm(data.no_agent_amount)} with no agent`}
                />
              ) : (
                <StatCard label="Customers" value={data.total.customers ?? 0} />
              )}
              {dataBy === 'person' && data.me ? (
                <StatCard
                  label="Your rank"
                  value={`#${data.me.rank}`}
                  sub={
                    myRow ? (
                      <span className={changeTone(myRow.change_pct)}>
                        {formatRm(myRow.amount)}
                        {outstanding ? '' : `, ${formatChange(myRow.change_pct)} vs ${versus}`}
                      </span>
                    ) : undefined
                  }
                />
              ) : dataBy !== 'person' ? (
                <StatCard label="Items" value={data.total.products ?? 0} />
              ) : null}
            </div>
          ) : null}

          {!runnable || isError || firstLoad ? null : empty ? (
            <div
              data-testid="leaderboard-empty"
              className="flex flex-col items-center gap-1 rounded-lg border border-border py-10 text-center"
            >
              <span className="text-sm font-medium">No sales in this period</span>
              <span className="text-sm text-muted-foreground">Try another period or clear the filters.</span>
            </div>
          ) : (
            <>
              {dataBy === 'person' ? <LeaderboardPodium rows={rows} versus={versus} showChange={!outstanding} /> : null}

              <div className="md:hidden" data-testid="leaderboard-list">
                {mobileRows.map((row) => {
                  const label = row.person ?? row.name;
                  const drill = drillOf(row);
                  const codes = dataBy === 'person' ? codesText(label, row.codes ?? []) : '';
                  const sub = dataBy === 'customer' ? [row.code, (row.companies ?? []).join(', ')].filter(Boolean).join(', ') : codes;
                  const Row = drill ? 'button' : 'div';
                  return (
                    <Row
                      key={row.rank}
                      {...(drill ? { type: 'button' as const, onClick: () => navigate(drill) } : {})}
                      className={cn(
                        'flex w-full items-start justify-between gap-3 border-b border-border py-2 text-start text-sm',
                        row.is_me && 'bg-primary/5 -mx-4 px-4',
                        drill && 'cursor-pointer',
                      )}
                    >
                      <div className="min-w-0">
                        <p className="truncate">
                          <b className="tabular-nums">{row.rank}</b> {label}
                          {row.is_me ? ' (you)' : ''}
                        </p>
                        {sub ? <p className="truncate text-xs text-muted-foreground">{sub}</p> : null}
                        {!outstanding ? (
                          <p className={cn('text-xs', changeTone(row.change_pct))}>
                            {row.change_pct === null ? '-' : `${formatChange(row.change_pct)} vs ${versus}`}
                          </p>
                        ) : null}
                        {dataBy === 'person' && row.target ? (
                          <p className="truncate text-xs text-muted-foreground">{targetText(row.target)}</p>
                        ) : null}
                      </div>
                      <span className="shrink-0 tabular-nums">{formatAmount(row.amount)}</span>
                    </Row>
                  );
                })}
                {mobileAll.length > mobileRows.length ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={() => setMobileShown((n) => n + MOBILE_PAGE)}
                  >
                    Show more ({mobileAll.length - mobileRows.length})
                  </Button>
                ) : null}
              </div>

              <div className="hidden md:block">
                <DataGrid
                  table={table}
                  recordCount={rows.length}
                  isLoading={isLoading}
                  isPlaceholderData={isPlaceholderData}
                  listingKey="sales.leaderboard.view"
                  tableLayout={{ width: 'fixed', columnsResizable: true }}
                  onRowClick={openRow}
                  rowClassName={(row) => (row.is_me ? 'bg-primary/5' : undefined)}
                  rowAttributes={(row) => ({
                    'data-me': row.is_me ? 'true' : undefined,
                    'data-drill': drillOf(row) ? 'true' : undefined,
                  })}
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
              </div>
            </>
          )}

          </div>

          {data && dataBy === 'person' ? (
            <p className="text-xs text-muted-foreground" data-testid="leaderboard-no-agent">
              Sales with no agent: {formatRm(data.no_agent_amount)} (not ranked)
            </p>
          ) : null}
        </div>
      </Container>
    </>
  );
}
