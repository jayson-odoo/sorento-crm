'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, PaginationState, SortingState } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ContextMenuItem } from '@/components/ui/context-menu';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useKindRuleCounts, useKinds } from '../hooks/useWarrantyConfig';
import type { WarrantyKind } from '../types/warranty.types';
import { KindFormDialog } from './KindFormDialog';
import { Text } from './PoliciesTab';
import WarrantyGrid from './WarrantyGrid';

const ACTIVE_OPTIONS = [
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Archived' },
];

export function KindsTab() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const search = useDebouncedSearch();
  const [activeFilter, setActiveFilter] = useState<string[]>([]);
  const [noRuleOnly, setNoRuleOnly] = useState(false);
  const [form, setForm] = useState<{ open: boolean; kind: WarrantyKind | null }>({ open: false, kind: null });
  const invalidateKeys = [['warranty-kinds'], ['warranty-kind-rule-counts'], ['warranty-kind-options']] as const;
  const archive = useDeferredRowAction({
    actionKey: 'warranty_kind.archive',
    entityType: 'warranty_kind',
    verb: 'Archiving',
    successMessage: 'Kind archived.',
    invalidateKeys,
  });
  const remove = useDeferredRowAction({
    actionKey: 'warranty_kind.delete',
    entityType: 'warranty_kind',
    verb: 'Deleting',
    successMessage: 'Kind deleted.',
    invalidateKeys,
  });
  const { data: counts } = useKindRuleCounts();
  const { data, isLoading, isFetching, isPlaceholderData, refetch, error } = useKinds({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: search.debouncedValue,
    is_active: activeFilter,
    ...(noRuleOnly ? { has_no_rule: true } : {}),
  });

  const columns = useMemo<ColumnDef<WarrantyKind>[]>(() => {
    const col = (
      id: string,
      title: string,
      size: number,
      cell: (k: WarrantyKind) => React.ReactNode,
      sortable = true,
    ): ColumnDef<WarrantyKind> => ({
      id,
      header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
      size,
      enableSorting: sortable,
      cell: ({ row }) => cell(row.original),
      meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-20" /> },
    });
    return [
      col('name', 'Kind', 260, (k) => <Text value={k.name} className="font-medium" />),
      col('code', 'Code', 200, (k) => <Text value={k.code} />),
      col('rule_count', 'Rules', 90, (k) => <Text value={String(k.rule_count)} />),
      col('term_count', 'Terms', 90, (k) => <Text value={String(k.term_count)} />),
      col('is_active', 'Active', 110, (k) => (
        <Badge variant={k.is_active ? 'success' : 'secondary'} size="sm" className="shrink-0">
          {k.is_active ? 'Active' : 'Archived'}
        </Badge>
      )),
    ];
  }, []);

  const pill = counts ? (
    <button type="button" onClick={() => setNoRuleOnly((v) => !v)} aria-pressed={noRuleOnly} className="shrink-0">
      <Badge variant={noRuleOnly ? 'warning' : 'warning'} appearance={noRuleOnly ? 'default' : 'light'} size="sm">
        {`${counts.without} of ${counts.total} kinds have no rule`}
      </Badge>
    </button>
  ) : undefined;

  return (
    <>
      <WarrantyGrid<WarrantyKind>
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
          placeholder: 'Search kinds...',
        }}
        isLoading={isLoading}
        isFetching={isFetching}
        isPlaceholderData={isPlaceholderData}
        error={error}
        refetch={() => void refetch()}
        empty={{ title: 'No kinds', hint: 'Kinds group the products a policy gives terms to.' }}
        leftActions={pill}
        filters={{
          kind: 'custom',
          active: activeFilter.length > 0,
          activeCount: activeFilter.length ? 1 : 0,
          content: (
            <div>
              <Label>Status</Label>
              <SearchableMultiSelect
                value={activeFilter}
                onChange={setActiveFilter}
                options={ACTIVE_OPTIONS}
                placeholder="All kinds"
                triggerClassName="mt-1"
                clearable
              />
            </div>
          ),
        }}
        primaryAction={
          <Button onClick={() => setForm({ open: true, kind: null })}>
            <Plus />
            Create
          </Button>
        }
        menu={(k) => (
          <>
            <ContextMenuItem onSelect={() => setForm({ open: true, kind: k })}>Edit</ContextMenuItem>
            {k.is_active && (
              <ContextMenuItem onSelect={() => archive.run({ id: k.id, subject: k.name })}>Archive</ContextMenuItem>
            )}
            {k.rule_count === 0 && k.term_count === 0 && (
              <ContextMenuItem onSelect={() => remove.run({ id: k.id, subject: k.name })}>Delete</ContextMenuItem>
            )}
          </>
        )}
      />
      <KindFormDialog
        open={form.open}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        kind={form.kind}
      />
    </>
  );
}
