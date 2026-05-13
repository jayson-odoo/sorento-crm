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
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateWarehouse, useUpdateWarehouse, useWarehouse } from '../hooks/useWarehouses';
import { WarehouseSchema, type WarehouseSchemaType } from '../forms/warehouse-schema';

interface WarehouseFormProps {
  warehouseId?: string;
  onSuccess?: () => void;
}

export default function WarehouseForm({ warehouseId, onSuccess }: WarehouseFormProps) {
  const router = useRouter();
  const isEditMode = !!warehouseId;
  const { data: warehouse, isLoading: isLoadingWarehouse } = useWarehouse(warehouseId || null);
  const createMutation = useCreateWarehouse();
  const updateMutation = useUpdateWarehouse();

  const form = useForm<WarehouseSchemaType>({
    resolver: zodResolver(WarehouseSchema),
    defaultValues: {
      warehouse_code: '',
      warehouse_name: '',
      location: null,
      manager_id: null,
      is_active: true,
    },
    mode: 'onSubmit',
  });

  // Load warehouse data when editing
  useEffect(() => {
    if (warehouse && isEditMode) {
      form.reset({
        warehouse_code: warehouse.warehouse_code,
        warehouse_name: warehouse.warehouse_name,
        location: warehouse.location || null,
        manager_id: warehouse.manager_id || null,
        is_active: warehouse.is_active,
      });
    }
  }, [warehouse, isEditMode, form]);

  const onSubmit = async (data: WarehouseSchemaType) => {
    try {
      if (isEditMode && warehouseId) {
        await updateMutation.mutateAsync({ id: warehouseId, data });
      } else {
        await createMutation.mutateAsync(data);
      }
      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/inventory-management/warehouses');
      }
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  if (isEditMode && isLoadingWarehouse) {
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
            <CardTitle>{isEditMode ? 'Edit Warehouse' : 'Create Warehouse'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="warehouse_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>System Location *</FormLabel>
                    <FormControl>
                      <Input placeholder="WH-001" {...field} />
                    </FormControl>
                    <FormDescription>Must be unique.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="warehouse_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>System Location Description *</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Selangor Main DC" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="location"
                render={({ field }) => (
                  <FormItem className="md:col-span-2">
                    <FormLabel>Warehouse</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Warehouse name / address"
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
                        Inactive warehouses will not appear in dropdowns
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
                {isEditMode ? 'Update Warehouse' : 'Create Warehouse'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
