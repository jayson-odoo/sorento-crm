'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm, Controller } from 'react-hook-form';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateUOM, useUpdateUOM, useUOM } from '../hooks/useUOM';
import { UOMSchema, type UOMSchemaType } from '../forms/uom-schema';
import type { UOMFormData } from '../types/uom.types';
import { useUOMSelectQuery } from '../../shared/hooks/use-uom-select-query';

interface UOMFormProps {
  uomId?: string;
  onSuccess?: () => void;
}

export default function UOMForm({ uomId, onSuccess }: UOMFormProps) {
  const router = useRouter();
  const isEditMode = !!uomId;
  const { data: uom, isLoading: isLoadingUOM } = useUOM(uomId || null);
  const { data: baseUOMs } = useUOMSelectQuery();
  const createMutation = useCreateUOM();
  const updateMutation = useUpdateUOM();

  const form = useForm<UOMSchemaType>({
    resolver: zodResolver(UOMSchema),
    defaultValues: {
      uom_code: '',
      uom_name: '',
      base_uom_id: null,
      conversion_factor: null,
      description: null,
      is_active: true,
    },
    mode: 'onSubmit',
  });

  // Load UOM data when editing
  useEffect(() => {
    if (uom && isEditMode) {
      form.reset({
        uom_code: uom.uom_code,
        uom_name: uom.uom_name,
        base_uom_id: uom.base_uom_id || null,
        conversion_factor: uom.conversion_factor || null,
        description: uom.description || null,
        is_active: uom.is_active ?? true,
      });
    }
  }, [uom, isEditMode, form]);

  const onSubmit = async (data: UOMSchemaType) => {
    try {
      // Convert null to undefined for form data
      const formData: UOMFormData = {
        uom_code: data.uom_code,
        uom_name: data.uom_name,
        description: data.description ?? undefined,
        base_uom_id: data.base_uom_id ?? undefined,
        conversion_factor: data.conversion_factor ?? undefined,
        is_active: data.is_active,
      };
      
      if (isEditMode && uomId) {
        await updateMutation.mutateAsync({ id: uomId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/master-data-management/units-of-measure');
      }
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  if (isEditMode && isLoadingUOM) {
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
            <CardTitle>{isEditMode ? 'Edit Unit of Measure' : 'Create Unit of Measure'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="uom_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>UOM Code *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="UOM-001"
                        disabled={isEditMode}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Unique identifier for the UOM. Cannot be changed after creation.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="uom_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>UOM Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="Unit of Measure Name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="base_uom_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Base UOM</FormLabel>
                    <Select
                      onValueChange={(value) => field.onChange(value === '__none__' ? null : value)}
                      value={field.value || '__none__'}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select base UOM" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="__none__">None (Base UOM)</SelectItem>
                        {baseUOMs?.map((baseUom) => (
                          <SelectItem key={baseUom.id} value={baseUom.id}>
                            {baseUom.uom_name} ({baseUom.uom_code})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      If this UOM is a conversion of another UOM, select the base UOM
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="conversion_factor"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Conversion Factor</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step="0.0001"
                        placeholder="1.0000"
                        {...field}
                        value={field.value ?? ''}
                        onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                      />
                    </FormControl>
                    <FormDescription>
                      Conversion factor relative to base UOM (e.g., 1 kg = 1000 g, factor = 1000)
                    </FormDescription>
                    <FormMessage />
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
                      placeholder="UOM description..."
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
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active</FormLabel>
                    <FormDescription>
                      Inactive UOMs will not appear in dropdowns when selecting a unit for products.
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
                {isEditMode ? 'Update UOM' : 'Create UOM'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
