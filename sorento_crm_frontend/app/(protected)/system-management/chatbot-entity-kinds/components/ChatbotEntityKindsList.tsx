'use client';

import { useMemo, useState } from 'react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useChatbotEntityKindsQuery } from '../hooks/useChatbotEntityKinds';
import {
  NARROWING_POLICY_OPTIONS,
} from '@/app/(protected)/system-management/chatbot-domains/types/chatbotDomain.types';
import type { ChatbotEntityKind } from '../types/chatbotEntityKind.types';
import ChatbotEntityKindModal from './ChatbotEntityKindModal';

export default function ChatbotEntityKindsList() {
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
  } = useDebouncedSearch();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCode, setEditingCode] = useState<string | null>(null);

  const { data, isLoading, isError } = useChatbotEntityKindsQuery();
  const kinds = useMemo(() => data ?? [], [data]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return kinds;
    return kinds.filter(
      (k) => k.code.toLowerCase().includes(q) || k.label.toLowerCase().includes(q),
    );
  }, [kinds, searchQuery]);

  const columns = useMemo<ColumnDef<ChatbotEntityKind>[]>(
    () => [
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Kind" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.code}</span>,
        size: 140,
        meta: { headerTitle: 'Kind' },
      },
      {
        id: 'resolved_against',
        header: ({ column }) => <DataGridColumnHeader title="Resolved against" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.resolved_against}>
            {row.original.resolved_against}
          </span>
        ),
        size: 260,
        meta: { headerTitle: 'Resolved against' },
      },
      {
        accessorKey: 'did_you_mean',
        header: ({ column }) => <DataGridColumnHeader title="Did-you-mean" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={row.original.did_you_mean ? 'success' : 'secondary'}
            appearance="light"
            size="sm"
          >
            {row.original.did_you_mean ? 'on' : 'off'}
          </Badge>
        ),
        size: 130,
        meta: { headerTitle: 'Did-you-mean' },
      },
      {
        id: 'default_narrowing',
        header: ({ column }) => <DataGridColumnHeader title="Default narrowing" column={column} />,
        cell: ({ row }) => {
          const label =
            NARROWING_POLICY_OPTIONS.find((o) => o.value === row.original.default_narrowing)
              ?.label ?? row.original.default_narrowing;
          return (
            <Badge variant="secondary" appearance="light" size="sm">
              {label}
            </Badge>
          );
        },
        size: 170,
        meta: { headerTitle: 'Default narrowing' },
      },
      {
        id: 'family_grouping',
        header: ({ column }) => <DataGridColumnHeader title="Family grouping" column={column} />,
        cell: ({ row }) => row.original.family_grouping ?? '-',
        size: 140,
        meta: { headerTitle: 'Family grouping' },
      },
      {
        id: 'base_property_words',
        header: ({ column }) => (
          <DataGridColumnHeader title="Base property words" column={column} />
        ),
        cell: ({ row }) => {
          const text =
            Object.entries(row.original.base_property_words)
              .map(([word, column]) => `${word} -> ${column}`)
              .join(', ') || '-';
          return (
            <span className="truncate block text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
        size: 260,
        meta: { headerTitle: 'Base property words' },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: filtered,
    columns,
    getRowId: (row) => row.code,
    getCoreRowModel: getCoreRowModel(),
  });

  const openCreate = () => {
    setEditingCode(null);
    setModalOpen(true);
  };

  const openEdit = (kind: ChatbotEntityKind) => {
    setEditingCode(kind.code);
    setModalOpen(true);
  };

  const listPrimaryAction = (
    <Button onClick={openCreate}>
      <Plus className="size-4" />
      Add kind
    </Button>
  );

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Entity kinds could not be loaded. Reload the page to try again.
      </p>
    );
  }

  return (
    <>
      <DataGrid
        table={table}
        recordCount={filtered.length}
        isLoading={isLoading}
        onRowClick={(row) => openEdit(row)}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyAction={listPrimaryAction}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  placeholder="Search entity kinds"
                  className="w-64"
                />
              }
              primaryAction={listPrimaryAction}
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>

      <ChatbotEntityKindModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        entityKindCode={editingCode}
        rows={filtered}
        onNavigate={(code) => setEditingCode(code)}
      />
    </>
  );
}
