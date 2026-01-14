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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useCreateStockInquiry,
  useUpdateStockInquiry,
  useStockInquiry,
} from '../hooks/useStockInquiries';
import {
  StockInquirySchema,
  type StockInquirySchemaType,
} from '../forms/stock-inquiry-schema';
import type { StockInquiryFormData } from '../types/stockInquiry.types';

interface StockInquiryFormProps {
  inquiryId?: string;
  onSuccess?: () => void;
}

export default function StockInquiryForm({
  inquiryId,
  onSuccess,
}: StockInquiryFormProps) {
  const router = useRouter();
  const isEditMode = !!inquiryId;
  const { data: inquiry, isLoading: isLoadingInquiry } = useStockInquiry(
    inquiryId || null,
  );
  const createMutation = useCreateStockInquiry();
  const updateMutation = useUpdateStockInquiry();

  const form = useForm<StockInquirySchemaType>({
    resolver: zodResolver(StockInquirySchema),
    defaultValues: {
      salesperson: null,
      product_code: null,
      item_description: null,
      project_customer: null,
      project_name: null,
      quantity: null,
      delivery_date: null,
      brand: null,
      additional_remark: null,
      purchasing_response: null,
    },
    mode: 'onSubmit',
  });

  const [formInitialized, setFormInitialized] = useState(false);

  // Load inquiry data when editing
  useEffect(() => {
    if (inquiry && isEditMode && !formInitialized) {
      form.reset({
        salesperson: inquiry.salesperson || null,
        product_code: inquiry.product_code || null,
        item_description: inquiry.item_description || null,
        project_customer: inquiry.project_customer || null,
        project_name: inquiry.project_name || null,
        quantity: inquiry.quantity || null,
        delivery_date: inquiry.delivery_date
          ? new Date(inquiry.delivery_date)
          : null,
        brand: inquiry.brand || null,
        additional_remark: inquiry.additional_remark || null,
        purchasing_response: inquiry.purchasing_response || null,
      });
      setFormInitialized(true);
    }
  }, [inquiry, isEditMode, form, formInitialized]);

  useEffect(() => {
    setFormInitialized(false);
  }, [inquiryId]);

  const onSubmit = async (data: StockInquirySchemaType) => {
    try {
      const formData: StockInquiryFormData = {
        salesperson: data.salesperson || undefined,
        product_code: data.product_code || undefined,
        item_description: data.item_description || undefined,
        project_customer: data.project_customer || undefined,
        project_name: data.project_name || undefined,
        quantity: data.quantity || undefined,
        delivery_date: data.delivery_date || undefined,
        brand: data.brand || undefined,
        additional_remark: data.additional_remark || undefined,
        purchasing_response: data.purchasing_response || undefined,
      };

      if (isEditMode && inquiryId) {
        await updateMutation.mutateAsync({ id: inquiryId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }

      onSuccess?.();
    } catch (error) {
      console.error('Error submitting form:', error);
    }
  };

  if (isEditMode && isLoadingInquiry) {
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Column */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Inquiry Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="salesperson"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Salesperson</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter salesperson name"
                          {...field}
                          value={field.value || ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="product_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Product Code</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter product code"
                          {...field}
                          value={field.value || ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="item_description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Item Description</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter item description"
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
                  name="quantity"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Quantity</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.01"
                          placeholder="Enter quantity"
                          {...field}
                          value={field.value || ''}
                          onChange={(e) => {
                            const value = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            field.onChange(value);
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="delivery_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Delivery Date</FormLabel>
                      <FormControl>
                        <Input
                          type="date"
                          {...field}
                          value={
                            field.value
                              ? new Date(field.value).toISOString().split('T')[0]
                              : ''
                          }
                          onChange={(e) => {
                            const date = e.target.value
                              ? new Date(e.target.value)
                              : null;
                            field.onChange(date);
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="brand"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Brand</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value || ''}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select brand" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="sorento">Sorento</SelectItem>
                          <SelectItem value="mocha">Mocha</SelectItem>
                          <SelectItem value="cabana">Cabana</SelectItem>
                          <SelectItem value="no logo">No Logo</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Project & Response</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="project_customer"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Project Customer</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter project customer"
                          {...field}
                          value={field.value || ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="project_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Project Name</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter project name"
                          {...field}
                          value={field.value || ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="additional_remark"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Additional Remark</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter additional remarks"
                          {...field}
                          value={field.value || ''}
                          rows={4}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="purchasing_response"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Purchasing Response</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter purchasing response"
                          {...field}
                          value={field.value || ''}
                          rows={4}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="flex justify-end gap-4">
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
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="size-4" />
                {isEditMode ? 'Update Stock Inquiry' : 'Create Stock Inquiry'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
