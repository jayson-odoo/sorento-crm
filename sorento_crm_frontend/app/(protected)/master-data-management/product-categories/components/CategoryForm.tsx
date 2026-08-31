'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { useCreateCategory, useUpdateCategory, useCategory } from '../hooks/useProductCategories';
// The floor is project-sales pricing POLICY, not a category column, so the panel and its
// rules live with the rest of that policy and are only surfaced here.
import { PriceFloorPanel } from '@/app/(protected)/project-sales/_shared/components/PriceFloorPanel';
import type { CategoryFormData, CategoryTreeItem } from '../types/category.types';

const CategorySchema = z.object({
  category_code: z.string().min(1, 'Category code is required').max(50),
  category_name: z.string().min(1, 'Category name is required').max(150),
  description: z.string().max(500).optional().nullable(),
  is_active: z.boolean(),
  is_searchable: z.boolean(),
  display_order: z.number().int().min(0),
});

interface CategoryFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryId?: string;
  /** When set, form opens in create mode with fields pre-filled from this category (for Duplicate). */
  copyFromCategory?: CategoryTreeItem | null;
}

export default function CategoryForm({ open, onOpenChange, categoryId, copyFromCategory }: CategoryFormProps) {
  const { data: category } = useCategory(categoryId || null);
  const createMutation = useCreateCategory();
  const updateMutation = useUpdateCategory();

  const form = useForm<z.infer<typeof CategorySchema>>({
    resolver: zodResolver(CategorySchema),
    mode: 'onTouched',
    defaultValues: {
      category_code: '',
      category_name: '',
      description: '',
      is_active: true,
      is_searchable: true,
      display_order: 0,
    },
  });

  useEffect(() => {
    if (open) {
      if (categoryId && category) {
        form.reset({
          category_code: category.category_code,
          category_name: category.category_name,
          description: category.description || '',
          is_active: category.is_active,
          is_searchable: category.is_searchable ?? true,
          display_order: category.display_order || 0,
        });
      } else if (copyFromCategory) {
        form.reset({
          category_code: `${copyFromCategory.category_code}-COPY`,
          category_name: `${copyFromCategory.category_name} (copy)`,
          description: copyFromCategory.description || '',
          is_active: copyFromCategory.is_active,
          is_searchable: copyFromCategory.is_searchable ?? true,
          display_order: copyFromCategory.display_order ?? 0,
        });
      } else {
        form.reset({
          category_code: '',
          category_name: '',
          description: '',
          is_active: true,
          is_searchable: true,
          display_order: 0,
        });
      }
    }
  }, [open, form, categoryId, category, copyFromCategory]);

  const onSubmit = async (data: z.infer<typeof CategorySchema>) => {
    try {
      const formData: CategoryFormData = {
        category_code: data.category_code,
        category_name: data.category_name,
        description: data.description ?? undefined,
        is_active: data.is_active,
        is_searchable: data.is_searchable,
        display_order: data.display_order,
      };
      
      if (categoryId) {
        await updateMutation.mutateAsync({ id: categoryId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      onOpenChange(false);
      form.reset();
    } catch (error) {
      // Error handled by mutation
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{categoryId ? 'Edit Category' : 'Create Category'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="category_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Category Code *</FormLabel>
                  <FormControl>
                    <Input placeholder="CAT-001" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="category_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Category Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter category name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Enter description"
                      {...field}
                      value={field.value || ''}
                      rows={3}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="display_order"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Display Order</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active</FormLabel>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="is_searchable"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Chat searchable</FormLabel>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            {/* Edit only, and it saves on its own: a floor is a row in
                price_floor_rules, not a category column, so this form's submit has
                nothing to do with it and could not report a half-failure honestly. A
                category being CREATED has no id to hang a rule on yet. */}
            {categoryId && category && (
              <PriceFloorPanel
                target={{
                  level: 'category',
                  id: categoryId,
                  label: category.category_name,
                }}
              />
            )}

            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                {categoryId ? 'Update' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
