'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, PaginationState, SortingState } from '@tanstack/react-table';
import { FlaskConical, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ContextMenuItem } from '@/components/ui/context-menu';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { splitMulti, joinMulti } from '@/lib/list-filters/multiValue';
import { useKindOptions, useRules } from '../hooks/useWarrantyConfig';
import { useInitialListState, useWriteListUrl } from '../hooks/useListUrlState';
import { formatMatchTypeLabel } from '../lib/warrantyLabels';
import type { WarrantyRule } from '../types/warranty.types';
import { Text } from './PoliciesTab';
import { RuleFormDialog } from './RuleFormDialog';
import { RuleTesterDialog } from './RuleTesterDialog';
import WarrantyGrid from './WarrantyGrid';

export function RulesTab() {
  const initial = useInitialListState();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: initial.pageIndex, pageSize: initial.pageSize });
  const [sorting, setSorting] = useState<SortingState>(initial.sorting.length ? initial.sorting : [{ id: 'kind', desc: false }]);
  const search = useDebouncedSearch(initial.searchQuery);
  const [kindFilter, setKindFilter] = useState<string[]>(splitMulti(initial.filters.kind_id));
  useWriteListUrl(
    { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery: search.debouncedValue },
    { kind_id: kindFilter.length ? joinMulti(kindFilter) : undefined },
  );
  const [form, setForm] = useState<{ open: boolean; rule: WarrantyRule | null }>({ open: false, rule: null });
  const [testing, setTesting] = useState(false);
  const remove = useDeferredRowAction({
    actionKey: 'warranty_kind_rule.delete',
    entityType: 'warranty_kind_rule',
    verb: 'Deleting',
    successMessage: 'Rule deleted.',
    invalidateKeys: [['warranty-rules'], ['warranty-kinds'], ['warranty-kind-rule-counts']],
  });
  const { data: kinds = [] } = useKindOptions();
  const { data, isLoading, isFetching, isPlaceholderData, refetch, error } = useRules({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: search.debouncedValue,
    kind_id: kindFilter,
  });

  const columns = useMemo<ColumnDef<WarrantyRule>[]>(() => {
    const col = (id: string, title: string, size: number, cell: (r: WarrantyRule) => React.ReactNode): ColumnDef<WarrantyRule> => ({
      id,
      header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
      size,
      cell: ({ row }) => cell(row.original),
      meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-20" /> },
    });
    return [
      col('kind', 'Kind', 240, (r) => <Text value={r.kind_name} className="font-medium" />),
      col('match_type', 'Match', 130, (r) => <Text value={formatMatchTypeLabel(r.match_type)} />),
      col('match_value', 'Value', 320, (r) => <Text value={r.match_value} />),
      col('priority', 'Priority', 90, (r) => <Text value={String(r.priority)} />),
    ];
  }, []);

  return (
    <>
      <WarrantyGrid<WarrantyRule>
        rows={data?.data ?? []}
        total={data?.pagination.total ?? 0}
        columns={columns}
        pagination={pagination}
        onPaginationChange={setPagination}
        sorting={sorting}
        onSortingChange={setSorting}
        search={{
          value: search.value,
          onChange: search.setValue,
          settling: search.isSettling,
          query: search.debouncedValue,
          placeholder: 'Search rules...',
        }}
        isLoading={isLoading}
        isFetching={isFetching}
        isPlaceholderData={isPlaceholderData}
        error={error}
        refetch={() => void refetch()}
        empty={{ title: 'No rules', hint: 'A rule maps products to a kind.' }}
        filters={{
          kind: 'custom',
          active: kindFilter.length > 0,
          activeCount: kindFilter.length ? 1 : 0,
          content: (
            <div>
              <Label>Kind</Label>
              <SearchableMultiSelect
                value={kindFilter}
                onChange={setKindFilter}
                options={kinds.map((k) => ({ value: k.id, label: k.name }))}
                placeholder="All kinds"
                triggerClassName="mt-1"
                clearable
              />
            </div>
          ),
        }}
        leftActions={
          <Button variant="outline" onClick={() => setTesting(true)}>
            <FlaskConical />
            Test a product
          </Button>
        }
        primaryAction={
          <Button onClick={() => setForm({ open: true, rule: null })}>
            <Plus />
            Create
          </Button>
        }
        menu={(r) => (
          <>
            <ContextMenuItem onSelect={() => setForm({ open: true, rule: r })}>Edit</ContextMenuItem>
            <ContextMenuItem
              onSelect={() =>
                remove.run({ id: r.id, subject: `${r.kind_name}: ${formatMatchTypeLabel(r.match_type)} ${r.match_value}` })
              }
            >
              Delete
            </ContextMenuItem>
          </>
        )}
      />
      <RuleFormDialog open={form.open} onOpenChange={(open) => setForm((f) => ({ ...f, open }))} rule={form.rule} />
      <RuleTesterDialog open={testing} onOpenChange={setTesting} />
    </>
  );
}
