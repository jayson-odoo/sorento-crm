'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateComplaint, useUpdateComplaint, useUpdateComplaintAndReply, useComplaint } from '../hooks/useComplaints';
import { ComplaintSchema, type ComplaintSchemaType } from '../forms/complaint-schema';
import type { ComplaintFormData, ComplaintAttachment } from '../types/complaint.types';
import ComplaintNavigation from './ComplaintNavigation';
import ComplaintManualAttachmentsSection from './ComplaintManualAttachmentsSection';

interface ComplaintFormProps {
  complaintId?: string;
  onSuccess?: () => void;
}

export default function ComplaintForm({ complaintId, onSuccess }: ComplaintFormProps) {
  const router = useRouter();
  const isEditMode = !!complaintId;
  const { data: complaint, isLoading: isLoadingComplaint } = useComplaint(
    complaintId || null,
  );
  const createMutation = useCreateComplaint();
  const updateMutation = useUpdateComplaint();

  const form = useForm<ComplaintSchemaType>({
    resolver: zodResolver(ComplaintSchema),
    defaultValues: {
      delivery_order_number: null,
      complaint_date: null,
      customer_type: null,
      customer_type_others: null,
      within_warranty: null,
      product_type: null,
      defects_discovered: null,
      complaint_type: null,
      defect_description: null,
      product_code: null,
      salesperson: null,
      customer_name: null,
      contact_person: null,
      contact_number: null,
      customer_address: null,
      project_title: null,
      contact_id: null,
      space_id: null,
      technical_team_response: null,
      attachments: [],
    },
    mode: 'onSubmit',
  });

  const [formInitialized, setFormInitialized] = useState(false);
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const updateAndReplyMutation = useUpdateComplaintAndReply();

  // Load complaint data when editing
  useEffect(() => {
    if (complaint && isEditMode && !formInitialized) {
      form.reset({
        delivery_order_number: complaint.delivery_order_number || null,
        complaint_date: complaint.complaint_date
          ? new Date(complaint.complaint_date)
          : null,
        customer_type: complaint.customer_type || null,
        customer_type_others: complaint.customer_type_others || null,
        within_warranty: complaint.within_warranty || null,
        product_type: complaint.product_type || null,
        defects_discovered: complaint.defects_discovered || null,
        complaint_type: complaint.complaint_type || null,
        defect_description: complaint.defect_description || null,
        product_code: complaint.product_code || null,
        salesperson: complaint.salesperson || null,
        customer_name: complaint.customer_name || null,
        contact_person: complaint.contact_person || null,
        contact_number: complaint.contact_number || null,
        customer_address: complaint.customer_address || null,
        project_title: complaint.project_title || null,
        contact_id: complaint.contact_id ?? null,
        space_id: complaint.space_id ?? null,
        technical_team_response: complaint.technical_team_response ?? null,
        attachments: complaint.attachments || [],
      });
      setFormInitialized(true);
    }
  }, [complaint, isEditMode, form, formInitialized]);

  useEffect(() => {
    setFormInitialized(false);
  }, [complaintId]);

  const onSubmit = async (data: ComplaintSchemaType) => {
    try {
      // Transform attachments to match ComplaintAttachment type
      // Filter out attachments that don't have required fields (id, complaint_id, uploaded_at)
      const validAttachments = (data.attachments || [])
        .filter((att): att is ComplaintAttachment => 
          !!att.id && !!att.complaint_id && !!att.uploaded_at
        )
        .map((att) => ({
          id: att.id!,
          complaint_id: att.complaint_id!,
          file_name: att.file_name ?? null,
          file_url: att.file_url ?? null,
          file_size_bytes: att.file_size_bytes ?? null,
          uploaded_at: att.uploaded_at!,
        }));

      const formData: ComplaintFormData = {
        delivery_order_number: data.delivery_order_number || undefined,
        complaint_date: data.complaint_date || undefined,
        customer_type: data.customer_type || undefined,
        customer_type_others: data.customer_type_others || undefined,
        within_warranty: data.within_warranty || undefined,
        product_type: data.product_type || undefined,
        defects_discovered: data.defects_discovered || undefined,
        complaint_type: data.complaint_type || undefined,
        defect_description: data.defect_description || undefined,
        product_code: data.product_code || undefined,
        salesperson: data.salesperson || undefined,
        customer_name: data.customer_name || undefined,
        contact_person: data.contact_person || undefined,
        contact_number: data.contact_number || undefined,
        customer_address: data.customer_address || undefined,
        project_title: data.project_title || undefined,
        contact_id: data.contact_id || undefined,
        space_id: data.space_id || undefined,
        technical_team_response: data.technical_team_response || undefined,
        attachments: validAttachments.length > 0 ? validAttachments : undefined,
      };

      if (isEditMode && complaintId) {
        await updateMutation.mutateAsync({ id: complaintId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }

      onSuccess?.();
    } catch (error) {
      // Error is handled by the mutation
      console.error('Error submitting form:', error);
    }
  };

  const handleUpdateAndReplyClick = async () => {
    const valid = await form.trigger();
    if (!valid || !complaintId) return;
    setUpdateAndReplyDialogOpen(true);
  };

  const handleUpdateAndReplyConfirm = async () => {
    if (!complaintId) return;
    const data = form.getValues();
    const validAttachments = (data.attachments || [])
      .filter((att): att is ComplaintAttachment => !!att.id && !!att.complaint_id && !!att.uploaded_at)
      .map((att) => ({
        id: att.id!,
        complaint_id: att.complaint_id!,
        file_name: att.file_name ?? null,
        file_url: att.file_url ?? null,
        file_size_bytes: att.file_size_bytes ?? null,
        uploaded_at: att.uploaded_at!,
      }));
    const formData: ComplaintFormData = {
      delivery_order_number: data.delivery_order_number || undefined,
      complaint_date: data.complaint_date || undefined,
      customer_type: data.customer_type || undefined,
      customer_type_others: data.customer_type_others || undefined,
      within_warranty: data.within_warranty || undefined,
      product_type: data.product_type || undefined,
      defects_discovered: data.defects_discovered || undefined,
      complaint_type: data.complaint_type || undefined,
      defect_description: data.defect_description || undefined,
      product_code: data.product_code || undefined,
      salesperson: data.salesperson || undefined,
      customer_name: data.customer_name || undefined,
      contact_person: data.contact_person || undefined,
      contact_number: data.contact_number || undefined,
      customer_address: data.customer_address || undefined,
      project_title: data.project_title || undefined,
      contact_id: data.contact_id || undefined,
      space_id: data.space_id || undefined,
      technical_team_response: data.technical_team_response || undefined,
      attachments: validAttachments.length > 0 ? validAttachments : undefined,
    };
    try {
      await updateAndReplyMutation.mutateAsync({ id: complaintId, data: formData });
      setUpdateAndReplyDialogOpen(false);
      onSuccess?.();
    } catch {
      // Error toast from mutation
    }
  };

  if (isEditMode && isLoadingComplaint) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending || updateAndReplyMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        {isEditMode && complaintId && (
          <div className="flex justify-end">
            <ComplaintNavigation complaintId={complaintId} />
          </div>
        )}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Column */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Complaint Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="delivery_order_number"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Delivery Order Number</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter DO number"
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
                  name="complaint_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Complaint Date</FormLabel>
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
                  name="customer_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Customer Type</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value || ''}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select customer type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="individual">Individual</SelectItem>
                          <SelectItem value="corporate">Corporate</SelectItem>
                          <SelectItem value="government">Government</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {form.watch('customer_type') === 'other' && (
                  <FormField
                    control={form.control}
                    name="customer_type_others"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Customer Type (Other)</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="Specify customer type"
                            {...field}
                            value={field.value || ''}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                <FormField
                  control={form.control}
                  name="within_warranty"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Within Warranty</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value || ''}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select warranty status" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="yes">Yes</SelectItem>
                          <SelectItem value="no">No</SelectItem>
                          <SelectItem value="unknown">Unknown</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="product_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Product Type</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter product type"
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
                  name="defects_discovered"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Defects Discovered</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter defects discovered"
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
                  name="complaint_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Complaint Type</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter complaint type"
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
                  name="defect_description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Defect Description</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter detailed defect description"
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

          {/* Right Column */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Product & Customer Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
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
                  name="customer_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Customer Name</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter customer name"
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
                  name="contact_person"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contact Person</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter contact person name"
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
                  name="contact_number"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contact Number</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter contact number"
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
                  name="customer_address"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Customer Address</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter customer address"
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
                  name="project_title"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Project Title</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Enter project title"
                          {...field}
                          value={field.value || ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Respond conversation</CardTitle>
                <FormDescription>
                  Optional: set Contact ID and Space ID (from respond.io) to build the conversation inbox URL. When provided on create/update, the URL is generated automatically.
                </FormDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {complaint?.respond_inbox_url && (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Respond Inbox</p>
                    <a
                      href={complaint.respond_inbox_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline text-sm break-all"
                    >
                      {complaint.respond_inbox_url}
                    </a>
                  </div>
                )}
                <FormField
                  control={form.control}
                  name="contact_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contact ID</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Respond.io contact ID"
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
                  name="space_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Space ID</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Respond.io space ID"
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
                  name="technical_team_response"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Technical Team Response</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter technical team response to send to customer"
                          {...field}
                          value={field.value ?? ''}
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

        {isEditMode && complaintId && (
          <ComplaintManualAttachmentsSection
            complaintId={complaintId}
            attachments={complaint?.attachments ?? []}
          />
        )}

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
              onClick={handleUpdateAndReplyClick}
              disabled={isLoading}
            >
              {updateAndReplyMutation.isPending ? (
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
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="size-4" />
                {isEditMode ? 'Update Complaint' : 'Create Complaint'}
              </>
            )}
          </Button>
        </div>
      </form>

      <AlertDialog open={updateAndReplyDialogOpen} onOpenChange={setUpdateAndReplyDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Update & Reply</AlertDialogTitle>
            <AlertDialogDescription>
              This will save your changes and send the technical team response to the
              customer via Respond.io. The conversation will be marked as responded.
              Continue?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={updateAndReplyMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleUpdateAndReplyConfirm();
              }}
              disabled={updateAndReplyMutation.isPending}
            >
              {updateAndReplyMutation.isPending ? 'Sending...' : 'Update & Reply'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Form>
  );
}
