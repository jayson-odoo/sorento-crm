'use client';

import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useCategoriesTree } from '../hooks/useProductCategories';
import CategoryTree from './CategoryTree';
import CategoryForm from './CategoryForm';
import CategoryDeleteDialog from './category-delete-dialog';
import type { CategoryTreeItem } from '../types/category.types';

export default function CategoriesList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingCategoryId, setEditingCategoryId] = useState<string | undefined>(undefined);
  const [copyFromCategory, setCopyFromCategory] = useState<CategoryTreeItem | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [categoryToDelete, setCategoryToDelete] = useState<CategoryTreeItem | null>(null);
  const { data: categories, isLoading } = useCategoriesTree();

  const handleEdit = (category: CategoryTreeItem) => {
    setCopyFromCategory(null);
    setEditingCategoryId(category.id);
    setFormOpen(true);
  };

  const handleDuplicate = (category: CategoryTreeItem) => {
    setEditingCategoryId(undefined);
    setCopyFromCategory(category);
    setFormOpen(true);
  };

  const handleDelete = (category: CategoryTreeItem) => {
    setCategoryToDelete(category);
    setDeleteDialogOpen(true);
  };

  const handleFormClose = (open: boolean) => {
    setFormOpen(open);
    if (!open) {
      setEditingCategoryId(undefined);
      setCopyFromCategory(null);
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-2.5">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search categories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
          <Button
            onClick={() => {
              setCopyFromCategory(null);
              setEditingCategoryId(undefined);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            Create Category
          </Button>
        </CardHeader>
        <CardTable>
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              Loading categories...
            </div>
          ) : (
            <ScrollArea>
              <CategoryTree
                categories={categories || []}
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

      <CategoryForm
        open={formOpen}
        onOpenChange={handleFormClose}
        categoryId={editingCategoryId}
        copyFromCategory={copyFromCategory}
      />

      {categoryToDelete && (
        <CategoryDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setCategoryToDelete(null);
          }}
          category={categoryToDelete}
        />
      )}
    </>
  );
}
