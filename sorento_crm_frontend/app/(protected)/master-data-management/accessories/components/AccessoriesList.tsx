'use client';

import { useMemo, useState } from 'react';
import { getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { useDeferredRowAction, useRowPending } from '@/hooks/useDeferredRowAction';
import { useAccessories } from '../hooks/useAccessories';
import { buildAccessoryColumns } from './AccessoryColumns';
import AccessoryFormDialog from './AccessoryFormDialog';
import type { Accessory } from '../types/accessory.types';

export default function AccessoriesList() {
  const canEdit = useHasPermission('master_data.products.edit');
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
  } = useDebouncedSearch();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Accessory | null>(null);
  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel. A 409 from
  // the server (still listed on products or combos) surfaces when the window lapses.
  const deletion = useDeferredRowAction({
    actionKey: 'accessory.delete',
    entityType: 'accessory',
    successMessage: 'Accessory deleted',
    invalidateKeys: [['accessories'], ['owner-accessories']],
  });
  const rowPending = useRowPending<Accessory>('accessory');

  const { data, isLoading, isPlaceholderData, error, refetch } = useAccessories({
    pageIndex: 0,
    pageSize: 100,
    sorting: [],
    searchQuery,
  });
  const rows = useMemo(() => data?.data ?? [], [data]);

  const columns = useMemo(
    () =>
      buildAccessoryColumns({
        onDelete: canEdit
          ? (accessory) => deletion.run({ id: accessory.id, subject: accessory.name })
          : undefined,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canEdit],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
  });

  const handleOpenChange = (open: boolean) => {
    setFormOpen(open);
    if (!open) setEditing(null);
  };

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination?.total ?? rows.length}
        isLoading={isLoading}
        error={error}
        onRetry={() => void refetch()}
        isPlaceholderData={isPlaceholderData}
        rowPending={rowPending}
        onRowClick={(row) => {
          setEditing(row);
          setFormOpen(true);
        }}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  placeholder="Search accessories..."
                  className="w-64"
                />
              }
              primaryAction={
                canEdit ? (
                  <Button
                    onClick={() => {
                      setEditing(null);
                      setFormOpen(true);
                    }}
                  >
                    <Plus className="size-4" />
                    Add accessory
                  </Button>
                ) : undefined
              }
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>

      <AccessoryFormDialog
        open={formOpen}
        onOpenChange={handleOpenChange}
        accessory={editing}
        canEdit={canEdit}
      />
    </>
  );
}
