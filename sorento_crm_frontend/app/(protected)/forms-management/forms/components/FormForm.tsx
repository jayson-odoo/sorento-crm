'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save, X } from 'lucide-react';
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
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useCreateForm, useUpdateForm, useForm as useFormQuery } from '../hooks/useForms';
import { FormSchema, type FormSchemaInput, type FormSchemaType } from '../forms/form-schema';
import type { FormFormData } from '../types/form.types';
import { useAttachments } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { formatDate } from '@/lib/helpers';
import { toast } from 'sonner';

interface FormFormProps {
  formId?: string;
  onSuccess?: () => void;
}

export default function FormForm({ formId, onSuccess }: FormFormProps) {
  const router = useRouter();
  const isEditMode = !!formId;
  const { data: form, isLoading: isLoadingForm } = useFormQuery(formId || null);
  const createMutation = useCreateForm();
  const updateMutation = useUpdateForm();

  const formHook = useForm<FormSchemaInput, unknown, FormSchemaType>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      code: '',
      name: '',
      form_type: 'marketing',
      purpose: null,
      language: 'en',
      is_active: false,
      attachment_id: null,
    },
    mode: 'onSubmit',
  });

  // Track if form has been initialized to prevent multiple resets
  const [formInitialized, setFormInitialized] = useState(false);

  const handlePreview = async (attachmentId: string) => {
    try {
      const previewUrl = await getAttachmentPreviewUrl(attachmentId);
      if (previewUrl) {
        window.open(previewUrl, '_blank');
      }
    } catch {
      toast.error('Failed to open attachment preview');
    }
  };

  // Load form data when editing
  useEffect(() => {
    if (form && isEditMode && !formInitialized) {
      const timeoutId = setTimeout(() => {
        formHook.reset({
          code: form.code,
          name: form.name,
          form_type: form.form_type || 'marketing',
          purpose: form.purpose || null,
          language: form.language,
          is_active: form.is_active,
          attachment_id: form.attachment_id || null,
        });
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    }
  }, [form, isEditMode, formHook, formInitialized]);

  // Reset formInitialized when formId changes
  useEffect(() => {
    setFormInitialized(false);
  }, [formId]);

  // Fetch attachments for selection
  const { data: attachmentsData } = useAttachments({
    pageIndex: 0,
    pageSize: 100,
    sorting: [],
    searchQuery: '',
  });
  const attachmentsList = attachmentsData?.data || [];
  const attachments = (() => {
    if (!form?.attachment) return attachmentsList;
    if (attachmentsList.some((a) => a.id === form.attachment!.id)) return attachmentsList;
    const merged = {
      ...form.attachment,
      uploaded_at: form.created_at,
    } as unknown as (typeof attachmentsList)[number];
    return [merged, ...attachmentsList];
  })();

  const onSubmit = async (data: FormSchemaType) => {
    try {
      const formData: FormFormData = {
        code: data.code,
        name: data.name,
        form_type: data.form_type,
        purpose: data.purpose || undefined,
        language: data.language,
        is_active: data.is_active,
        attachment_id: data.attachment_id || null,
      };

      if (isEditMode && formId) {
        await updateMutation.mutateAsync({ id: formId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }

      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/forms-management/forms');
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('Form submission error:', error);
    }
  };

  if (isEditMode && isLoadingForm) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;
  const selectedAttachmentId = formHook.watch('attachment_id');
  const selectedAttachment = selectedAttachmentId
    ? attachments.find((a) => a.id === selectedAttachmentId)
    : null;

  return (
    <Form {...formHook}>
      <form onSubmit={formHook.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{isEditMode ? 'Edit Form' : 'Create Form'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={formHook.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Form Code *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="FORM-001"
                        {...field}
                        disabled={isEditMode}
                      />
                    </FormControl>
                    <FormDescription>
                      Unique form identifier (alphanumeric, dashes, underscores only)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={formHook.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Form Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="Customer Feedback Form" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={formHook.control}
                name="form_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Form type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value || 'marketing'}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select form type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="marketing">Marketing</SelectItem>
                        <SelectItem value="registration">Registration</SelectItem>
                        <SelectItem value="application">Application</SelectItem>
                        <SelectItem value="feedback">Feedback</SelectItem>
                        <SelectItem value="survey">Survey</SelectItem>
                        <SelectItem value="complaint">Complaint</SelectItem>
                        <SelectItem value="internal">Internal</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Category for search and integrations (e.g. marketing for downloadable application forms)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={formHook.control}
              name="purpose"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Purpose</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Enter form purpose..."
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={formHook.control}
                name="language"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Language *</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value || 'en'}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select language" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="es">Spanish</SelectItem>
                        <SelectItem value="fr">French</SelectItem>
                        <SelectItem value="de">German</SelectItem>
                        <SelectItem value="it">Italian</SelectItem>
                        <SelectItem value="pt">Portuguese</SelectItem>
                        <SelectItem value="zh">Chinese</SelectItem>
                        <SelectItem value="ja">Japanese</SelectItem>
                        <SelectItem value="ko">Korean</SelectItem>
                        <SelectItem value="ar">Arabic</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={formHook.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Active Status</FormLabel>
                      <FormDescription>
                        Enable or disable this form
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

            {/* Attachment Selection */}
            <FormField
              control={formHook.control}
              name="attachment_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Attachment</FormLabel>
                  <div className="space-y-3">
                    <Select
                      value={field.value || '__none__'}
                      onValueChange={(value) => {
                        field.onChange(value === '__clear__' || value === '__none__' ? null : value);
                      }}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select an attachment or leave empty">
                            {selectedAttachment
                              ? selectedAttachment.original_filename
                              : 'No attachment selected'}
                          </SelectValue>
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="__none__">
                          <span className="text-muted-foreground">No attachment</span>
                        </SelectItem>
                        {field.value && (
                          <SelectItem value="__clear__">
                            <span className="flex items-center gap-2">
                              <X className="size-4" />
                              Clear attachment
                            </span>
                          </SelectItem>
                        )}
                        {attachments.map((attachment) => (
                          <SelectItem key={attachment.id} value={attachment.id}>
                            {attachment.original_filename}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {selectedAttachment && (
                      <div className="rounded-lg border p-3 bg-muted/50">
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <p className="font-medium text-sm">{selectedAttachment.original_filename}</p>
                            <p className="text-xs text-muted-foreground">
                              {selectedAttachment.file_size_bytes
                                ? `${(selectedAttachment.file_size_bytes / 1024).toFixed(2)} KB`
                                : '-'} •{' '}
                              {formatDate(new Date(selectedAttachment.uploaded_at))}
                            </p>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                handlePreview(selectedAttachment.id);
                              }}
                            >
                              Preview
                            </Button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  <FormDescription>
                    Optionally link an attachment to this form. You can clear it by selecting "Clear attachment".
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-4 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (onSuccess) {
                    onSuccess();
                  } else {
                    router.push('/forms-management/forms');
                  }
                }}
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
                    {isEditMode ? 'Update Form' : 'Create Form'}
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
