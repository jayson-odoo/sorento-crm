'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Loader2, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { StatCard } from '@/components/scm/StatCard';
import { useSalesLeaderboardOptionsQuery, useSalesLeaderboardQuery } from '@/hooks/useSalesLeaderboardQuery';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import type { LeaderboardOptions, LeaderboardRow } from '@/services/salesLeaderboardService';
import { LeaderboardPodium } from './LeaderboardPodium';
import {
  COLUMN_SIZES,
  changeTone,
  codesText,
  formatAmount,
  formatChange,
  formatRm,
  periodRange,
  previousLabel,
  type PeriodKind,
} from './leaderboardFormat';

const PERIOD_CHIPS: { kind: PeriodKind; label: string }[] = [
  { kind: 'this_month', label: 'This month' },
  { kind: 'last_month', label: 'Last month' },
  { kind: 'this_quarter', label: 'This quarter' },
  { kind: 'ytd', label: 'YTD' },
  { kind: 'custom', label: 'Custom' },
];

const NO_OPTIONS: LeaderboardOptions = { companies: [], brands: [], categories: [] };

/**
 * Sales > Leaderboard (PLAN-sales-leaderboard-07nov, UAC L1-L6). Read-only: no CTA, no subtitle.
 * Invoiced sales ranked by sales person; no target and no commission is shown here.
 */
