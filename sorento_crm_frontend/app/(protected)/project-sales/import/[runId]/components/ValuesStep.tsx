'use client';

import * as React from 'react';
import { ChevronDown } from 'lucide-react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type RowSelectionState,
  type SortingState,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { formatDateSafe } from '@/lib/helpers';
import {
  useProjectImportLines,
  useProjectImportLinesSummary,
  useProjectImportMutations,
} from '../../../_shared/hooks/useProjectImport';
import type {
  ProjectImportAction,
  ProjectImportKind,
  ProjectImportLine,
  ProjectImportRun,
} from '../../../_shared/types/projectImport.types';
import { KIND_TABS } from '../../components/importLabels';
import { ACTION_LABELS, ACTIONS_BY_KIND, LineChoiceDialog, type LineChoice } from './LineChoiceDialog';

const STATUS_FILTER = [
  { value: 'todo', label: 'To do' },
  { value: 'set', label: 'Set' },
];

const SOURCE_WORDS: Record<string, string> = { saved: 'Saved', so: 'From SO' };

function lineKey(line: ProjectImportLine): string {
  return `${line.customer_value_key}\u0001${line.value_key}`;
}

function linkedTo(line: ProjectImportLine): string {
  if (line.status === 'todo' || !line.action) return 'To do';
  if (line.action === 'link') return line.target_label ?? 'Linked';
  if (line.action === 'create') return line.new_title ? `New: ${line.new_title}` : 'Create new';
  return ACTION_LABELS[line.action];
}

function setBy(line: ProjectImportLine): string {
  if (!line.source) return '';
  return [SOURCE_WORDS[line.source] ?? '', line.set_by_name, line.set_at ? formatDateSafe(line.set_at) : '']
    .filter(Boolean)
    .join(', ');
}

type Pending = { action: 'link' | 'create'; lines: ProjectImportLine[]; viaBulk: boolean };

