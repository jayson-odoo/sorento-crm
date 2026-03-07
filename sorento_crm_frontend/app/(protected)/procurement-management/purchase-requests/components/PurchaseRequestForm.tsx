'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm, useFieldArray } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save, Send, Plus, Trash2 } from 'lucide-react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useCreatePurchaseRequest,
  useUpdatePurchaseRequest,
  useUpdatePurchaseRequestAndReply,
  usePurchaseRequest,
} from '../hooks/usePurchaseRequests';
import { getOrCreateViewLink } from '../services/purchaseRequestService';
import { toast } from 'sonner';
import {
  PurchaseRequestSchema,
  type PurchaseRequestSchemaType,
} from '../forms/purchase-request-schema';
import type { PurchaseRequestFormData } from '../types/purchaseRequest.types';

const PURCHASE_REQUESTS_EDIT = '/procurement-management/purchase-requests';
const SPONSORSHIP_FORMS_EDIT = '/procurement-management/sponsorship-forms';

interface PurchaseRequestFormProps {
  requestId?: string;
  /** When set (e.g. on sponsorship-forms/new), form defaults to this type and type field is hidden. */
  defaultRequestType?: 'purchase_request' | 'sponsorship_form';
  /** On edit: if the loaded record's type doesn't match, redirect to the correct section's edit page. */
  expectedRequestType?: 'purchase_request' | 'sponsorship_form';
  /** URL to redirect to after successful create/update (serializable; use this from Server Component pages). */
  successRedirectUrl?: string;
}

