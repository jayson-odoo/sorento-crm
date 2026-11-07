'use client';

import { Trash2 } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import type { Accessory } from '../types/accessory.types';

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "3 products, 1 combo". */
export function usedOnText(row: Pick<Accessory, 'product_count' | 'combo_count'>): string {
  return `${plural(row.product_count, 'product', 'products')}, ${plural(row.combo_count, 'combo', 'combos')}`;
}

export function buildAccessoryColumns(handlers: {
  onDelete?: (accessory: Accessory) => void;
}): ColumnDef<Accessory>[] {
  const { onDelete } = handlers;
  return [
    {
      id: 'picture',
      header: ({ column }) => <DataGridColumnHeader title="Picture" column={column} />,
      size: 90,
      enableSorting: false,
      meta: { headerTitle: 'Picture' },
      cell: ({ row }) =>
        row.original.image ? (
          <img
            src={row.original.image.url}
            alt=""
            className="size-10 rounded-md border object-cover"
          />
        ) : (
          <span className="text-xs text-muted-foreground">No picture</span>
        ),
    },
    {
      id: 'name',
      accessorFn: (row) => row.name,
      header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
      size: 260,
      enableSorting: false,
      meta: { headerTitle: 'Name' },
      cell: ({ row }) => (
        <span className="block truncate font-medium" title={row.original.name}>
          {row.original.name}
        </span>
      ),
    },
    {
      id: 'spec',
      accessorFn: (row) => row.spec ?? '',
      header: ({ column }) => <DataGridColumnHeader title="Spec" column={column} />,
      size: 280,
      enableSorting: false,
      meta: { headerTitle: 'Spec' },
      cell: ({ row }) => (
        <span
          className="block truncate text-muted-foreground"
          title={row.original.spec ?? undefined}
        >
          {row.original.spec ?? '-'}
        </span>
      ),
    },
    {
      id: 'used_on',
      accessorFn: (row) => usedOnText(row),
      header: ({ column }) => <DataGridColumnHeader title="Used on" column={column} />,
      size: 200,
      enableSorting: false,
      meta: { headerTitle: 'Used on' },
      cell: ({ row }) => <span className="block truncate">{usedOnText(row.original)}</span>,
    },
    ...(onDelete
      ? [
          {
            id: 'actions',
            header: '',
            size: 70,
            enableSorting: false,
            enableHiding: false,
            enableResizing: false,
            meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
            cell: ({ row }) => (
              <RowActionsMenu
                ariaLabel={`accessory ${row.original.name}`}
                actions={[
                  {
                    key: 'accessory.delete',
                    label: 'Delete accessory',
                    icon: Trash2,
                    kind: 'destructive' as const,
                    run: () => onDelete(row.original),
                  },
                ]}
              />
            ),
          } satisfies ColumnDef<Accessory>,
        ]
      : []),
  ];
}
