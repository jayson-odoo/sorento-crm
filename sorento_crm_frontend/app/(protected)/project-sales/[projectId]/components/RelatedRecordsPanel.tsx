'use client';

import { withProjectBack } from '../../_shared/lib/reviewOrigin';
import * as React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type {
  ColumnDef,
  PaginationState,
  SortingState,
  Updater,
} from '@tanstack/react-table';
import { HandCoins } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { formatDate } from '@/lib/helpers';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { formatStatusLabel } from '@/lib/status-badge';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  useProjectRelatedRecords,
  useSponsorshipRollup,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  RelatedRecordRow,
  RelatedRecordsParams,
} from '../../_shared/types/project.types';
import { formatMyr } from './QuotationsPanel';
import { RELATED_RECORD_TYPES } from './relatedRecordTypes';

const PAGE_SIZE = 25;
const DEFAULT_SORTING: SortingState = [{ id: 'date', desc: true }];

/**
 * The grid's state in the project page's address bar (owner rule "Filters & search" 3), so Back
 * from a record lands on the same page, sort, search and filters. Prefixed: the page's own
 * `page` / `sort` / `query` belong to the projects list it was opened from (prev/next).
 */
const URL_KEYS = {
  page: 'rel_page',
  limit: 'rel_limit',
  sort: 'rel_sort',
  dir: 'rel_dir',
  query: 'rel_query',
  type: 'rel_type',
  status: 'rel_status',
} as const;

function stateFromUrl(sp: URLSearchParams, initialTypes?: string[]) {
  const page = Number(sp.get(URL_KEYS.page) || '1');
  const limit = Number(sp.get(URL_KEYS.limit) || String(PAGE_SIZE));
  const sort = sp.get(URL_KEYS.sort);
  const sorting: SortingState =
    sort === 'none'
      ? []
      : sort
        ? [{ id: sort, desc: sp.get(URL_KEYS.dir) !== 'asc' }]
        : DEFAULT_SORTING;
  const urlTypes = splitMulti(sp.get(URL_KEYS.type) ?? '');
  return {
    pagination: {
      pageIndex: Number.isFinite(page) && page > 1 ? page - 1 : 0,
      pageSize: Number.isFinite(limit) && limit > 0 ? limit : PAGE_SIZE,
    },
    sorting,
    search: sp.get(URL_KEYS.query) ?? '',
    types: urlTypes.length ? urlTypes : (initialTypes ?? []),
    statuses: splitMulti(sp.get(URL_KEYS.status) ?? ''),
  };
}

/** The grid's opening read: Date, newest first, page one, no filter (AC-A4). */
const OPENING_PARAMS: RelatedRecordsParams = {
  pageIndex: 0,
  pageSize: PAGE_SIZE,
  sorting: [{ id: 'date', desc: true }],
  types: [],
  statuses: [],
};

/**
 * The Related tab's badge (AC-A1): every linked row this viewer may see, with no filter.
 * The same query the grid opens with, so the tab costs no second request.
 */
export function RelatedTabCount({ projectId, enabled }: { projectId: string; enabled: boolean }) {
  const { data } = useProjectRelatedRecords(projectId, OPENING_PARAMS, { enabled });
  const count = Object.values(data?.type_counts ?? {}).reduce((sum, n) => sum + n, 0);
  if (!count) return null;
  return (
    <Badge variant="secondary" appearance="light" aria-label={`${count} related records`}>
      {count}
    </Badge>
  );
}

function Dash() {
  return <span className="text-muted-foreground">-</span>;
}

function TextCell({ text }: { text: string | null }) {
  return text ? (
    <span className="block truncate text-sm" title={text}>
      {text}
    </span>
  ) : (
    <Dash />
  );
}

/** A status pill in the record type's own words and colours (a complaint reads as on its own
 *  page, `lib/complaint-status.ts`), else the shared ones. */
