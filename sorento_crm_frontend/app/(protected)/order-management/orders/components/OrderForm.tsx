'use client';

import { useEffect, useMemo, useState } from 'react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateOrder, useUpdateOrder, useOrder, useOrders } from '../hooks/useOrders';
import { OrderSchema, type OrderSchemaType } from '../forms/order-schema';
import type { OrderFormData } from '../types/order.types';
import { useCustomerSelectQuery } from '../../shared/hooks/use-customer-select-query';
import { useOrderStatusSelectQuery } from '../../shared/hooks/use-order-status-select-query';
import RecordNavigation from '@/components/common/RecordNavigation';

interface OrderFormProps {
  orderId?: string;
  onSuccess?: () => void;
}

export default function OrderForm({ orderId, onSuccess }: OrderFormProps) {
  const router = useRouter();
  const isEditMode = !!orderId;
  const { data: order, isLoading: isLoadingOrder } = useOrder(orderId || null);
  const { data: customers } = useCustomerSelectQuery();
  const { data: orderStatuses } = useOrderStatusSelectQuery();
  const createMutation = useCreateOrder();
  const updateMutation = useUpdateOrder();
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = useOrders(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  const form = useForm<OrderSchemaType>({
    resolver: zodResolver(OrderSchema),
    defaultValues: {
      order_number: '',
      order_date: new Date(),
      promised_delivery_date: undefined,
      actual_delivery_date: undefined,
      customer_id: '',
      order_status_id: '',
      billing_address_id: undefined,
      shipping_address_id: undefined,
      created_time: undefined,
      debtor_code: '',
      debtor_name: '',
      agent: '',
      is_cancelled: false,
      remarks_cs: '',
      order_type: '',
      delivery_time: '',
      checker: '',
      transporter: '',
      driver_name: '',
      lorry_plate: '',
      customer_ref: '',
      delivery_remarks_cs: '',
      delivery_remarks: '',
      salesman: '',
      trips: undefined,
      warehouse: '',
      delivery_days: undefined,
      kpi_warning: false,
      subtotal_amount: 0,
      discount_amount: 0,
      tax_amount: 0,
      total_amount: 0,
      remarks: '',
    },
    mode: 'onSubmit',
  });

  // Track if form has been initialized to prevent multiple resets
  const [formInitialized, setFormInitialized] = useState(false);

  // Watch financial fields to auto-calculate total
  const subtotal = form.watch('subtotal_amount');
  const discount = form.watch('discount_amount') || 0;
  const tax = form.watch('tax_amount') || 0;

  // Auto-calculate total when financial fields change
  useEffect(() => {
    const calculatedTotal = subtotal - discount + tax;
    if (calculatedTotal >= 0) {
      form.setValue('total_amount', calculatedTotal);
    }
  }, [subtotal, discount, tax, form]);

  // Load order data when editing
  useEffect(() => {
    if (
      order &&
      isEditMode &&
      customers &&
      customers.length > 0 &&
      orderStatuses &&
      orderStatuses.length > 0 &&
      !formInitialized
    ) {
      // Ensure values are strings for proper matching
      const customerId = order.customer_id ? String(order.customer_id) : '';
      const orderStatusId = order.order_status_id ? String(order.order_status_id) : '';

      // Verify that the selected values exist in the options
      const customerExists = customers.some((c) => c.id === customerId) || order.customer;
      const orderStatusExists = orderStatuses.some((os) => os.id === orderStatusId) || order.order_status;

      // Only reset if we can guarantee the selected items will be available
      if (customerExists && orderStatusExists) {
        // Use setTimeout to ensure SelectContent items are rendered before form reset
        const timeoutId = setTimeout(() => {
          form.reset({
            order_number: order.order_number,
            order_date: order.order_date ? new Date(order.order_date) : new Date(),
            promised_delivery_date: order.promised_delivery_date ? new Date(order.promised_delivery_date) : undefined,
            actual_delivery_date: order.actual_delivery_date ? new Date(order.actual_delivery_date) : undefined,
            customer_id: customerId,
            order_status_id: orderStatusId,
            billing_address_id: order.billing_address_id || undefined,
            shipping_address_id: order.shipping_address_id || undefined,
            created_time: order.created_time ? new Date(order.created_time) : undefined,
            debtor_code: order.debtor_code || '',
            debtor_name: order.debtor_name || '',
            agent: order.agent || '',
            is_cancelled: order.is_cancelled ?? false,
            remarks_cs: order.remarks_cs || '',
            order_type: order.order_type || '',
            delivery_time: order.delivery_time || '',
            checker: order.checker || '',
            transporter: order.transporter || '',
            driver_name: order.driver_name || '',
            lorry_plate: order.lorry_plate || '',
            customer_ref: order.customer_ref || '',
            delivery_remarks_cs: order.delivery_remarks_cs || '',
            delivery_remarks: order.delivery_remarks || '',
            salesman: order.salesman || '',
            trips: order.trips ?? undefined,
            warehouse: order.warehouse || '',
            delivery_days: order.delivery_days ?? undefined,
            kpi_warning: order.kpi_warning ?? false,
            subtotal_amount: order.subtotal_amount,
            discount_amount: order.discount_amount || 0,
            tax_amount: order.tax_amount || 0,
            total_amount: order.total_amount,
            remarks: order.remarks || '',
          });
          setFormInitialized(true);
        }, 0);

        return () => clearTimeout(timeoutId);
      }
    }
  }, [order, isEditMode, customers, orderStatuses, form, formInitialized]);

  // Reset formInitialized when orderId changes
  useEffect(() => {
    setFormInitialized(false);
  }, [orderId]);

  const onSubmit = async (data: OrderSchemaType) => {
    try {
      // Calculate total to ensure it's correct
      const calculatedTotal = data.subtotal_amount - (data.discount_amount || 0) + (data.tax_amount || 0);

      // Transform data to ensure proper format
      const formData: OrderFormData = {
        order_number: data.order_number,
        order_date: data.order_date,
        promised_delivery_date: data.promised_delivery_date || undefined,
        actual_delivery_date: data.actual_delivery_date || undefined,
        customer_id: data.customer_id,
        order_status_id: data.order_status_id,
        billing_address_id: data.billing_address_id || undefined,
        shipping_address_id: data.shipping_address_id || undefined,
        created_time: data.created_time || undefined,
        debtor_code: data.debtor_code || undefined,
        debtor_name: data.debtor_name || undefined,
        agent: data.agent || undefined,
        is_cancelled: data.is_cancelled ?? false,
        remarks_cs: data.remarks_cs || undefined,
        order_type: data.order_type || undefined,
        delivery_time: data.delivery_time || undefined,
        checker: data.checker || undefined,
        transporter: data.transporter || undefined,
        driver_name: data.driver_name || undefined,
        lorry_plate: data.lorry_plate || undefined,
        customer_ref: data.customer_ref || undefined,
        delivery_remarks_cs: data.delivery_remarks_cs || undefined,
        delivery_remarks: data.delivery_remarks || undefined,
        salesman: data.salesman || undefined,
        trips: data.trips ?? undefined,
        warehouse: data.warehouse || undefined,
        delivery_days: data.delivery_days ?? undefined,
        kpi_warning: data.kpi_warning ?? false,
        subtotal_amount: typeof data.subtotal_amount === 'number' ? data.subtotal_amount : Number(data.subtotal_amount),
        discount_amount: data.discount_amount || 0,
        tax_amount: data.tax_amount || 0,
        total_amount: calculatedTotal,
        remarks: data.remarks || undefined,
      };

      if (isEditMode && orderId) {
        await updateMutation.mutateAsync({ id: orderId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }

      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/order-management/orders');
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('Order form submission error:', error);
    }
  };

  if (isEditMode && isLoadingOrder) {
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
        {isEditMode && orderId && (
          <div className="flex justify-end">
            <RecordNavigation
              currentId={orderId}
              items={navigationItems}
              basePath="/order-management/orders"
            />
          </div>
        )}
        <Tabs defaultValue="basic" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="basic">Basic Information</TabsTrigger>
            <TabsTrigger value="financial">Financial Details</TabsTrigger>
            <TabsTrigger value="remarks">Remarks</TabsTrigger>
            <TabsTrigger value="tracking">Delivery & Tracking</TabsTrigger>
          </TabsList>

          {/* Tab 1: Basic Information */}
          <TabsContent value="basic">
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <FormField
                  control={form.control}
                  name="order_number"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Order Number *</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="ORD-001"
                          {...field}
                          disabled={isEditMode}
                        />
                      </FormControl>
                      <FormDescription>
                        Unique order identifier
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="order_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Order Date *</FormLabel>
                        <FormControl>
                          <Input
                            type="date"
                            {...field}
                            value={field.value ? field.value.toISOString().split('T')[0] : ''}
                            onChange={(e) => field.onChange(new Date(e.target.value))}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="promised_delivery_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Promised Delivery Date</FormLabel>
                        <FormControl>
                          <Input
                            type="date"
                            {...field}
                            value={field.value ? field.value.toISOString().split('T')[0] : ''}
                            onChange={(e) => field.onChange(e.target.value ? new Date(e.target.value) : undefined)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="actual_delivery_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Actual Delivery Date</FormLabel>
                        <FormControl>
                          <Input
                            type="date"
                            {...field}
                            value={field.value ? field.value.toISOString().split('T')[0] : ''}
                            onChange={(e) => field.onChange(e.target.value ? new Date(e.target.value) : undefined)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="customer_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Customer *</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || ''}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select customer" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {customers?.map((customer) => (
                              <SelectItem key={customer.id} value={customer.id}>
                                {customer.customer_code} - {customer.customer_name}
                              </SelectItem>
                            ))}
                            {(!customers || customers.length === 0) && (
                              <SelectItem value="__no_customers__" disabled>
                                No customers available
                              </SelectItem>
                            )}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="order_status_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Order Status *</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || ''}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select order status" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {orderStatuses?.map((status) => (
                              <SelectItem key={status.id} value={status.id}>
                                {status.status_code} - {status.status_name}
                              </SelectItem>
                            ))}
                            {(!orderStatuses || orderStatuses.length === 0) && (
                              <SelectItem value="__no_statuses__" disabled>
                                No order statuses available
                              </SelectItem>
                            )}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 2: Financial Details */}
          <TabsContent value="financial">
            <Card>
              <CardHeader>
                <CardTitle>Financial Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="subtotal_amount"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Subtotal Amount *</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value ?? ''}
                            onChange={(e) => {
                              const value = e.target.value;
                              if (value === '') {
                                field.onChange(0);
                              } else {
                                const numValue = parseFloat(value);
                                field.onChange(isNaN(numValue) ? 0 : numValue);
                              }
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="discount_amount"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Discount Amount</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value ?? ''}
                            onChange={(e) => {
                              const value = e.target.value;
                              if (value === '') {
                                field.onChange(0);
                              } else {
                                const numValue = parseFloat(value);
                                field.onChange(isNaN(numValue) ? 0 : numValue);
                              }
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="tax_amount"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Tax Amount</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value ?? ''}
                            onChange={(e) => {
                              const value = e.target.value;
                              if (value === '') {
                                field.onChange(0);
                              } else {
                                const numValue = parseFloat(value);
                                field.onChange(isNaN(numValue) ? 0 : numValue);
                              }
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="total_amount"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Total Amount *</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value ?? ''}
                            onChange={(e) => {
                              const value = e.target.value;
                              if (value === '') {
                                field.onChange(0);
                              } else {
                                const numValue = parseFloat(value);
                                field.onChange(isNaN(numValue) ? 0 : numValue);
                              }
                            }}
                          />
                        </FormControl>
                        <FormDescription>
                          Auto-calculated: Subtotal - Discount + Tax
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 3: Remarks */}
          <TabsContent value="remarks">
            <Card>
              <CardHeader>
                <CardTitle>Remarks</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <FormField
                  control={form.control}
                  name="remarks"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Remarks</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter any additional notes or remarks..."
                          {...field}
                          value={field.value || ''}
                          rows={8}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 4: Delivery & Tracking */}
          <TabsContent value="tracking">
            <Card>
              <CardHeader>
                <CardTitle>Delivery & Tracking</CardTitle>
              </CardHeader>
              <CardContent className="space-y-8">
                <div className="space-y-4">
                  <h4 className="text-sm font-semibold text-muted-foreground">Master Information</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormField
                      control={form.control}
                      name="created_time"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Created Time</FormLabel>
                          <FormControl>
                            <Input
                              type="datetime-local"
                              value={field.value ? new Date(field.value).toISOString().slice(0, 16) : ''}
                              onChange={(e) => field.onChange(e.target.value ? new Date(e.target.value) : undefined)}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="order_type"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Type</FormLabel>
                          <FormControl>
                            <Input placeholder="BEYOND" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="debtor_code"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Debtor Code</FormLabel>
                          <FormControl>
                            <Input placeholder="300-A007" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="debtor_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Debtor Name</FormLabel>
                          <FormControl>
                            <Input placeholder="ASIAN PAC HOLDINGS BERHAD" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="agent"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Agent</FormLabel>
                          <FormControl>
                            <Input placeholder="ERIC" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="is_cancelled"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Cancelled</FormLabel>
                          <Select
                            value={field.value ? 'true' : 'false'}
                            onValueChange={(value) => field.onChange(value === 'true')}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="false">No</SelectItem>
                              <SelectItem value="true">Yes</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="remarks_cs"
                      render={({ field }) => (
                        <FormItem className="md:col-span-2">
                          <FormLabel>Remarks CS</FormLabel>
                          <FormControl>
                            <Textarea placeholder="Remarks from CS..." {...field} value={field.value || ''} rows={3} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <h4 className="text-sm font-semibold text-muted-foreground">Delivery Information</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormField
                      control={form.control}
                      name="delivery_time"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Delivery Time</FormLabel>
                          <FormControl>
                            <Input placeholder="8:47 AM" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="checker"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Checker</FormLabel>
                          <FormControl>
                            <Input placeholder="indra" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="transporter"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Transporter</FormLabel>
                          <FormControl>
                            <Input placeholder="SORENTO" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="driver_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Driver Name</FormLabel>
                          <FormControl>
                            <Input placeholder="AZLAN" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="lorry_plate"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Lorry Plate</FormLabel>
                          <FormControl>
                            <Input placeholder="VCG1678" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="customer_ref"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Customer</FormLabel>
                          <FormControl>
                            <Input placeholder="CPI EMPOWER SDN BHD (PROJECT)" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <h4 className="text-sm font-semibold text-muted-foreground">Delivery Details</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormField
                      control={form.control}
                      name="delivery_remarks_cs"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Remarks CS</FormLabel>
                          <FormControl>
                            <Textarea placeholder="CS remarks..." {...field} value={field.value || ''} rows={3} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="delivery_remarks"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Remarks</FormLabel>
                          <FormControl>
                            <Textarea placeholder="Delivery remarks..." {...field} value={field.value || ''} rows={3} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="salesman"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Salesman</FormLabel>
                          <FormControl>
                            <Input placeholder="ACT" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="trips"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Trips</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              {...field}
                              value={field.value ?? ''}
                              onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : undefined)}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="warehouse"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Warehouse</FormLabel>
                          <FormControl>
                            <Input placeholder="BRW" {...field} value={field.value || ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <h4 className="text-sm font-semibold text-muted-foreground">KPI</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormField
                      control={form.control}
                      name="delivery_days"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Delivery Days</FormLabel>
                          <FormControl>
                            <Input value={field.value ?? ''} disabled />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="kpi_warning"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>KPI Warning</FormLabel>
                          <FormControl>
                            <Input value={field.value ? 'Yes' : 'No'} disabled />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        <div className="flex justify-end gap-4 pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              if (onSuccess) {
                onSuccess();
              } else {
                router.push('/order-management/orders');
              }
            }}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="mr-2 size-4" />
                {isEditMode ? 'Update Order' : 'Create Order'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
