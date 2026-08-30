'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
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
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import {
  useCreateComplaintRootCause,
  useUpdateComplaintRootCause,
  useComplaintRootCause,
} from '../hooks/useComplaintRootCauses';
import type { ComplaintRootCauseFormData } from '../types/complaintRootCause.types';

const FormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(150),
  description: z.string().max(2000).optional().nullable(),
  is_active: z.boolean(),
});

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rowId?: string;
}

export default function ComplaintRootCauseFormDialog({ open, onOpenChange, rowId }: Props) {
  const { data: row } = useComplaintRootCause(rowId || null);
  const createMutation = useCreateComplaintRootCause();
  const updateMutation = useUpdateComplaintRootCause();

  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    mode: 'onTouched',
    defaultValues: { name: '', description: '', is_active: true },
  });

  useEffect(() => {
    if (open) {
      if (rowId && row) {
        form.reset({
          name: row.name,
          description: row.description || '',
          is_active: row.is_active,
        });
      } else {
        form.reset({ name: '', description: '', is_active: true });
      }
    }
  }, [open, form, rowId, row]);

  const onSubmit = async (data: z.infer<typeof FormSchema>) => {
    try {
      const payload: ComplaintRootCauseFormData = {
        name: data.name,
        description: data.description ?? undefined,
        is_active: data.is_active,
      };
      if (rowId) {
        await updateMutation.mutateAsync({ id: rowId, data: payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onOpenChange(false);
      form.reset();
    } catch {
      /* handled in mutation onError */
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{rowId ? 'Edit Root Cause' : 'Create Root Cause'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Manufacturing defect" {...field} />
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
                      placeholder="Optional description"
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
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active</FormLabel>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {rowId ? 'Update' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