function Pill({ status, kind }: { status: string | null; kind?: string }) {
  if (!status) return <Dash />;
  const def = kind ? RELATED_RECORD_TYPES[kind] : undefined;
  const label = (def?.statusLabel ?? formatStatusLabel)(status);
  const tone = (def?.statusPillClass ?? statusPillClass)(status);
  // A type that names its own statuses ("Processed by CS") is shown as written; the shared
  // base capitalizes, which is right only for the generic labels.
  const base = def?.statusLabel
    ? STATUS_PILL_BASE.replace(/\bcapitalize\b/, 'normal-case')
    : STATUS_PILL_BASE;
  return (
    <span className={`${base} ${tone} truncate`} title={label}>
      {label}
    </span>
  );
}

/**
 * Every record linked to this project, one grid (PROJECT-RELATED-RECORDS): stock inquiries,
 * complaints, purchase requests, sponsorship forms and new product applications. Sorted,
 * searched, filtered and paged on the server; a row opens its own record.
 *
 * The types and their labels come from the API's `types` (what this viewer may see) and the
 * frontend registry (`relatedRecordTypes.ts`), so a new type needs no edit here (AC-D1).
 * The sponsorship spend line stays on top, as it was on the Sponsorship Form tab (AC-A10).
 */
export function RelatedRecordsPanel({
  project,
  initialTypes,
}: {
  project: Project;
  /** The Type filter to open with (`?tab=sponsorships` opens on Sponsorship form, AC-A2). */
  initialTypes?: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlKey = searchParams.toString();
  const [opening] = React.useState(() => stateFromUrl(new URLSearchParams(urlKey), initialTypes));
  const [sorting, setSorting] = React.useState<SortingState>(opening.sorting);
  const [pagination, setPagination] = React.useState<PaginationState>(opening.pagination);
  const [search, setSearch] = React.useState(opening.search);
  const [types, setTypes] = React.useState<string[]>(opening.types);
  const [statuses, setStatuses] = React.useState<string[]>(opening.statuses);
  const searchQuery = useDebouncedValue(search.trim(), 300);

  // Mirror the grid's state into the address bar, keeping every other param (the tab, the
  // projects list's own prev/next query). Only its own `rel_*` params, and only while the page
  // shows Related: the tab is the page's to write, so a tab click (or Back into another tab)
  // is never written over while this panel is still mounted.
  React.useEffect(() => {
    const next = new URLSearchParams(urlKey);
    const tab = next.get('tab');
    if (tab !== 'related' && tab !== 'sponsorships') return;
    // The retired Sponsorship Form tab's links open Related: the alias becomes its own name.
    if (tab === 'sponsorships') next.set('tab', 'related');
    for (const key of Object.values(URL_KEYS)) next.delete(key);
    if (pagination.pageIndex > 0) next.set(URL_KEYS.page, String(pagination.pageIndex + 1));
    if (pagination.pageSize !== PAGE_SIZE) next.set(URL_KEYS.limit, String(pagination.pageSize));
    const sort = sorting[0];
    if (!sort) next.set(URL_KEYS.sort, 'none');
    else if (sort.id !== DEFAULT_SORTING[0].id || !sort.desc) {
      next.set(URL_KEYS.sort, sort.id);
      next.set(URL_KEYS.dir, sort.desc ? 'desc' : 'asc');
    }
    if (searchQuery) next.set(URL_KEYS.query, searchQuery);
    if (types.length) next.set(URL_KEYS.type, joinMulti(types));
    if (statuses.length) next.set(URL_KEYS.status, joinMulti(statuses));
    const qs = next.toString();
    if (qs !== urlKey) router.replace(`${pathname}?${qs}`, { scroll: false });
  }, [urlKey, pathname, router, pagination, sorting, searchQuery, types, statuses]);

  const related = useProjectRelatedRecords(project.id, {
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: searchQuery || undefined,
    types,
    statuses,
  });
  const data = related.data;
  // The spend line is sponsorship data: asked for only when this viewer may see sponsorship
  // forms (the API's `types`, own_scope.request_access), as the rows are (AC-B2).
  const seesSponsorships = Boolean(data?.types?.some((t) => t.kind === 'sponsorship_form'));
  const rollup = useSponsorshipRollup(project.id, { enabled: seesSponsorships });

  const rows = React.useMemo(() => data?.data ?? [], [data]);
  const apiTypes = React.useMemo(() => data?.types ?? [], [data]);
  const apiLabels = React.useMemo(
    () => Object.fromEntries(apiTypes.map((t) => [t.kind, t.label])),
    [apiTypes],
  );
  const linkedCount = Object.values(data?.type_counts ?? {}).reduce((sum, n) => sum + n, 0);
  const filtering = types.length > 0 || statuses.length > 0 || searchQuery !== '';

  // A filter or sort change starts again from page one; page three of the old order means nothing.
  const firstPage = () => setPagination((current) => ({ ...current, pageIndex: 0 }));
  const onSortingChange = (updater: Updater<SortingState>) => {
    setSorting(updater);
    firstPage();
  };
  const filterCount = (types.length ? 1 : 0) + (statuses.length ? 1 : 0);
  const clearFilters = () => {
    setTypes([]);
    setStatuses([]);
    firstPage();
  };

  const typeOptions = apiTypes.map((t) => ({ value: t.kind, label: t.label }));
  const typeLabel = (kind: string) =>
    apiLabels[kind] ?? RELATED_RECORD_TYPES[kind]?.label ?? kind;
  const filterSummary = [
    types.length ? `Type: ${types.map(typeLabel).join(', ')}` : '',
    statuses.length ? `Status: ${statuses.map(formatStatusLabel).join(', ')}` : '',
  ]
    .filter(Boolean)
    .join('; ');
  const statusOptions = Array.from(new Set([...(data?.statuses ?? []), ...statuses])).map(
    (status) => ({ value: status, label: formatStatusLabel(status) }),
  );

  const columns = React.useMemo<ColumnDef<RelatedRecordRow>[]>(
    () => [
      {
        id: 'type',
        accessorFn: (row) => row.kind,
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (
          <TextCell
            text={
              RELATED_RECORD_TYPES[row.original.kind]?.label ??
              apiLabels[row.original.kind] ??
              row.original.kind
            }
          />
        ),
        size: 190,
        meta: { headerTitle: 'Type' },
      },
      {
        id: 'number',
        accessorFn: (row) => row.number ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Number" column={column} />,
        cell: ({ row }) =>
          row.original.number ? (
            <span className="block truncate text-sm font-medium" title={row.original.number}>
              {row.original.number}
            </span>
          ) : (
            <Dash />
          ),
        size: 150,
        meta: { headerTitle: 'Number' },
      },
      {
        id: 'status',
        accessorFn: (row) => row.status ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => <Pill status={row.original.status} kind={row.original.kind} />,
        size: 150,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'approval',
        accessorFn: (row) => row.approval_status ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Approval" column={column} />,
        cell: ({ row }) => <Pill status={row.original.approval_status} />,
        size: 130,
        meta: { headerTitle: 'Approval' },
      },
      {
        id: 'date',
        accessorFn: (row) => row.date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        cell: ({ row }) =>
          row.original.date ? (
            <span className="block truncate text-sm" title={formatDate(row.original.date)}>
              {formatDate(row.original.date)}
            </span>
          ) : (
            <Dash />
          ),
        size: 120,
        meta: { headerTitle: 'Date' },
      },
      {
        id: 'raised_by',
        accessorFn: (row) => row.raised_by ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Raised by" column={column} />,
        cell: ({ row }) => <TextCell text={row.original.raised_by} />,
        size: 170,
        meta: { headerTitle: 'Raised by' },
      },
      {
        id: 'subject',
        accessorFn: (row) => row.subject ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Subject" column={column} />,
        cell: ({ row }) => <TextCell text={row.original.subject} />,
        size: 280,
        meta: { headerTitle: 'Subject' },
      },
      {
        id: 'value',
        accessorFn: (row) => row.value ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        cell: ({ row }) =>
          row.original.value === null || row.original.value === undefined ? (
            <Dash />
          ) : (
            <span className="block truncate text-sm tabular-nums">
              {formatMyr(String(row.original.value))}
            </span>
          ),
        size: 140,
        meta: { headerTitle: 'Value' },
      },
    ],
    [apiLabels],
  );

  const spend =
    seesSponsorships && rollup.data && rollup.data.form_count > 0 ? rollup.data : null;

  return (
    <div className="space-y-3">
      {spend && (
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" appearance="light" className="gap-1">
            <HandCoins className="size-3" aria-hidden />
            {`Sponsorship spend: ${formatMyr(spend.total)} across ${spend.form_count} form${spend.form_count === 1 ? '' : 's'}`}
          </Badge>
          {spend.by_year.map((year) => (
            <span
              key={year.year}
              className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground"
            >
              <span className="font-medium text-foreground">{year.year}</span>{' '}
              {formatMyr(year.total)}
            </span>
          ))}
        </div>
      )}
      <PanelDataGrid
        toolbar={({ table }) => (
          <DataGridListToolbar
            table={table}
            exportConfig={false}
            searchSlot={
              <ListSearchInput
                type="search"
                value={search}
                onChange={(value) => {
                  setSearch(value);
                  firstPage();
                }}
                placeholder="Search number, subject, raised by"
                aria-label="Search related records"
                className="w-full sm:w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: filterCount > 0,
              activeCount: filterCount,
              activeSummary: filterSummary
                ? { label: filterSummary, onClear: clearFilters }
                : undefined,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Type</Label>
                    <SearchableMultiSelect
                      value={types}
                      onChange={(value) => {
                        setTypes(value);
                        firstPage();
                      }}
                      options={typeOptions}
                      placeholder="All types"
                      aria-label="Type"
                      triggerClassName="mt-1 w-full"
                      clearable
                    />
                  </div>
                  <div>
                    <Label>Status</Label>
                    <SearchableMultiSelect
                      value={statuses}
                      onChange={(value) => {
                        setStatuses(value);
                        firstPage();
                      }}
                      options={statusOptions}
                      placeholder="All statuses"
                      aria-label="Status"
                      triggerClassName="mt-1 w-full"
                      clearable
                    />
                  </div>
                </div>
              ),
            }}
          />
        )}
        columns={columns}
        rows={rows}
        getRowId={(row) => `${row.kind}:${row.id}`}
        listingKey="projects.projects.view::project-related-records"
        isLoading={related.isLoading}
        isPlaceholderData={related.isPlaceholderData}
        error={related.isError ? related.error : undefined}
        onRetry={() => void related.refetch()}
        serverSorting={{ sorting, onSortingChange }}
        serverPaging={{
          pagination,
          onPaginationChange: setPagination,
          rowCount: data?.pagination.total ?? 0,
        }}
        emptyTitle={
          filtering && linkedCount > 0 ? 'Nothing matches these filters' : 'No related records'
        }
        emptyBody={
          filtering && linkedCount > 0
            ? undefined
            : 'Records show here once their Project field names this project.'
        }
        onRowClick={(row) => {
          const def = RELATED_RECORD_TYPES[row.kind];
          if (!def) return;
          // Every record's page reads `?back=` (BackToList originLabel): its Back returns to this
          // project's Related tab. A sponsorship form names the retired tab, which opens Related
          // filtered to sponsorship forms, where its Cancel and Submit land too.
          router.push(
            withProjectBack(
              def.href(row.id),
              project.id,
              row.kind === 'sponsorship_form' ? 'sponsorships' : 'related',
            ),
          );
        }}
      />
    </div>
  );
}
