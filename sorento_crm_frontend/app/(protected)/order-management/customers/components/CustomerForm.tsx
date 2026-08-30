'use client';

import { useEffect, useState } from 'react';
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
import { useCreateCustomer, useUpdateCustomer, useCustomer } from '../hooks/useCustomers';
import { CustomerSchema, type CustomerSchemaType } from '../forms/customer-schema';
import type { CustomerFormData } from '../types/customer.types';
import ListPager from '@/components/common/ListPager';
import { customersPagerQuery } from '../hooks/useCustomers';

interface CustomerFormProps {
  customerId?: string;
  onSuccess?: () => void;
}

export default function CustomerForm({ customerId, onSuccess }: CustomerFormProps) {
  const router = useRouter();
  const isEditMode = !!customerId;
  const { data: customer, isLoading: isLoadingCustomer } = useCustomer(customerId || null);
  const createMutation = useCreateCustomer();
  const updateMutation = useUpdateCustomer();

  const form = useForm<CustomerSchemaType>({
    resolver: zodResolver(CustomerSchema),
    defaultValues: {
      customer_code: '',
      customer_name: '',
      email: '',
      phone_number: '',
      is_active: true,
    },
    mode: 'onSubmit',
  });

  // Track if form has been initialized to prevent multiple resets
  const [formInitialized, setFormInitialized] = useState(false);

  // Load customer data when editing
  useEffect(() => {
    if (customer && isEditMode && !formInitialized) {
      form.reset({
        customer_code: customer.customer_code,
        customer_name: customer.customer_name,
        email: customer.email || '',
        phone_number: customer.phone_number || '',
        is_active: customer.is_active,
      });
      setFormInitialized(true);
    }
  }, [customer, isEditMode, form, formInitialized]);

  // Reset formInitialized when customerId changes
  useEffect(() => {
    setFormInitialized(false);
  }, [customerId]);

  const onSubmit = async (data: CustomerSchemaType) => {
    try {
      // Transform data to ensure proper format
      const formData: CustomerFormData = {
        customer_code: data.customer_code,
        customer_name: data.customer_name,
        email: data.email || undefined,
        phone_number: data.phone_number || undefined,
        is_active: data.is_active,
      };

      if (isEditMode && customerId) {
        await updateMutation.mutateAsync({ id: customerId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/order-management/customers');
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('Customer form submission error:', error);
    }
  };

  if (isEditMode && isLoadingCustomer) {
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
        {isEditMode && customerId && (
          <div className="flex justify-end">
            <ListPager
              {...customersPagerQuery}
              detailPath="/order-management/customers"
              currentId={customerId}
              ariaLabel="customer"
              hrefFor={(id, search) =>
                `/order-management/customers/${id}/edit${search ? `?${search}` : ''}`
              }
            />
          </div>
        )}
        <Card>
          <CardHeader>
            <CardTitle>{isEditMode ? 'Edit Customer' : 'Create Customer'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Basic Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Basic Information</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="customer_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Customer Code *</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="CUST-001"
                          {...field}
                          disabled={isEditMode}
                        />
                      </FormControl>
                      <FormDescription>
                        Unique customer identifier (alphanumeric, dashes, underscores only)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="customer_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Customer Name *</FormLabel>
                      <FormControl>
                        <Input placeholder="Enter customer name" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Email</FormLabel>
                      <FormControl>
                        <Input type="email" placeholder="customer@example.com" {...field} value={field.value || ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="phone_number"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Phone Number</FormLabel>
                      <FormControl>
                        <Input placeholder="+1 (555) 123-4567" {...field} value={field.value || ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Status */}
            <div className="space-y-4">
              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Active Status</FormLabel>
                      <FormDescription>
                        Enable or disable this customer
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

            <div className="flex justify-end gap-4 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (onSuccess) {
                    onSuccess();
                  } else {
                    router.push('/order-management/customers');
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
                    {isEditMode ? 'Update Customer' : 'Create Customer'}
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </Form>
  );
}
