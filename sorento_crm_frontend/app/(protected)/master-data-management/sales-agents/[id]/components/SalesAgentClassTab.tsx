'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import type { RecordAction } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { SALES_AGENT_CLASSES_PREFIX, useSalesAgentClasses } from '../../hooks/useSalesAgents';
import type { SalesAgentClassRow } from '../../types/salesAgent.types';
import SalesAgentClassModal from './SalesAgentClassModal';

function RowActions({ row, onEdit }: { row: SalesAgentClassRow; onEdit: (row: SalesAgentClassRow) => void }) {
  const deletion = useDeferredAction({
    actionKey: 'sales_agent_class.delete',
    entityType: 'sales_agent_class',
    entityId: row.id,
    verb: 'Deleting',
    subject: row.class_label,
    surface: 'toast',
    successMessage: 'Class deleted',
    invalidateKeys: [SALES_AGENT_CLASSES_PREFIX, ['sales-agent'], ['sales-agents']],
  });
  const actions: RecordAction[] = [
    { key: 'sales_agent_class.edit', label: 'Edit', icon: Pencil, run: () => onEdit(row) },
    {
      key: 'sales_agent_class.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    },
  ];
  return <RowActionsMenu actions={actions} ariaLabel="class" />;
}

/** Sales agent -> Class history: the agent's dated classes (Dealer, Project team, Other). */
export default function SalesAgentClassTab({ agentId }: { agentId: string }) {
  const canEdit = useHasPermission('master_data.sales_agents.edit');
  const { data, isLoading, isError, error } = useSalesAgentClasses(agentId);
  const rows = useMemo<SalesAgentClassRow[]>(() => data ?? [], [data]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SalesAgentClassRow | null>(null);

  const openEdit = (row: SalesAgentClassRow) => {
    setEditing(row);
    setModalOpen(true);
  };

  const columns = useMemo<ColumnDef<SalesAgentClassRow>[]>(
    () => [
      {
        accessorKey: 'class_label',
        header: ({ column }) => <DataGridColumnHeader title="Class" column={column} />,
        cell: ({ row }) => <span className="block truncate">{row.original.class_label}</span>,
        size: 200,
        meta: { headerTitle: 'Class', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'from_month',
        header: ({ column }) => <DataGridColumnHeader title="From month" column={column} />,
        cell: ({ row }) => row.original.from_month ?? 'From the beginning',
        size: 180,
        meta: { headerTitle: 'From month', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'to_month',
        header: ({ column }) => <DataGridColumnHeader title="To month" column={column} />,
        cell: ({ row }) => row.original.to_month ?? 'Open',
        size: 180,
        meta: { headerTitle: 'To month', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      ...(canEdit
        ? [
            {
              id: 'actions',
              header: '',
              cell: ({ row }) => <RowActions row={row.original} onEdit={openEdit} />,
              size: 56,
              enableSorting: false,
              enableResizing: false,
              meta: { headerTitle: 'Actions' },
            } as ColumnDef<SalesAgentClassRow>,
          ]
        : []),
    ],
    [canEdit],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <>
      {isError ? (
        <div className="mb-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load the class history.'}
        </div>
      ) : null}
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        listingKey="master_data.sales_agents.view::classes"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          <div className="flex w-full flex-col items-center gap-1 py-6">
            <span className="text-sm font-medium">No class history</span>
            <span className="text-sm text-muted-foreground">Classes added for this agent appear here.</span>
          </div>
        }
      >
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Class history</CardTitle>
            </CardHeading>
            {canEdit ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setEditing(null);
                  setModalOpen(true);
                }}
              >
                <Plus className="size-4" />
                Add class
              </Button>
            ) : null}
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>
      <SalesAgentClassModal agentId={agentId} open={modalOpen} onOpenChange={setModalOpen} row={editing} />
    </>
  );
}
