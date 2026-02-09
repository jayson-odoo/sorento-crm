'use client';

import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCategoriesTree } from '../hooks/useProductCategories';
import CategoryTree from './CategoryTree';
import CategoryForm from './CategoryForm';
import CategoryDeleteDialog from './category-delete-dialog';
import type { CategoryTreeItem } from '../types/category.types';

export default function CategoriesList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingCategoryId, setEditingCategoryId] = useState<string | undefined>(undefined);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [categoryToDelete, setCategoryToDelete] = useState<CategoryTreeItem | null>(null);
  const { data: categories, isLoading } = useCategoriesTree();

  const handleEdit = (category: CategoryTreeItem) => {
    setEditingCategoryId(category.id);
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
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search categories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
          <Button onClick={() => {
            setEditingCategoryId(undefined);
            setFormOpen(true);
          }}>
            <Plus className="size-4" />
            Create Category
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">Loading categories...</div>
          ) : (
            <CategoryTree
              categories={categories || []}
              searchQuery={searchQuery}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <CategoryForm
        open={formOpen}
        onOpenChange={handleFormClose}
        categoryId={editingCategoryId}
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
    </div>
  );
}
