'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  RowSelectionState,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useNumberingRules } from '../hooks/useNumberingRules';
import type { DocumentNumberingRule } from '../types/numberingRule.types';
import { DOC_TYPE_LABELS, RESET_POLICY_OPTIONS } from '../types/numberingRule.types';
import NumberingRuleEditDialog from './NumberingRuleEditDialog';
import { Pencil } from 'lucide-react';

const RESET_LABELS: Record<string, string> = Object.fromEntries(
  RESET_POLICY_OPTIONS.map((o) => [o.value, o.label]),
);

export default function NumberingRulesList() {
  const { data: rules, isLoading, isError, error } = useNumberingRules();
  const [editRule, setEditRule] = useState<DocumentNumberingRule | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const isForbidden =
    isError &&
    error instanceof Error &&
    (error.message.toLowerCase().includes('forbidden') || error.message.includes('403'));

  const columns = useMemo<ColumnDef<DocumentNumberingRule>[]>(
    () => [
      buildSelectColumn<DocumentNumberingRule>(),
      {
        accessorKey: 'doc_type',
        header: ({ column }) => <DataGridColumnHeader title="Document type" column={column} />,
        cell: ({ row }) => (
          <span className="font-medium">
            {DOC_TYPE_LABELS[row.original.doc_type] ?? row.original.doc_type}
          </span>
        ),
        size: 180,
        meta: { headerTitle: 'Document type', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'enabled',
        header: ({ column }) => <DataGridColumnHeader title="Enabled" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.enabled ? 'success' : 'secondary'}>
            {row.original.enabled ? 'Yes' : 'No'}
          </Badge>
        ),
        size: 100,
        meta: { headerTitle: 'Enabled' },
      },
      {
        accessorKey: 'prefix_template',
        header: ({ column }) => <DataGridColumnHeader title="Prefix" column={column} />,
        cell: ({ row }) => row.original.prefix_template ?? '-',
        size: 160,
        meta: { headerTitle: 'Prefix' },
      },
      {
        accessorKey: 'number_digits',
        header: ({ column }) => <DataGridColumnHeader title="Digits" column={column} />,
        size: 80,
        meta: { headerTitle: 'Digits' },
      },
      {
        accessorKey: 'next_value',
        header: ({ column }) => <DataGridColumnHeader title="Next value" column={column} />,
        size: 100,
        meta: { headerTitle: 'Next value' },
      },
      {
        accessorKey: 'reset_policy',
        header: ({ column }) => <DataGridColumnHeader title="Reset" column={column} />,
        cell: ({ row }) => RESET_LABELS[row.original.reset_policy] ?? row.original.reset_policy,
        size: 100,
        meta: { headerTitle: 'Reset' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setEditRule(row.original);
              setDialogOpen(true);
            }}
            aria-label="Edit"
          >
            <Pencil className="size-4" />
          </Button>
        ),
        size: 80,
        enableHiding: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rules ?? [],
    getRowId: (row) => row.id,
    state: { rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isForbidden) {
    return (
      <Card>
        <CardTable>
          <div className="p-8 text-center text-muted-foreground">
            <p className="font-medium">You don&apos;t have permission to view running numbers.</p>
            <p className="text-sm mt-1">Ask your administrator to assign the &quot;View Running Numbers&quot; permission to your role.</p>
          </div>
        </CardTable>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <DataGrid
          table={table}
          recordCount={rules?.length ?? 0}
          isLoading={isLoading}
          tableLayout={{ columnsVisibility: true }}
        >
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              exportConfig={{ filename: 'numbering_rules_export.xlsx' }}
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </DataGrid>
      </Card>
      <NumberingRuleEditDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) setEditRule(null);
        }}
        rule={editRule}
      />
    </>
  );
}