export default function LeaderboardView() {
  const [period, setPeriod] = useState<PeriodKind>('this_month');
  const [custom, setCustom] = useState<{ from: string; to: string }>({ from: '', to: '' });
  const [company, setCompany] = useState('');
  const [brand, setBrand] = useState<string[]>([]);
  const [category, setCategory] = useState<string[]>([]);

  // Custom sends no previous window: the backend reads the same number of days just before.
  const range = useMemo<{ from: string; to: string; previousFrom?: string; previousTo?: string }>(
    () => (period === 'custom' ? custom : periodRange(period)),
    [period, custom],
  );
  const runnable = Boolean(range.from && range.to && range.to >= range.from);

  const options = useSalesLeaderboardOptionsQuery().data ?? NO_OPTIONS;
  const { data, isLoading, isFetching, isError, error } = useSalesLeaderboardQuery(
    {
      date_from: range.from,
      date_to: range.to,
      previous_from: range.previousFrom,
      previous_to: range.previousTo,
      company: company || undefined,
      brand,
      category,
    },
    runnable,
  );

  const rows = useMemo<LeaderboardRow[]>(() => data?.rows ?? [], [data]);
  const versus = data ? previousLabel(data.previous_from, data.previous_to) : 'previous period';
  const myRow = rows.find((row) => row.is_me);
  const activeFilters = (company ? 1 : 0) + (brand.length ? 1 : 0) + (category.length ? 1 : 0);

  const columns = useMemo<ColumnDef<LeaderboardRow>[]>(
    () => [
      {
        accessorKey: 'rank',
        header: ({ column }) => <DataGridColumnHeader title="Rank" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.rank}</span>,
        size: COLUMN_SIZES.rank,
        meta: { headerTitle: 'Rank', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        accessorKey: 'person',
        header: ({ column }) => <DataGridColumnHeader title="Sales person" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.person}>
            {row.original.person}
            {row.original.is_me ? ' (you)' : ''}
          </span>
        ),
        size: COLUMN_SIZES.person,
        meta: { headerTitle: 'Sales person', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'codes',
        header: ({ column }) => <DataGridColumnHeader title="Codes" column={column} />,
        cell: ({ row }) => {
          const text = codesText(row.original.person, row.original.codes);
          return (
            <span className="block truncate text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
        size: COLUMN_SIZES.codes,
        meta: { headerTitle: 'Codes', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'amount',
        header: ({ column }) => <DataGridColumnHeader title="Invoiced net (RM)" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{formatAmount(row.original.amount)}</span>,
        size: COLUMN_SIZES.amount,
        meta: {
          headerTitle: 'Invoiced net (RM)',
          headerClassName: 'text-end',
          cellClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-24" />,
        },
      },
      {
        accessorKey: 'change_pct',
        header: ({ column }) => <DataGridColumnHeader title="vs last period" column={column} />,
        cell: ({ row }) => (
          <span className={cn('tabular-nums', changeTone(row.original.change_pct))}>
            {formatChange(row.original.change_pct)}
          </span>
        ),
        size: COLUMN_SIZES.change,
        meta: {
          headerTitle: 'vs last period',
          headerClassName: 'text-end',
          cellClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-12" />,
        },
      },
      {
        accessorKey: 'customers',
        header: ({ column }) => <DataGridColumnHeader title="Customers" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.customers}</span>,
        size: COLUMN_SIZES.customers,
        meta: {
          headerTitle: 'Customers',
          headerClassName: 'text-end',
          cellClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-8" />,
        },
      },
    ],
    [],
  );

  // The Codes column only earns its width when some row has codes worth showing.
  const showCodes = rows.some((row) => codesText(row.person, row.codes) !== '');

  const table = useReactTable({
    columns,
    data: rows,
    state: { columnVisibility: { codes: showCodes } },
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
          value={company}
          onChange={setCompany}
          options={options.companies}
          placeholder="All"
          triggerClassName="mt-1 w-full"
          clearable
        />
      </div>
      <div className="w-full sm:w-56">
        <Label htmlFor={`${idPrefix}-brand`}>Brand</Label>
        <SearchableMultiSelect
          id={`${idPrefix}-brand`}
          value={brand}
          onChange={setBrand}
          options={options.brands}
          placeholder="Any"
          triggerClassName="mt-1 w-full"
        />
      </div>
      <div className="w-full sm:w-56">
        <Label htmlFor={`${idPrefix}-category`}>Category</Label>
        <SearchableMultiSelect
          id={`${idPrefix}-category`}
          value={category}
          onChange={setCategory}
          options={options.categories}
          placeholder="Any"
          triggerClassName="mt-1 w-full"
        />
      </div>
    </>
  );

  // A new period or filter is loading behind the old board (kept as placeholder data).
  const refreshing = isFetching && Boolean(data);
  const firstLoad = runnable && !data && !isError && (isLoading || isFetching);
  const empty = runnable && !isLoading && !isError && rows.length === 0;

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
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Period">
              {PERIOD_CHIPS.map((chip) => (
                <Button
                  key={chip.kind}
                  type="button"
                  size="sm"
                  variant={period === chip.kind ? 'primary' : 'outline'}
                  aria-pressed={period === chip.kind}
                  className="h-7 px-2.5"
                  onClick={() => setPeriod(chip.kind)}
                >
                  {chip.label}
                </Button>
              ))}
            </div>
            {refreshing ? (
              <span role="status" data-testid="leaderboard-loading" className="flex h-7 items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Loading
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

          {period === 'custom' ? (
            <div className="w-full sm:w-72">
              <Label htmlFor="lb-range">Dates</Label>
              <DateRangePicker
                id="lb-range"
                aria-label="Custom date range"
                from={custom.from}
                to={custom.to}
                onChange={(next) => setCustom({ from: next.from ?? '', to: next.to ?? '' })}
                className="mt-1"
              />
            </div>
          ) : null}

          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load the leaderboard.'}
            </div>
          ) : null}

          {period === 'custom' && !runnable ? (
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
                label="Total invoiced"
                value={formatRm(data.total.amount)}
                sub={
                  data.total.change_pct === null ? undefined : (
                    <span className={changeTone(data.total.change_pct)}>
                      {formatChange(data.total.change_pct)} vs {versus} ({formatRm(data.total.prev_amount)})
                    </span>
                  )
                }
              />
              <StatCard
                label="Sales persons ranked"
                value={rows.length}
                sub={`plus ${formatRm(data.no_agent_amount)} with no agent`}
              />
              {data.me ? (
                <StatCard
                  label="Your rank"
                  value={`#${data.me.rank}`}
                  sub={
                    myRow ? (
                      <span className={changeTone(myRow.change_pct)}>
                        {formatRm(myRow.amount)}, {formatChange(myRow.change_pct)} vs {versus}
                      </span>
                    ) : undefined
                  }
                />
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
              <LeaderboardPodium rows={rows} versus={versus} />

              <div className="md:hidden" data-testid="leaderboard-list">
                {rows.slice(3).map((row) => (
                  <div
                    key={row.rank}
                    className={cn(
                      'flex items-start justify-between gap-3 border-b border-border py-2 text-sm',
                      row.is_me && 'bg-primary/5 -mx-4 px-4',
                    )}
                  >
                    <div className="min-w-0">
                      <p className="truncate">
                        <b className="tabular-nums">{row.rank}</b> {row.person}
                        {row.is_me ? ' (you)' : ''}
                      </p>
                      {codesText(row.person, row.codes) ? (
                        <p className="truncate text-xs text-muted-foreground">{codesText(row.person, row.codes)}</p>
                      ) : null}
                      <p className={cn('text-xs', changeTone(row.change_pct))}>
                        {row.change_pct === null ? '-' : `${formatChange(row.change_pct)} vs ${versus}`}
                      </p>
                    </div>
                    <span className="shrink-0 tabular-nums">{formatAmount(row.amount)}</span>
                  </div>
                ))}
              </div>

              <div className="hidden md:block">
                <DataGrid
                  table={table}
                  recordCount={rows.length}
                  isLoading={isLoading}
                  listingKey="sales.leaderboard.view"
                  tableLayout={{ width: 'fixed', columnsResizable: true }}
                  rowClassName={(row) => (row.is_me ? 'bg-primary/5' : undefined)}
                  rowAttributes={(row) => ({ 'data-me': row.is_me ? 'true' : undefined })}
                >
                  <Card>
                    <CardTable>
                      <DataGridTable />
                    </CardTable>
                  </Card>
                </DataGrid>
              </div>
            </>
          )}

          </div>

          {data ? (
            <p className="text-xs text-muted-foreground" data-testid="leaderboard-no-agent">
              Sales with no agent: {formatRm(data.no_agent_amount)} (not ranked)
            </p>
          ) : null}
        </div>
      </Container>
    </>
  );
}
