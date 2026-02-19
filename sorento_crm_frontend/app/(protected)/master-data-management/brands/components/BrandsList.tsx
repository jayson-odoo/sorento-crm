'use client';

import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useBrands } from '../hooks/useBrands';
import BrandTable from './BrandTable';
import BrandFormDialog from './BrandFormDialog';
import BrandDeleteDialog from './BrandDeleteDialog';
import type { Brand } from '../types/brand.types';

export default function BrandsList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingBrandId, setEditingBrandId] = useState<string | undefined>(
    undefined,
  );
  const [copyFromBrand, setCopyFromBrand] = useState<Brand | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [brandToDelete, setBrandToDelete] = useState<Brand | null>(null);

  const { data, isLoading } = useBrands({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'brand_name', desc: false }],
    searchQuery: '',
  });
  const brands = data?.data ?? [];

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

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-2.5">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search brands..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
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
        </CardHeader>
        <CardTable>
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              Loading brands...
            </div>
          ) : (
            <ScrollArea>
              <BrandTable
                brands={brands}
                searchQuery={searchQuery}
                onEdit={handleEdit}
                onDuplicate={handleDuplicate}
                onDelete={handleDelete}
              />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardTable>
      </Card>

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