/** The Values step (AC-PI-46): one tab per kind, one line per value in the file. */
export function ValuesStep({
  run,
  kind: kindProp,
  onKindChange,
  readOnly = false,
}: {
  run: ProjectImportRun;
  kind?: ProjectImportKind;
  onKindChange?: (kind: ProjectImportKind) => void;
  readOnly?: boolean;
}) {
  const [ownKind, setOwnKind] = React.useState<ProjectImportKind>(kindProp ?? 'customer');
  const kind = kindProp ?? ownKind;
  const setKind = (next: ProjectImportKind) => {
    setOwnKind(next);
    onKindChange?.(next);
  };
  const summary = useProjectImportLinesSummary(run.id);
  const { value: search, setValue: setSearch, debouncedValue, isSettling } = useDebouncedSearch();
  const [status, setStatus] = React.useState('');
  const [pagination, setPagination] = React.useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = React.useState<SortingState>([{ id: 'rows', desc: true }]);
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const [pending, setPending] = React.useState<Pending | null>(null);

  React.useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    setRowSelection({});
  }, [kind, status, debouncedValue]);

  const lines = useProjectImportLines(
    run.id,
    kind,
    { ...pagination, sorting, searchQuery: debouncedValue },
    status ? { status: status as 'todo' | 'set' } : {},
  );
  const { line: setOne, bulk } = useProjectImportMutations(run.id);
  const items = React.useMemo(() => lines.data?.items ?? [], [lines.data]);
  const total = lines.data?.total ?? 0;

  // The bulk "Set to" is ONE call with every ticked key; a line's own menu sets that line.
  const apply = async (targets: ProjectImportLine[], choice: LineChoice, viaBulk: boolean) => {
    if (!targets.length) return;
    if (!viaBulk) {
      const [only] = targets;
      await setOne.mutateAsync({
        kind,
        customer_value_key: only.customer_value_key,
        value_key: only.value_key,
        ...choice,
      });
    } else {
      await bulk.mutateAsync({
        kind,
        keys: targets.map((l) => [l.customer_value_key, l.value_key] as [string, string]),
        ...choice,
      });
    }
    setRowSelection({});
  };

  const choose = (targets: ProjectImportLine[], action: ProjectImportAction, viaBulk = false) => {
    if (action === 'link' || (action === 'create' && kind === 'project')) {
      setPending({ action, lines: targets, viaBulk });
      return;
    }
    void apply(targets, { action, target_id: null, new_title: null }, viaBulk).catch(() => undefined);
  };

  const actions = ACTIONS_BY_KIND[kind];

  const columns = React.useMemo<ColumnDef<ProjectImportLine>[]>(() => {
    const out: ColumnDef<ProjectImportLine>[] = [];
    if (!readOnly) {
      out.push(buildSelectColumn<ProjectImportLine>({ rowLabel: (row) => `Select ${row.original.value_text ?? ''}` }));
    }
    if (kind === 'project') {
      out.push({
        accessorKey: 'customer_text',
        header: ({ column }) => <DataGridColumnHeader title="Customer in file" column={column} />,
        size: 220,
        meta: { headerTitle: 'Customer in file', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer_text ?? ''}>
            {row.original.customer_text}
          </span>
        ),
      });
    }
    out.push(
      {
        accessorKey: 'value_text',
        header: ({ column }) => <DataGridColumnHeader title="Value in file" column={column} />,
        size: 260,
        meta: { headerTitle: 'Value in file', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.value_text ?? ''}>
            {row.original.value_text}
          </span>
        ),
      },
      {
        accessorKey: 'rows',
        header: ({ column }) => <DataGridColumnHeader title="Rows" column={column} />,
        size: 80,
        meta: { headerTitle: 'Rows' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.rows}</span>,
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Linked to" column={column} />,
        size: 260,
        meta: { headerTitle: 'Linked to' },
        cell: ({ row }) => {
          const label = linkedTo(row.original);
          const todo = label === 'To do';
          if (readOnly) {
            return (
              <span className={todo ? 'text-muted-foreground' : 'block truncate'} title={label}>
                {label}
              </span>
            );
          }
          return (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 max-w-full justify-between gap-1 px-2"
                  aria-label={`Change ${row.original.value_text ?? ''}`}
                >
                  <span className={todo ? 'truncate text-muted-foreground' : 'truncate'} title={label}>
                    {label}
                  </span>
                  <ChevronDown className="size-3.5 shrink-0" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {actions.map((action) => (
                  <DropdownMenuItem key={action} onSelect={() => choose([row.original], action)}>
                    {ACTION_LABELS[action]}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          );
        },
      },
      {
        accessorKey: 'set_at',
        header: ({ column }) => <DataGridColumnHeader title="Set by" column={column} />,
        size: 240,
        meta: { headerTitle: 'Set by' },
        cell: ({ row }) => {
          const text = setBy(row.original);
          return (
            <span className="block truncate text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
      },
    );
    return out;
    // `choose` reads the current kind; the columns are rebuilt whenever it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, readOnly, actions]);

  const table = useReactTable({
    columns,
    data: items,
    getRowId: lineKey,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: !readOnly,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  const ticked = items.filter((l) => rowSelection[lineKey(l)]);

  const bulkMenu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={!ticked.length || bulk.isPending}>
          Set to
          <ChevronDown className="size-3.5" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {actions.map((action) => (
          <DropdownMenuItem key={action} onSelect={() => choose(ticked, action, true)}>
            {ACTION_LABELS[action]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <div className="space-y-4">
      <Tabs value={kind} onValueChange={(next) => setKind(next as ProjectImportKind)}>
        <TabsList variant="line" className="w-full justify-start overflow-x-auto">
          {KIND_TABS.map((tab) => {
            const todo = summary.data?.[tab.kind]?.todo ?? 0;
            return (
              <TabsTrigger key={tab.kind} value={tab.kind}>
                <span>
                  {tab.label}
                  {todo > 0 && <span className="ms-1.5 text-xs text-muted-foreground">{`${todo} to do`}</span>}
                </span>
              </TabsTrigger>
            );
          })}
        </TabsList>
      </Tabs>

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={lines.isLoading}
        error={lines.error}
        onRetry={() => void lines.refetch()}
        isPlaceholderData={lines.isPlaceholderData}
        listingKey={`projects.import.view::values-${kind}`}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-semibold">
              {status || debouncedValue ? 'No values match' : 'No values of this kind in the file'}
            </p>
          </div>
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  isSettling={isSearchInFlight(isSettling, lines.isFetching, debouncedValue)}
                  placeholder="Search values"
                  aria-label="Search values"
                  className="w-full sm:w-56 md:w-64"
                />
              }
              filters={{
                kind: 'custom',
                active: Boolean(status),
                activeCount: status ? 1 : 0,
                content: (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Show</Label>
                    <SearchableSelect
                      value={status}
                      onChange={setStatus}
                      options={STATUS_FILTER}
                      clearable
                      placeholder="Every value"
                      aria-label="Show"
                    />
                  </div>
                ),
              }}
              exportConfig={false}
              showColumns={false}
              keepSearchWhileSelected
              bulkActionsSlot={readOnly ? undefined : bulkMenu}
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

      {pending && (
        <LineChoiceDialog
          open
          kind={kind}
          action={pending.action}
          title={
            pending.lines.length === 1
              ? (pending.lines[0].value_text ?? '')
              : `${pending.lines.length} values`
          }
          initialTitle={pending.action === 'create' ? pending.lines[0]?.value_text : null}
          busy={setOne.isPending || bulk.isPending}
          onCancel={() => setPending(null)}
          onSave={(choice) =>
            void apply(pending.lines, choice, pending.viaBulk)
              .then(() => setPending(null))
              .catch(() => undefined)
          }
        />
      )}
    </div>
  );
}

export default ValuesStep;
