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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useQuery } from '@tanstack/react-query';
import { useCreateWarehouse, useUpdateWarehouse, useWarehouse } from '../hooks/useWarehouses';
import { getWarehouses } from '../services/warehouseService';
import type { Warehouse } from '../types/warehouse.types';
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
      warehouse_name: null,
      location: null,
      manager_id: null,
      is_active: true,
      counts_as_available: true,
      pool_warehouse_id: null,
    },
    mode: 'onSubmit',
  });

  // Candidate pools. Any location can be a pool, so this is the warehouse list itself,
  // minus the one being edited: a location pooling to itself is the default and is
  // expressed by leaving the field empty, never by selecting itself.
  const { data: poolOptions } = useQuery({
    queryKey: ['warehouses-select'],
    queryFn: async () => {
      const response = await getWarehouses({
        pageIndex: 0,
        pageSize: 1000,
        sorting: [],
        searchQuery: '',
      });
      return response.data || [];
    },
    staleTime: 1000 * 60 * 5,
  });

  // Load warehouse data when editing
  useEffect(() => {
    if (warehouse && isEditMode) {
      form.reset({
        warehouse_code: warehouse.warehouse_code,
        warehouse_name: warehouse.warehouse_name ?? null,
        location: warehouse.location || null,
        manager_id: warehouse.manager_id || null,
        is_active: warehouse.is_active,
        counts_as_available: warehouse.counts_as_available ?? true,
        // A location whose pool is itself is the "no pooling" default, so it reads as empty.
        pool_warehouse_id:
          warehouse.pool_warehouse_id && warehouse.pool_warehouse_id !== warehouse.id
            ? warehouse.pool_warehouse_id
            : null,
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
                    <FormLabel>System Location Description</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="e.g. Selangor Main DC"
                        {...field}
                        value={field.value ?? ''}
                        onChange={(e) => field.onChange(e.target.value || null)}
                      />
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

              <FormField
                control={form.control}
                name="counts_as_available"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Available for planning</FormLabel>
                      <FormDescription>
                        Turn this off for held, reserved, defective or clearance locations.
                        Stock here is real but cannot cover demand, so the plan ignores it.
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

              <FormField
                control={form.control}
                name="pool_warehouse_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Draws stock from</FormLabel>
                    <FormControl>
                      <SearchableSelect
                        value={field.value ?? ''}
                        onChange={(v) => field.onChange(v || null)}
                        options={(poolOptions || [])
                          .filter((w: Warehouse) => w.id !== warehouseId)
                          .map((w: Warehouse) => ({
                            value: w.id,
                            label: w.warehouse_name
                              ? `${w.warehouse_name} (${w.warehouse_code})`
                              : w.warehouse_code,
                          }))}
                        placeholder="Leave empty if this location stands alone"
                      />
                    </FormControl>
                    <FormDescription>
                      The shared pool this location draws on. A shortage here is covered from
                      that pool before anything is bought. Leave empty unless this location
                      genuinely shares stock with others on the same site.
                    </FormDescription>
                    <FormMessage />
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
