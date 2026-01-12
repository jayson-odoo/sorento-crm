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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { useCreateCategory, useUpdateCategory, useCategory } from '../hooks/useProductCategories';
import { useCategoriesTree } from '../hooks/useProductCategories';
import type { CategoryFormData } from '../types/category.types';

const CategorySchema = z.object({
  category_code: z.string().min(1, 'Category code is required').max(50),
  category_name: z.string().min(1, 'Category name is required').max(150),
  description: z.string().max(500).optional().nullable(),
  parent_category_id: z.string().uuid().optional().nullable(),
  is_active: z.boolean().default(true),
  display_order: z.number().int().min(0).default(0),
});

interface CategoryFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryId?: string;
}

export default function CategoryForm({ open, onOpenChange, categoryId }: CategoryFormProps) {
  const { data: categories } = useCategoriesTree();
  const { data: category, isLoading: isLoadingCategory } = useCategory(categoryId || null);
  const createMutation = useCreateCategory();
  const updateMutation = useUpdateCategory();

  const form = useForm<CategoryFormData>({
    resolver: zodResolver(CategorySchema),
    defaultValues: {
      category_code: '',
      category_name: '',
      description: '',
      parent_category_id: null,
      is_active: true,
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
          parent_category_id: category.parent_category_id || null,
          is_active: category.is_active,
          display_order: category.display_order || 0,
        });
      } else {
        form.reset({
          category_code: '',
          category_name: '',
          description: '',
          parent_category_id: null,
          is_active: true,
          display_order: 0,
        });
      }
    }
  }, [open, form, categoryId, category]);

  const onSubmit = async (data: CategoryFormData) => {
    try {
      if (categoryId) {
        await updateMutation.mutateAsync({ id: categoryId, data });
      } else {
        await createMutation.mutateAsync(data);
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
              name="parent_category_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Parent Category</FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(value === '__none__' ? null : value)}
                    value={field.value || '__none__'}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select parent category" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="__none__">None (Root Category)</SelectItem>
                      {/* TODO: Flatten tree for select */}
                    </SelectContent>
                  </Select>
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

            <div className="flex justify-end gap-2">
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
