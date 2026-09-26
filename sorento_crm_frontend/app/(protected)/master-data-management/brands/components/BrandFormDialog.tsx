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
  // False means every product on this brand is bought locally by CS and never
  // raises an Order Inquiry (PLAN-brand-flows-to-purchasing.md).
  flows_to_purchasing: z.boolean(),
  // The chatbot's brand preference: higher weights are answered first (0 = none).
  chatbot_weight: z.coerce.number().min(0, 'Enter 0 or more').max(9999, 'Enter 9999 or less'),
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
      flows_to_purchasing: true,
      chatbot_weight: 0,
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
          flows_to_purchasing: brand.flows_to_purchasing,
          chatbot_weight: brand.chatbot_weight ?? 0,
        });
      } else if (copyFromBrand) {
        form.reset({
          brand_code: `${copyFromBrand.brand_code}-COPY`,
          brand_name: `${copyFromBrand.brand_name} (copy)`,
          description: copyFromBrand.description || '',
          is_active: copyFromBrand.is_active,
          access_levels: copyFromBrand.access_levels ?? [],
          flows_to_purchasing: copyFromBrand.flows_to_purchasing,
          // A copy never takes the preference of the brand it was copied from.
          chatbot_weight: 0,
        });
      } else {
        form.reset({
          brand_code: '',
          brand_name: '',
          description: '',
          is_active: true,
          access_levels: [],
          flows_to_purchasing: true,
          chatbot_weight: 0,
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
        flows_to_purchasing: data.flows_to_purchasing,
        chatbot_weight: data.chatbot_weight,
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
          {/* noValidate: the zod schema says why a value is refused ("Enter 9999 or less");
              the browser's own min/max check would stop the submit before it could. */}
          <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
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

            <FormField
              control={form.control}
              name="flows_to_purchasing"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Flows to purchasing</FormLabel>
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
              name="chatbot_weight"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Chatbot brand weight</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      max={9999}
                      step={0.1}
                      inputMode="decimal"
                      className="w-32"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
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
