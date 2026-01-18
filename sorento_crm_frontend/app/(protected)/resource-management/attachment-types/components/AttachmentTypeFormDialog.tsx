'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { LoaderCircleIcon } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { Button } from '@/components/ui/button';
import {
  useCreateAttachmentType,
  useUpdateAttachmentType,
  useAttachmentType,
} from '../hooks/useAttachmentTypes';
import {
  AttachmentTypeSchema,
  type AttachmentTypeSchemaType,
} from '../forms/attachment-type-schema';
import type { AttachmentType } from '../types/attachmentType.types';

interface AttachmentTypeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentTypeId?: string | null;
}

export default function AttachmentTypeFormDialog({
  open,
  onOpenChange,
  attachmentTypeId,
}: AttachmentTypeFormDialogProps) {
  const isEditMode = !!attachmentTypeId;
  const { data: attachmentType, isLoading: isLoadingType } = useAttachmentType(attachmentTypeId || null);
  const createMutation = useCreateAttachmentType();
  const updateMutation = useUpdateAttachmentType();

  const form = useForm<AttachmentTypeSchemaType>({
    resolver: zodResolver(AttachmentTypeSchema),
    defaultValues: {
      type_name: '',
      description: '',
      allowed_extensions: '',
      max_file_size_mb: 10,
    },
    mode: 'onSubmit',
  });

  // Reset form when dialog opens or attachment type changes
  useEffect(() => {
    if (open) {
      if (isEditMode && attachmentType) {
        form.reset({
          type_name: attachmentType.type_name,
          description: attachmentType.description || '',
          allowed_extensions: attachmentType.allowed_extensions,
          max_file_size_mb: attachmentType.max_file_size_mb,
        });
      } else {
        form.reset({
          type_name: '',
          description: '',
          allowed_extensions: '',
          max_file_size_mb: 10,
        });
      }
    }
  }, [open, isEditMode, attachmentType, form]);

  const onSubmit = async (data: AttachmentTypeSchemaType) => {
    try {
      if (isEditMode && attachmentTypeId) {
        await updateMutation.mutateAsync({
          id: attachmentTypeId,
          data: {
            type_name: data.type_name,
            description: data.description || undefined,
            allowed_extensions: data.allowed_extensions,
            max_file_size_mb: data.max_file_size_mb,
          },
        });
      } else {
        await createMutation.mutateAsync({
          type_name: data.type_name,
          description: data.description || undefined,
          allowed_extensions: data.allowed_extensions,
          max_file_size_mb: data.max_file_size_mb,
        });
      }
      onOpenChange(false);
      form.reset();
    } catch (error) {
      // Error handled by mutation
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending || isLoadingType;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Edit Attachment Type' : 'Create Attachment Type'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="type_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Type Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., Document, Image" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Enter description"
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
              name="allowed_extensions"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Allowed Extensions *</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="e.g., pdf,doc,docx,jpg,png (comma-separated)"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="max_file_size_mb"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Max File Size (MB) *</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="10"
                      {...field}
                      value={field.value || ''}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading || !form.formState.isDirty}>
                {isLoading && <LoaderCircleIcon className="animate-spin mr-2" />}
                {isEditMode ? 'Update' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
