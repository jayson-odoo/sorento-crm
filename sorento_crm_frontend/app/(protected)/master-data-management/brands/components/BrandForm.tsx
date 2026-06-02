'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateBrand, useUpdateBrand, useBrand } from '../hooks/useBrands';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
import { BrandSchema, type BrandSchemaType } from '../forms/brand-schema';
import type { BrandFormData } from '../types/brand.types';

interface BrandFormProps {
  brandId?: string;
  onSuccess?: () => void;
}

export default function BrandForm({ brandId, onSuccess }: BrandFormProps) {
  const router = useRouter();
  const isEditMode = !!brandId;
  const { data: brand, isLoading: isLoadingBrand } = useBrand(brandId || null);
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const createMutation = useCreateBrand();
  const updateMutation = useUpdateBrand();

  const form = useForm<BrandSchemaType>({
    resolver: zodResolver(BrandSchema),
    defaultValues: {
      brand_code: '',
      brand_name: '',
      manufacturer: null,
      website: null,
      description: null,
      logo_url: null,
      is_active: true,
      access_levels: [],
    },
    mode: 'onSubmit',
  });

  // Load brand data when editing
  useEffect(() => {
    if (brand && isEditMode) {
      form.reset({
        brand_code: brand.brand_code,
        brand_name: brand.brand_name,
        manufacturer: brand.manufacturer || null,
        website: brand.website || null,
        description: brand.description || null,
        logo_url: brand.logo_url || null,
        is_active: brand.is_active,
        access_levels: brand.access_levels ?? [],
      });
    }
  }, [brand, isEditMode, form]);

  const onSubmit = async (data: BrandSchemaType) => {
    try {
      // Convert null to undefined for form data
      const formData: BrandFormData = {
        brand_code: data.brand_code,
        brand_name: data.brand_name,
        manufacturer: data.manufacturer ?? undefined,
        website: data.website ?? undefined,
        description: data.description ?? undefined,
        logo_url: data.logo_url ?? undefined,
        is_active: data.is_active,
        access_levels: data.access_levels ?? [],
      };
      
      if (isEditMode && brandId) {
        await updateMutation.mutateAsync({ id: brandId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/master-data-management/brands');
      }
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  if (isEditMode && isLoadingBrand) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{isEditMode ? 'Edit Brand' : 'Create Brand'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="brand_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Brand Code *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="BRAND-001"
                        disabled={isEditMode}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Unique identifier for the brand. Cannot be changed after creation.
                    </FormDescription>
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
                      <Input placeholder="Brand Name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manufacturer"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Manufacturer</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Manufacturer Name"
                        {...field}
                        value={field.value || ''}
                        onChange={(e) => field.onChange(e.target.value || null)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="website"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Website</FormLabel>
                    <FormControl>
                      <Input
                        type="url"
                        placeholder="https://example.com"
                        {...field}
                        value={field.value || ''}
                        onChange={(e) => field.onChange(e.target.value || null)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="logo_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Logo URL</FormLabel>
                    <FormControl>
                      <Input
                        type="url"
                        placeholder="https://example.com/logo.png"
                        {...field}
                        value={field.value || ''}
                        onChange={(e) => field.onChange(e.target.value || null)}
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
                      <FormLabel className="text-base">Active Status</FormLabel>
                      <FormDescription>
                        Inactive brands will not appear in dropdowns
                      </FormDescription>
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
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Brand description..."
                      rows={4}
                      {...field}
                      value={field.value || ''}
                      onChange={(e) => field.onChange(e.target.value || null)}
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
                    Choose who can see products in this brand. Used by the AI
                    promotion fallback to scope product search to brands the
                    active contact is allowed to view. Leave empty for no
                    visibility restriction.
                  </FormDescription>
                  <div className="mt-2 flex flex-wrap gap-4">
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
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.back()}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="size-4" />
                {isEditMode ? 'Update Brand' : 'Create Brand'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
