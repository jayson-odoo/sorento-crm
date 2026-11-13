'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ColumnDef, PaginationState, SortingState } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ContextMenuItem } from '@/components/ui/context-menu';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Skeleton } from '@/components/ui/skeleton';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { usePolicies } from '../hooks/useWarrantyConfig';
import { POLICY_LIFECYCLE_LABEL, formatCivilDate, policyLifecycle } from '../lib/warrantyLabels';
import type { WarrantyPolicy } from '../types/warranty.types';
import { PolicyFormDialog } from './PolicyFormDialog';
import { SupersedeDialog } from './SupersedeDialog';
import WarrantyGrid from './WarrantyGrid';

const LIFECYCLE_VARIANT = { in_force: 'success', scheduled: 'info', superseded: 'secondary' } as const;

export function Text({ value, className }: { value: string | null | undefined; className?: string }) {
  return (
    <span className={`block truncate ${className ?? ''}`} title={value || undefined}>
      {value || '-'}
    </span>
  );
}

export function PoliciesTab() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'effective_from', desc: true }]);
  const search = useDebouncedSearch();
  const [form, setForm] = useState<{ open: boolean; policy: WarrantyPolicy | null }>({ open: false, policy: null });
  const [supersede, setSupersede] = useState<WarrantyPolicy | null>(null);
  const remove = useDeferredRowAction({
    actionKey: 'warranty_policy.delete',
    entityType: 'warranty_policy',
    verb: 'Deleting',
    successMessage: 'Policy deleted.',
    invalidateKeys: [['warranty-policies'], ['service-job'], ['service-jobs']],
  });
  const { data, isLoading, isFetching, isPlaceholderData, refetch, error } = usePolicies({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: search.debouncedValue,
  });

  const columns = useMemo<ColumnDef<WarrantyPolicy>[]>(() => {
    const col = (
      id: string,
      title: string,
      size: number,
      cell: (p: WarrantyPolicy) => React.ReactNode,
      sortable = true,
    ): ColumnDef<WarrantyPolicy> => ({
      id,
      header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
      size,
      enableSorting: sortable,
      cell: ({ row }) => cell(row.original),
      meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-20" /> },
    });
    return [
      col('version', 'Version', 140, (p) => (
        <Link
          href={`/after-sales/warranty/policies/${p.id}`}
          className="block truncate font-medium text-primary hover:underline"
          title={p.version}
        >
          {p.version}
        </Link>
      )),
      col('effective_from', 'In force from', 140, (p) => <Text value={formatCivilDate(p.effective_from)} />),
      col('effective_to', 'In force to', 140, (p) => <Text value={p.effective_to ? formatCivilDate(p.effective_to) : null} />),
      col(
        'status',
        'Status',
        120,
        (p) => {
          const state = policyLifecycle(p);
          return (
            <Badge variant={LIFECYCLE_VARIANT[state]} size="sm" className="shrink-0">
              {POLICY_LIFECYCLE_LABEL[state]}
            </Badge>
          );
        },
        false,
      ),
      col('terms', 'Terms', 90, (p) => <Text value={String(p.term_count)} />, false),
    ];
  }, []);

  return (
    <>
      <WarrantyGrid<WarrantyPolicy>
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
          placeholder: 'Search policies...',
        }}
        isLoading={isLoading}
        isFetching={isFetching}
        isPlaceholderData={isPlaceholderData}
        error={error}
        refetch={() => void refetch()}
        empty={{ title: 'No policies', hint: 'Create the first warranty policy version.' }}
        rowHref={(p) => `/after-sales/warranty/policies/${p.id}`}
        primaryAction={
          <Button onClick={() => setForm({ open: true, policy: null })}>
            <Plus />
            Create
          </Button>
        }
        menu={(p) => (
          <>
            <ContextMenuItem onSelect={() => setForm({ open: true, policy: p })}>Edit</ContextMenuItem>
            <ContextMenuItem onSelect={() => setSupersede(p)}>Supersede</ContextMenuItem>
            <ContextMenuItem onSelect={() => remove.run({ id: p.id, subject: `Policy ${p.version}` })}>
              Delete
            </ContextMenuItem>
          </>
        )}
      />
      <PolicyFormDialog
        open={form.open}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        policy={form.policy}
      />
      {supersede && (
        <SupersedeDialog open onOpenChange={(open) => !open && setSupersede(null)} policy={supersede} />
      )}
    </>
  );
}