export default function PurchaseRequestForm({
  requestId,
  defaultRequestType = 'purchase_request',
  expectedRequestType,
  successRedirectUrl,
}: PurchaseRequestFormProps) {
  const router = useRouter();
  const isEditMode = !!requestId;
  const { data: request, isLoading: isLoadingRequest } = usePurchaseRequest(
    requestId || null,
  );
  const createMutation = useCreatePurchaseRequest();
  const updateMutation = useUpdatePurchaseRequest();
  const updateAndReplyMutation = useUpdatePurchaseRequestAndReply();
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const [replyMessage, setReplyMessage] = useState('');

  // Redirect to the correct edit page if record type doesn't match (e.g. opened purchase-request edit but record is sponsorship_form)
  useEffect(() => {
    if (
      requestId &&
      request &&
      expectedRequestType &&
      request.request_type &&
      request.request_type !== expectedRequestType
    ) {
      const correctPath =
        request.request_type === 'sponsorship_form'
          ? `${SPONSORSHIP_FORMS_EDIT}/${requestId}/edit`
          : `${PURCHASE_REQUESTS_EDIT}/${requestId}/edit`;
      router.replace(correctPath);
    }
  }, [requestId, request, expectedRequestType, router]);

  const form = useForm<PurchaseRequestSchemaType>({
    resolver: zodResolver(PurchaseRequestSchema),
    defaultValues: {
      request_type: defaultRequestType,
      request_number: null,
      request_date: null,
      customer_name: null,
      project_title: null,
      purpose: null,
      expected_delivery_date: null,
      expected_po_date: null,
      expected_po_date_text: null,
      requested_by: null,
      requested_at: null,
      products: [{ item_code: null, quantity: null, remark: null }],
    },
    mode: 'onSubmit',
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'products',
  });

  const [formInitialized, setFormInitialized] = useState(false);

  useEffect(() => {
    if (request && isEditMode && !formInitialized) {
      const products =
        (request.lines?.length ?? 0) > 0
          ? request.lines!.map((l) => ({
              item_code: l.item_code ?? null,
              quantity:
                l.quantity != null ? Number(l.quantity) : null,
              remark: l.remark ?? null,
            }))
          : [{ item_code: null, quantity: null, remark: null }];
      form.reset({
        request_type: (request.request_type ?? 'purchase_request') as
          | 'purchase_request'
          | 'sponsorship_form',
        request_number: request.request_number ?? null,
        request_date: request.request_date
          ? new Date(request.request_date).toISOString().split('T')[0]
          : null,
        customer_name: request.customer_name ?? null,
        project_title: request.project_title ?? null,
        purpose: request.purpose ?? null,
        expected_delivery_date: request.expected_delivery_date
          ? new Date(request.expected_delivery_date).toISOString().split('T')[0]
          : null,
        expected_po_date: request.expected_po_date
          ? new Date(request.expected_po_date).toISOString().split('T')[0]
          : null,
        expected_po_date_text: request.expected_po_date_text ?? null,
        requested_by: request.requested_by ?? null,
        requested_at: request.requested_at
          ? new Date(request.requested_at).toISOString().split('T')[0]
          : null,
        products,
      });
      setFormInitialized(true);
    }
  }, [request, isEditMode, form, formInitialized]);

  useEffect(() => {
    setFormInitialized(false);
  }, [requestId]);

  const onSubmit = async (data: PurchaseRequestSchemaType) => {
    try {
      const formData: PurchaseRequestFormData = {
        request_type: data.request_type,
        request_number: data.request_number ?? undefined,
        request_date: data.request_date || undefined,
        customer_name: data.customer_name || undefined,
        project_title: data.project_title || undefined,
        purpose: data.purpose || undefined,
        expected_delivery_date: data.expected_delivery_date || undefined,
        expected_po_date: data.expected_po_date || undefined,
        expected_po_date_text: data.expected_po_date_text || undefined,
        requested_by: data.requested_by || undefined,
        requested_at: data.requested_at || undefined,
        products: data.products
          .filter((p) => p.item_code != null || p.quantity != null)
          .map((p) => ({
            item_code: p.item_code ?? undefined,
            quantity:
              p.quantity != null && p.quantity !== ''
                ? Number(p.quantity)
                : undefined,
            remark: p.remark ?? undefined,
          })),
      };

      if (isEditMode && requestId) {
        await updateMutation.mutateAsync({ id: requestId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      if (successRedirectUrl) {
        router.push(successRedirectUrl);
      }
    } catch (error) {
      console.error('Error submitting form:', error);
    }
  };

  if (isEditMode && isLoadingRequest) {
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
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Header</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="request_number"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Form number</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g. PR-2026-001"
                          {...field}
                          value={field.value ?? ''}
                          onChange={(e) => field.onChange(e.target.value || null)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                {defaultRequestType !== 'sponsorship_form' && (
                  <FormField
                    control={form.control}
                    name="request_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Type</FormLabel>
                        <Select
                          onValueChange={field.onChange}
                          value={field.value ?? ''}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select type" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="purchase_request">
                              Purchase Request
                            </SelectItem>
                            <SelectItem value="sponsorship_form">
                              Sponsorship Form
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
                <FormField
                  control={form.control}
                  name="request_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Request Date</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="customer_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Customer Name</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Customer name"
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
                  name="project_title"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Project Title</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Project title"
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
                  name="purpose"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Purpose</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g. Showroom"
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
                  name="expected_delivery_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Expected Delivery Date</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="expected_po_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Expected PO Date</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="expected_po_date_text"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Expected PO (text)</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g. PROPOSED STAGE (IMMEDIATE ORDER)"
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
                  name="requested_by"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Requested By</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Name"
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
                  name="requested_at"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Requested At</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>Line Items</CardTitle>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    append({ item_code: null, quantity: null, remark: null })
                  }
                >
                  <Plus className="size-4" />
                  Add row
                </Button>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Item Code</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Remark</TableHead>
                      <TableHead className="w-12" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {fields.map((field, index) => (
                      <TableRow key={field.id}>
                        <TableCell>
                          <FormField
                            control={form.control}
                            name={`products.${index}.item_code`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormControl>
                                  <Input
                                    placeholder="Item code"
                                    {...f}
                                    value={f.value ?? ''}
                                    className="h-8"
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </TableCell>
                        <TableCell>
                          <FormField
                            control={form.control}
                            name={`products.${index}.quantity`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormControl>
                                  <Input
                                    type="number"
                                    step="any"
                                    placeholder="0"
                                    {...f}
                                    value={f.value ?? ''}
                                    onChange={(e) => {
                                      const v = e.target.value
                                        ? parseFloat(e.target.value)
                                        : null;
                                      f.onChange(v);
                                    }}
                                    className="h-8 w-24"
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </TableCell>
                        <TableCell>
                          <FormField
                            control={form.control}
                            name={`products.${index}.remark`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormControl>
                                  <Input
                                    placeholder="Remark"
                                    {...f}
                                    value={f.value ?? ''}
                                    className="h-8"
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => remove(index)}
                            disabled={fields.length <= 1}
                          >
                            <Trash2 className="size-4 text-destructive" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
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
          {isEditMode && (
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                const valid = await form.trigger();
                if (!valid || !requestId) return;
                setReplyMessage('');
                try {
                  const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                  const { view_url } = await getOrCreateViewLink(requestId, baseUrl);
                  if (view_url) setReplyMessage(view_url);
                } catch {
                  // leave empty, user can type
                }
                setUpdateAndReplyDialogOpen(true);
              }}
              disabled={isLoading || updateAndReplyMutation.isPending}
            >
              {updateAndReplyMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Sending…
                </>
              ) : (
                <>
                  <Send className="size-4" />
                  Update & Reply
                </>
              )}
            </Button>
          )}
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="size-4" />
                {isEditMode ? 'Update' : 'Create'}
              </>
            )}
          </Button>
        </div>
      </form>

      {isEditMode && (
        <Dialog open={updateAndReplyDialogOpen} onOpenChange={setUpdateAndReplyDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Update & Reply</DialogTitle>
              <DialogDescription>
                This message will be sent to the conversation in Respond. You can edit it below. The view link is included by default for the recipient to open the form.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pr-reply_message">Message to send</Label>
                <Textarea
                  id="pr-reply_message"
                  value={replyMessage}
                  onChange={(e) => setReplyMessage(e.target.value)}
                  placeholder="Add a message (view link will be appended if added above)"
                  rows={4}
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
                onClick={async () => {
                  if (!requestId) return;
                  try {
                    const values = form.getValues();
                    await updateAndReplyMutation.mutateAsync({
                      id: requestId,
                      data: {
                        formData: {
                          request_type: values.request_type,
                          request_number: values.request_number ?? undefined,
                          request_date: values.request_date ?? undefined,
                          customer_name: values.customer_name ?? undefined,
                          project_title: values.project_title ?? undefined,
                          purpose: values.purpose ?? undefined,
                          expected_delivery_date: values.expected_delivery_date ?? undefined,
                          expected_po_date: values.expected_po_date ?? undefined,
                          expected_po_date_text: values.expected_po_date_text ?? undefined,
                          requested_by: values.requested_by ?? undefined,
                          requested_at: values.requested_at ?? undefined,
                          products: (values.products ?? []).map((p) => ({
                            item_code: p.item_code ?? undefined,
                            quantity:
                              typeof p.quantity === 'number'
                                ? p.quantity
                                : p.quantity != null && p.quantity !== ''
                                  ? Number(p.quantity)
                                  : undefined,
                            remark: p.remark ?? undefined,
                          })),
                        },
                        reply_message: replyMessage.trim(),
                      },
                    });
                    setUpdateAndReplyDialogOpen(false);
                    setReplyMessage('');
                    toast.success('Updated and reply sent');
                    if (successRedirectUrl) router.push(successRedirectUrl);
                  } catch {
                    // toast from mutation
                  }
                }}
              >
                {updateAndReplyMutation.isPending ? 'Sending…' : 'Update & Reply'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Form>
  );
}
