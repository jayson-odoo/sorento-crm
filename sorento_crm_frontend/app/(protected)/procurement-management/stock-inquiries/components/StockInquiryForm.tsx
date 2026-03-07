'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useCreateStockInquiry,
  useUpdateStockInquiry,
  useUpdateStockInquiryAndReply,
  useStockInquiry,
} from '../hooks/useStockInquiries';
import { getOrCreateStockInquiryViewLink } from '../services/stockInquiryService';
import { toast } from 'sonner';
import {
  StockInquirySchema,
  type StockInquirySchemaType,
} from '../forms/stock-inquiry-schema';
import type { StockInquiryFormData } from '../types/stockInquiry.types';
import StockInquiryAttachmentsSection from './StockInquiryAttachmentsSection';

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
  const updateAndReplyMutation = useUpdateStockInquiryAndReply();
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const [replyMessage, setReplyMessage] = useState('');
  const [previewPreparing, setPreviewPreparing] = useState(false);

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
      remark: null,
      additional_remark: null,
      purchasing_response: null,
      contact_id: null,
      space_id: null,
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
        quantity: inquiry.quantity ?? null,
        delivery_date: inquiry.delivery_date ?? null,
        remark: inquiry.remark ?? null,
        additional_remark: inquiry.additional_remark || null,
        purchasing_response: inquiry.purchasing_response || null,
        contact_id: inquiry.contact_id || null,
        space_id: inquiry.space_id || null,
      });
      setFormInitialized(true);
    }
  }, [inquiry, isEditMode, form, formInitialized]);

  useEffect(() => {
    setFormInitialized(false);
  }, [inquiryId]);

  const handleUpdateAndReplyClick = async () => {
    const valid = await form.trigger();
    if (!valid || !inquiryId) return;
    setPreviewPreparing(true);
    try {
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
      const { view_url } = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
      const purchasingResponse = (form.getValues().purchasing_response ?? '').trim();
      const linkPart = view_url ? ` ${view_url}` : '';
      const fullMessage = `There is a response to your stock inquiry${linkPart}: ${purchasingResponse}`;
      setReplyMessage(fullMessage);
      setUpdateAndReplyDialogOpen(true);
    } catch {
      toast.error('Failed to prepare message preview. Could not get stock inquiry view link.');
    } finally {
      setPreviewPreparing(false);
    }
  };

  const handleUpdateAndReplyConfirm = async () => {
    if (!inquiryId) return;
    const data = form.getValues();
    const formData: StockInquiryFormData = {
      salesperson: data.salesperson || undefined,
      product_code: data.product_code || undefined,
      item_description: data.item_description || undefined,
      project_customer: data.project_customer || undefined,
      project_name: data.project_name || undefined,
      quantity: data.quantity ?? undefined,
      delivery_date: data.delivery_date ?? undefined,
      remark: data.remark ?? undefined,
      additional_remark: data.additional_remark || undefined,
      purchasing_response: replyMessage.trim() || undefined,
      contact_id: data.contact_id || undefined,
      space_id: data.space_id || undefined,
    };
    try {
      await updateAndReplyMutation.mutateAsync({ id: inquiryId, data: formData });
      setUpdateAndReplyDialogOpen(false);
      setReplyMessage('');
      onSuccess?.();
    } catch {
      // Error toast from mutation
    }
  };

  const onSubmit = async (data: StockInquirySchemaType) => {
    try {
      const formData: StockInquiryFormData = {
        salesperson: data.salesperson || undefined,
        product_code: data.product_code || undefined,
        item_description: data.item_description || undefined,
        project_customer: data.project_customer || undefined,
        project_name: data.project_name || undefined,
        quantity: data.quantity ?? undefined,
        delivery_date: data.delivery_date ?? undefined,
        remark: data.remark ?? undefined,
        additional_remark: data.additional_remark || undefined,
        purchasing_response: data.purchasing_response || undefined,
        contact_id: data.contact_id || undefined,
        space_id: data.space_id || undefined,
      };

      if (isEditMode && inquiryId) {
        await updateMutation.mutateAsync({ id: inquiryId, data: formData });
      } else {
        const created = await createMutation.mutateAsync(formData);
        if (created?.id) {
          try {
            const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
            const { view_url } = await getOrCreateStockInquiryViewLink(created.id, baseUrl);
            await navigator.clipboard.writeText(view_url);
            toast.success('Stock inquiry created. View link copied to clipboard.');
          } catch {
            // view link optional
          }
        }
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
                          placeholder="Enter quantity"
                          {...field}
                          value={field.value ?? ''}
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
                          placeholder="Enter delivery date"
                          {...field}
                          value={field.value ?? ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="remark"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Remark</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter remark"
                          {...field}
                          value={field.value ?? ''}
                          rows={3}
                        />
                      </FormControl>
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
                {inquiry?.respond_inbox_url && (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Respond Inbox</p>
                    <a
                      href={inquiry.respond_inbox_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline text-sm break-all"
                    >
                      {inquiry.respond_inbox_url}
                    </a>
                  </div>
                )}
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

        {isEditMode && inquiryId && (
          <StockInquiryAttachmentsSection
            inquiryId={inquiryId}
            attachments={inquiry?.attachments ?? []}
          />
        )}

        <div className="flex justify-end gap-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.back()}
            disabled={isLoading || updateAndReplyMutation.isPending}
          >
            Cancel
          </Button>
          {isEditMode && (
            <Button
              type="button"
              variant="secondary"
              onClick={handleUpdateAndReplyClick}
              disabled={isLoading || previewPreparing || updateAndReplyMutation.isPending}
            >
              {previewPreparing ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Preparing...
                </>
              ) : updateAndReplyMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <Send className="size-4" />
                  Update & Reply
                </>
              )}
            </Button>
          )}
          <Button
            type="submit"
            disabled={isLoading || updateAndReplyMutation.isPending}
          >
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

      <Dialog open={updateAndReplyDialogOpen} onOpenChange={setUpdateAndReplyDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Update & Reply</DialogTitle>
            <DialogDescription>
              Edit the message below. It will be saved as the purchasing response and sent to the customer via Respond.io. The conversation will be marked as responded.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="stock-inquiry-reply-message">Message to send</Label>
              <Textarea
                id="stock-inquiry-reply-message"
                value={replyMessage}
                onChange={(e) => setReplyMessage(e.target.value)}
                placeholder="Purchasing response..."
                rows={5}
                className="resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setUpdateAndReplyDialogOpen(false)}
              disabled={updateAndReplyMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              disabled={updateAndReplyMutation.isPending || !replyMessage.trim()}
              onClick={(e) => {
                e.preventDefault();
                handleUpdateAndReplyConfirm();
              }}
            >
              {updateAndReplyMutation.isPending ? 'Sending...' : 'Update & Reply'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Form>
  );
}
