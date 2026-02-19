'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm, useFieldArray, type Resolver } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreatePackingList, useUpdatePackingList, usePackingList } from '../hooks/usePackingLists';
import { packingListSchema, type PackingListSchemaType } from '../forms/packing-list-schema';
import { useSupplierSelectQuery } from '../../suppliers/hooks/useSupplierSelectQuery';
import { getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import { ProductCombobox } from './ProductCombobox';
import { SupplierCombobox } from './SupplierCombobox';

interface PackingListFormProps {
  packingListId?: string;
  onSuccess?: () => void;
}

export default function PackingListForm({
  packingListId,
  onSuccess,
}: PackingListFormProps) {
  const router = useRouter();
  const isEditMode = !!packingListId;
  const { data: packingList, isLoading: isLoadingPackingList } = usePackingList(packingListId ?? null);
  const { data: suppliers = [] } = useSupplierSelectQuery();
  const [products, setProducts] = useState<Array<{ id: string; product_code: string; product_name?: string }>>([]);

  const createMutation = useCreatePackingList();
  const updateMutation = useUpdatePackingList();

  const form = useForm<PackingListSchemaType>({
    resolver: zodResolver(packingListSchema) as Resolver<PackingListSchemaType>,
    defaultValues: {
      shipment_number: '',
      supplier_id: '',
      shipment_date: '',
      expected_arrival_date: '',
      bill_of_lading_number: '',
      shipping_container_number: '',
      invoice_number: '',
      shipment_status: 'in_transit',
      shipment_lines: [{ product_id: '', quantity_shipped: 1 }],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'shipment_lines',
  });

  useEffect(() => {
    getProducts({
      pageIndex: 0,
      pageSize: 500,
      sorting: [],
      searchQuery: '',
      status: 'active',
    }).then((res) => {
      setProducts(res.data ?? []);
    });
  }, []);

  const lastInitializedIdRef = useRef<string | null>(null);
  useEffect(() => {
    lastInitializedIdRef.current = null;
    return () => { lastInitializedIdRef.current = null; };
  }, [packingListId]);

  useLayoutEffect(() => {
    if (!packingList || !isEditMode || lastInitializedIdRef.current === packingList.id) return;

    form.reset({
      shipment_number: packingList.shipment_number,
      supplier_id: packingList.supplier_id ?? '',
      shipment_date: packingList.shipment_date ? new Date(packingList.shipment_date).toISOString().slice(0, 10) : '',
      expected_arrival_date: packingList.expected_arrival_date
        ? new Date(packingList.expected_arrival_date).toISOString().slice(0, 10)
        : '',
      bill_of_lading_number: packingList.bill_of_lading_number ?? '',
      shipping_container_number: packingList.shipping_container_number ?? '',
      invoice_number: packingList.invoice_number ?? '',
      shipment_status: packingList.shipment_status ?? 'in_transit',
      shipment_lines:
        packingList.shipment_lines?.length && packingList.shipment_lines.length > 0
          ? packingList.shipment_lines.map((l) => ({
              product_id: l.product_id,
              quantity_shipped: l.quantity_shipped,
            }))
          : [{ product_id: '', quantity_shipped: 1 }],
    });
    lastInitializedIdRef.current = packingList.id;
  }, [packingList, isEditMode, form]);

  const onSubmit = async (data: PackingListSchemaType) => {
    try {
      const payload = {
        shipment_number: data.shipment_number,
        supplier_id: data.supplier_id || undefined,
        shipment_date: data.shipment_date,
        expected_arrival_date: data.expected_arrival_date || undefined,
        bill_of_lading_number: data.bill_of_lading_number || undefined,
        shipping_container_number: data.shipping_container_number || undefined,
        invoice_number: data.invoice_number || undefined,
        shipment_status: data.shipment_status || 'in_transit',
        shipment_lines: data.shipment_lines
          ?.filter((l) => l.product_id && l.quantity_shipped > 0)
          .map((l) => ({
            product_id: l.product_id,
            quantity_shipped: l.quantity_shipped,
          })),
      };

      if (isEditMode && packingListId) {
        await updateMutation.mutateAsync({ id: packingListId, data: payload as any });
      } else {
        await createMutation.mutateAsync(payload as any);
      }
      if (onSuccess) {
        onSuccess();
      } else {
        router.push(isEditMode ? `/procurement-management/packing-lists/${packingListId}` : '/procurement-management/packing-lists');
      }
    } catch (error) {
      console.error('Packing list form submission error:', error);
    }
  };

  if (isEditMode && isLoadingPackingList) {
    return (
      <div className="flex justify-center p-8">
        <LoaderCircleIcon className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{isEditMode ? 'Edit Packing List' : 'Create Packing List'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <FormField
                control={form.control}
                name="shipment_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Shipment Number *</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. FJ25476991" {...field} disabled={isEditMode} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="shipping_container_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Container Number</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. TIIU4090481" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="supplier_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Supplier</FormLabel>
                    <FormControl>
                      <SupplierCombobox
                        value={field.value ?? ''}
                        onChange={field.onChange}
                        suppliers={suppliers}
                        supplierFallback={packingList?.supplier}
                        placeholder="Select supplier"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="shipment_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Shipment Date *</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="expected_arrival_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Expected Arrival Date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} value={field.value || ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="bill_of_lading_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Bill of Lading Number</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="invoice_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Invoice Number</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Shipment Lines</CardTitle>
              <Button type="button" variant="outline" size="sm" onClick={() => append({ product_id: '', quantity_shipped: 1 })}>
                <Plus className="size-4" /> Add Line
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {fields.map((field, index) => (
                <div key={field.id} className="flex flex-wrap items-end gap-2">
                  <FormField
                    control={form.control}
                    name={`shipment_lines.${index}.product_id`}
                    render={({ field }) => (
                      <FormItem className="min-w-[200px] flex-1">
                        <FormLabel>Product</FormLabel>
                        <FormControl>
                          <ProductCombobox
                            value={field.value}
                            onChange={field.onChange}
                            products={products}
                            productFallback={packingList?.shipment_lines?.[index]?.product}
                            placeholder="Select product"
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`shipment_lines.${index}.quantity_shipped`}
                    render={({ field }) => (
                      <FormItem className="w-32">
                        <FormLabel>Qty Shipped</FormLabel>
                        <FormControl>
                          <Input type="number" min={1} {...field} onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 0)} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <Button type="button" variant="ghost" size="icon" onClick={() => remove(index)} className="text-destructive">
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Button type="submit" disabled={isLoading}>
            {isLoading && <LoaderCircleIcon className="me-2 size-4 animate-spin" />}
            {isEditMode ? 'Update' : 'Create'}
          </Button>
          <Button type="button" variant="outline" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </form>
    </Form>
  );
}
