'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useCategoriesTree } from '../hooks/useProductCategories';
import CategoryTree from './CategoryTree';
import CategoryForm from './CategoryForm';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import type { CategoryTreeItem } from '../types/category.types';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

export default function CategoriesList() {
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
  } = useDebouncedSearch();
  const [formOpen, setFormOpen] = useState(false);
  const [editingCategoryId, setEditingCategoryId] = useState<string | undefined>(undefined);
  const [copyFromCategory, setCopyFromCategory] = useState<CategoryTreeItem | null>(null);
  const { data: categories, isLoading } = useCategoriesTree();

  // Delete asks nothing (D7): a toast counts down with Cancel, and a category
  // that still holds products is refused by the server when the window lapses.
  const deletion = useDeferredRowAction({
    actionKey: 'product_category.delete',
    entityType: 'product_category',
    successMessage: 'Category deleted',
    invalidateKeys: [['product-categories-tree'], ['product-category-select']],
  });

  const handleDuplicate = (category: CategoryTreeItem) => {
    setEditingCategoryId(undefined);
    setCopyFromCategory(category);
    setFormOpen(true);
  };

  const handleDelete = (category: CategoryTreeItem) => {
    deletion.run({
      id: category.id,
      subject: `${category.category_name} (${category.category_code})`,
    });
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
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <ListSearchInput
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search categories..."
            className="w-64"
          />
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
    </>
  );
}
