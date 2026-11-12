'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef, PaginationState, SortingState } from '@tanstack/react-table';
import { HandCoins } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { formatDate } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  useProjectRelatedRecords,
  useSponsorshipRollup,
} from '../../_shared/hooks/useProjects';
import { useProjectRelatedRecords as useRelatedRecordsQuery } from '../../_shared/hooks/useProjectRelatedRecords';
import type {
  Project,
  RelatedRecordRow,
  RelatedRecordsParams,
} from '../../_shared/types/project.types';
import { formatMyr } from './QuotationsPanel';
import { RELATED_RECORD_TYPES } from './relatedRecordTypes';

const PAGE_SIZE = 25;

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
  const { data } = useRelatedRecordsQuery(projectId, OPENING_PARAMS, { enabled });
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

function Pill({ status }: { status: string | null }) {
  if (!status) return <Dash />;
  const label = formatStatusLabel(status);
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(status)} truncate`} title={label}>
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
  const [sorting, setSorting] = React.useState<SortingState>(OPENING_PARAMS.sorting ?? []);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: OPENING_PARAMS.pageIndex,
    pageSize: OPENING_PARAMS.pageSize,
  });
  const [search, setSearch] = React.useState('');
  const [types, setTypes] = React.useState<string[]>(initialTypes ?? []);
  const [statuses, setStatuses] = React.useState<string[]>([]);
  const searchQuery = useDebouncedValue(search.trim(), 300);

  const related = useProjectRelatedRecords(project.id, {
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: searchQuery || undefined,
    types,
    statuses,
  });
  const rollup = useSponsorshipRollup(project.id);

  const data = related.data;
  const rows = React.useMemo(() => data?.data ?? [], [data]);
  const apiTypes = React.useMemo(() => data?.types ?? [], [data]);
  const apiLabels = React.useMemo(
    () => Object.fromEntries(apiTypes.map((t) => [t.kind, t.label])),
    [apiTypes],
  );
  const linkedCount = Object.values(data?.type_counts ?? {}).reduce((sum, n) => sum + n, 0);
  const filtering = types.length > 0 || statuses.length > 0 || searchQuery !== '';

  // A filter change starts again from page one; page three of the old matches means nothing.
  const firstPage = () => setPagination((current) => ({ ...current, pageIndex: 0 }));

  const typeOptions = apiTypes.map((t) => ({ value: t.kind, label: t.label }));
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
        cell: ({ row }) => <Pill status={row.original.status} />,
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
            <span className="truncate text-sm">{formatDate(row.original.date)}</span>
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

  const spend = rollup.data && rollup.data.form_count > 0 ? rollup.data : null;

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
              <>
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
                {/* No types or statuses to choose from while nothing is linked. */}
                {linkedCount > 0 && (
                  <>
                    <SearchableMultiSelect
                      value={types}
                      onChange={(value) => {
                        setTypes(value);
                        firstPage();
                      }}
                      options={typeOptions}
                      placeholder="All types"
                      aria-label="Type"
                      triggerClassName="w-full sm:w-44"
                      clearable
                    />
                    <SearchableMultiSelect
                      value={statuses}
                      onChange={(value) => {
                        setStatuses(value);
                        firstPage();
                      }}
                      options={statusOptions}
                      placeholder="All statuses"
                      aria-label="Status"
                      triggerClassName="w-full sm:w-44"
                      clearable
                    />
                  </>
                )}
              </>
            }
          />
        )}
        columns={columns}
        rows={rows}
        getRowId={(row) => `${row.kind}:${row.id}`}
        listingKey="projects.projects.view::project-related-records"
        isLoading={related.isLoading}
        error={related.isError ? related.error : undefined}
        onRetry={() => void related.refetch()}
        serverSorting={{ sorting, onSortingChange: setSorting }}
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
          if (def) router.push(def.href(row.id));
        }}
      />
    </div>
  );
}
