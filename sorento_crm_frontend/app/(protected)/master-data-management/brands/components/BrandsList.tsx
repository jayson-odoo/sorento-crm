'use client';

import { useMemo, useState } from 'react';
import {
  RowSelectionState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { useBrands } from '../hooks/useBrands';
import { buildBrandColumns } from './BrandTable';
import BrandFormDialog from './BrandFormDialog';
import BrandDeleteDialog from './BrandDeleteDialog';
import type { Brand } from '../types/brand.types';

export default function BrandsList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [formOpen, setFormOpen] = useState(false);
  const [editingBrandId, setEditingBrandId] = useState<string | undefined>(undefined);
  const [copyFromBrand, setCopyFromBrand] = useState<Brand | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [brandToDelete, setBrandToDelete] = useState<Brand | null>(null);

  const { data, isLoading } = useBrands({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'brand_name', desc: false }],
    searchQuery: '',
  });
  const handleEdit = (brand: Brand) => {
    setCopyFromBrand(null);
    setEditingBrandId(brand.id);
    setFormOpen(true);
  };

  const handleDuplicate = (brand: Brand) => {
    setEditingBrandId(undefined);
    setCopyFromBrand(brand);
    setFormOpen(true);
  };

  const handleDelete = (brand: Brand) => {
    setBrandToDelete(brand);
    setDeleteDialogOpen(true);
  };

  const handleFormClose = (open: boolean) => {
    setFormOpen(open);
    if (!open) {
      setEditingBrandId(undefined);
      setCopyFromBrand(null);
    }
  };

  // Search + status are filtered client-side (the list loads up to 100 brands).
  const filteredBrands = useMemo(() => {
    const brands = data?.data ?? [];
    const q = searchQuery.toLowerCase();
    return brands.filter((b) => {
      const matchesSearch =
        !q ||
        b.brand_name?.toLowerCase().includes(q) ||
        b.brand_code?.toLowerCase().includes(q);
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'active' ? b.is_active : !b.is_active);
      return matchesSearch && matchesStatus;
    });
  }, [data, searchQuery, statusFilter]);

  const columns = useMemo(
    () => buildBrandColumns({ onEdit: handleEdit, onDuplicate: handleDuplicate, onDelete: handleDelete }),
    [],
  );

  const table = useReactTable({
    columns,
    data: filteredBrands,
    getRowId: (row) => row.id,
    state: { rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });

  const statusActive = statusFilter !== 'all';

  return (
    <>
      <DataGrid
        table={table}
        recordCount={filteredBrands.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search brands..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="ps-9 w-64"
                  />
                  {searchQuery && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                      onClick={() => setSearchQuery('')}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: statusActive,
                activeCount: statusActive ? 1 : 0,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label>Status</Label>
                      <Select
                        value={statusFilter}
                        onValueChange={(v) => setStatusFilter(v as 'all' | 'active' | 'inactive')}
                      >
                        <SelectTrigger className="mt-1">
                          <SelectValue placeholder="All statuses" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All statuses</SelectItem>
                          <SelectItem value="active">Active</SelectItem>
                          <SelectItem value="inactive">Inactive</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {statusActive && (
                      <div className="flex justify-end">
                        <Button variant="ghost" size="sm" onClick={() => setStatusFilter('all')}>
                          Clear filters
                        </Button>
                      </div>
                    )}
                  </div>
                ),
              }}
              exportConfig={{ filename: 'brands_export.xlsx' }}
              primaryAction={
                <Button
                  onClick={() => {
                    setCopyFromBrand(null);
                    setEditingBrandId(undefined);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="size-4" />
                  Create Brand
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      <BrandFormDialog
        open={formOpen}
        onOpenChange={handleFormClose}
        brandId={editingBrandId}
        copyFromBrand={copyFromBrand}
      />

      {brandToDelete && (
        <BrandDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setBrandToDelete(null);
          }}
          brand={brandToDelete}
        />
      )}
    </>
  );
}
