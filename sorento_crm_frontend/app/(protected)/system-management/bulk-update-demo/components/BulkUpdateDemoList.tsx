'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { ChevronDown, PencilLine } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { BulkUpdateDialog, type BulkEditableField } from '@/components/common/BulkUpdateDialog';
import { mockBulkUpdate, type MockTask } from '../services/bulkUpdateService';

// ---- Mock fixtures (Phase-1: no backend) ------------------------------------

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'resolved', label: 'Resolved' },
];

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'med', label: 'Medium' },
  { value: 'high', label: 'High' },
];

// User-select STUB (Phase 2 swaps in services/userSelectService). Labels are
// human names — no UUIDs surface in the UI.
const ASSIGNEE_OPTIONS = [
  { value: 'u-aisha', label: 'Aisha Rahman' },
  { value: 'u-ben', label: 'Ben Tan' },
  { value: 'u-carla', label: 'Carla Mendes' },
  { value: 'u-deepak', label: 'Deepak Rao' },
];

const STATUS_LABEL: Record<string, string> = Object.fromEntries(
  STATUS_OPTIONS.map((o) => [o.value, o.label]),
);
const PRIORITY_LABEL: Record<string, string> = Object.fromEntries(
  PRIORITY_OPTIONS.map((o) => [o.value, o.label]),
);
const ASSIGNEE_LABEL: Record<string, string> = Object.fromEntries(
  ASSIGNEE_OPTIONS.map((o) => [o.value, o.label]),
);

function seedTasks(): MockTask[] {
  const names = [
    'Follow up on damaged carton',
    'Reconcile March GRN variance',
    'Chase supplier ETA — pallet racking',
    'Verify promotion artwork',
    'Refund request review',
    'Update stock count sheet',
    'Escalate late delivery',
    'Approve purchase requisition',
    'Investigate missing SKU',
    'Close resolved complaint',
    'Draft weekly ops summary',
    'Audit cold-chain log',
    'Reassign overdue ticket',
    'Confirm customer address',
    'Archive Q1 shipping docs',
  ];
  const statuses = ['open', 'in_progress', 'resolved'];
  const priorities = ['low', 'med', 'high'];
  const assignees = ASSIGNEE_OPTIONS.map((a) => a.value);
  return names.map((name, i) => ({
    id: `task-${String(i + 1).padStart(3, '0')}`,
    name,
    status: statuses[i % statuses.length],
    priority: priorities[i % priorities.length],
    assignee: assignees[i % assignees.length],
  }));
}

// Whitelist of bulk-editable fields for THIS list (the safety boundary).
const BULK_FIELDS: BulkEditableField[] = [
  {
    key: 'status',
    label: 'Status',
    type: 'select',
    options: STATUS_OPTIONS,
    helpText: 'Rows already Resolved cannot transition to another status.',
  },
  { key: 'priority', label: 'Priority', type: 'select', options: PRIORITY_OPTIONS },
  {
    key: 'assignee',
    label: 'Assignee',
    type: 'user',
    options: ASSIGNEE_OPTIONS,
    helpText: 'Reassign the selected tasks to one person.',
  },
];

function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'resolved') return 'success';
  if (status === 'in_progress') return 'warning';
  return 'secondary';
}

function priorityVariant(priority: string): 'destructive' | 'warning' | 'secondary' {
  if (priority === 'high') return 'destructive';
  if (priority === 'med') return 'warning';
  return 'secondary';
}

export default function BulkUpdateDemoList() {
  const [tasks, setTasks] = useState<MockTask[]>(() => seedTasks());
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkOpen, setBulkOpen] = useState(false);

  const columns = useMemo<ColumnDef<MockTask>[]>(
    () => [
      buildSelectColumn<MockTask>(),
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Task" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block max-w-[320px]" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        size: 320,
        meta: { headerTitle: 'Task' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={statusVariant(row.original.status)} appearance="ghost">
            {STATUS_LABEL[row.original.status] ?? row.original.status}
          </Badge>
        ),
        size: 130,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'priority',
        header: ({ column }) => <DataGridColumnHeader title="Priority" column={column} />,
        cell: ({ row }) => (
          <Badge variant={priorityVariant(row.original.priority)} appearance="ghost">
            {PRIORITY_LABEL[row.original.priority] ?? row.original.priority}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Priority' },
      },
      {
        accessorKey: 'assignee',
        header: ({ column }) => <DataGridColumnHeader title="Assignee" column={column} />,
        cell: ({ row }) => ASSIGNEE_LABEL[row.original.assignee] ?? row.original.assignee,
        size: 180,
        meta: { headerTitle: 'Assignee' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: tasks,
    getRowId: (row) => row.id,
    state: { pagination, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const selectedIds = selectedRowIds(table);

  const handleApply = async (fieldKey: string, value: string) => {
    const selectedRows = tasks.filter((t) => selectedIds.includes(t.id));
    const result = await mockBulkUpdate(selectedRows, fieldKey, value);

    // Optimistically reflect the (mock) update in the grid for the rows that
    // were NOT skipped, so the demo shows the effect of the bulk edit.
    const skippedIds = new Set(result.skipped.map((s) => s.id));
    setTasks((prev) =>
      prev.map((t) =>
        selectedIds.includes(t.id) && !skippedIds.has(t.id)
          ? { ...t, [fieldKey]: value }
          : t,
      ),
    );
    setRowSelection({});
    toast.success(
      `Bulk update applied — ${result.updated} updated${
        result.skipped.length ? `, ${result.skipped.length} skipped` : ''
      }.`,
    );
    return result;
  };

  return (
    <>
      <DataGrid
        table={table}
        recordCount={tasks.length}
        tableLayout={{ columnsVisibility: true, width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              exportConfig={false}
              bulkActionsSlot={() => (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="gap-1.5">
                      Action
                      <ChevronDown className="size-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuItem onClick={() => setBulkOpen(true)}>
                      <PencilLine className="size-4 me-2" /> Bulk update…
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <BulkUpdateDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        selectedCount={selectedIds.length}
        fields={BULK_FIELDS}
        onApply={handleApply}
      />
    </>
  );
}
