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
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { FormDescription } from '@/components/ui/form';
import { useCreateBrand, useUpdateBrand, useBrand } from '../hooks/useBrands';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
import type { BrandFormData, Brand } from '../types/brand.types';

const BrandFormSchema = z.object({
  brand_code: z.string().min(1, 'Brand code is required').max(50),
  brand_name: z.string().min(1, 'Brand name is required').max(150),
  description: z.string().max(2000).optional().nullable(),
  is_active: z.boolean(),
  access_levels: z.array(z.string()),
});

interface BrandFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  brandId?: string;
  /** When set, form opens in create mode with fields pre-filled from this brand (for Duplicate). */
  copyFromBrand?: Brand | null;
}

export default function BrandFormDialog({
  open,
  onOpenChange,
  brandId,
  copyFromBrand,
}: BrandFormDialogProps) {
  const { data: brand } = useBrand(brandId || null);
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const createMutation = useCreateBrand();
  const updateMutation = useUpdateBrand();

  const form = useForm<z.infer<typeof BrandFormSchema>>({
    resolver: zodResolver(BrandFormSchema),
    mode: 'onTouched',
    defaultValues: {
      brand_code: '',
      brand_name: '',
      description: '',
      is_active: true,
      access_levels: [],
    },
  });

  useEffect(() => {
    if (open) {
      if (brandId && brand) {
        form.reset({
          brand_code: brand.brand_code,
          brand_name: brand.brand_name,
          description: brand.description || '',
          is_active: brand.is_active,
          access_levels: brand.access_levels ?? [],
        });
      } else if (copyFromBrand) {
        form.reset({
          brand_code: `${copyFromBrand.brand_code}-COPY`,
          brand_name: `${copyFromBrand.brand_name} (copy)`,
          description: copyFromBrand.description || '',
          is_active: copyFromBrand.is_active,
          access_levels: copyFromBrand.access_levels ?? [],
        });
      } else {
        form.reset({
          brand_code: '',
          brand_name: '',
          description: '',
          is_active: true,
          access_levels: [],
        });
      }
    }
  }, [open, form, brandId, brand, copyFromBrand]);

  const onSubmit = async (data: z.infer<typeof BrandFormSchema>) => {
    try {
      const formData: BrandFormData = {
        brand_code: data.brand_code,
        brand_name: data.brand_name,
        description: data.description ?? undefined,
        is_active: data.is_active,
        access_levels: data.access_levels ?? [],
      };

      if (brandId) {
        await updateMutation.mutateAsync({ id: brandId, data: formData });
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
          <DialogTitle>
            {brandId ? 'Edit Brand' : 'Create Brand'}
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="brand_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Brand Code *</FormLabel>
                  <FormControl>
                    <Input placeholder="BRAND-001" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="brand_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Brand Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter brand name" {...field} />
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
              name="access_levels"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Access Levels</FormLabel>
                  <FormDescription>
                    Who can see products in this brand. Used by the AI promotion
                    fallback. Leave empty for no restriction.
                  </FormDescription>
                  <div className="mt-2 flex flex-wrap gap-3">
                    {accessTypeOptions.map((opt) => {
                      const checked = field.value?.includes(opt.code);
                      return (
                        <label key={opt.code} className="flex items-center gap-2 text-sm">
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(value) => {
                              const next = new Set(field.value || []);
                              if (value) {
                                next.add(opt.code);
                              } else {
                                next.delete(opt.code);
                              }
                              field.onChange(Array.from(next));
                            }}
                          />
                          {opt.name || opt.code}
                        </label>
                      );
                    })}
                  </div>
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
              <Button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {brandId ? 'Update' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
