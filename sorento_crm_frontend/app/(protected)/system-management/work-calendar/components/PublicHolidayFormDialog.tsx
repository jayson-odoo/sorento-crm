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
import { PublicHolidaySchema, type PublicHolidaySchemaType } from '../forms/public-holiday-schema';
import type { PublicHoliday } from '../types/workCalendar.types';
import { useCreatePublicHoliday, useUpdatePublicHoliday } from '../hooks/useWorkCalendar';

interface PublicHolidayFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  holiday?: PublicHoliday | null;
}

export default function PublicHolidayFormDialog({
  open,
  onOpenChange,
  holiday,
}: PublicHolidayFormDialogProps) {
  const createMutation = useCreatePublicHoliday();
  const updateMutation = useUpdatePublicHoliday();
  const isEditMode = Boolean(holiday?.id);

  const form = useForm<PublicHolidaySchemaType>({
    resolver: zodResolver(PublicHolidaySchema),
    defaultValues: {
      date: '',
      name: '',
      description: '',
    },
  });

  useEffect(() => {
    if (holiday) {
      form.reset({
        date: holiday.date || '',
        name: holiday.name || '',
        description: holiday.description || '',
      });
    } else {
      form.reset({
        date: '',
        name: '',
        description: '',
      });
    }
  }, [holiday, form]);

  const onSubmit = (data: PublicHolidaySchemaType) => {
    if (isEditMode && holiday) {
      updateMutation.mutate(
        { id: holiday.id, data },
        { onSuccess: () => onOpenChange(false) },
      );
    } else {
      createMutation.mutate(data, { onSuccess: () => onOpenChange(false) });
    }
  };

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Edit Public Holiday' : 'Add Public Holiday'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Date</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Holiday name" {...field} />
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
                    <Textarea rows={3} placeholder="Optional description" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <LoaderCircleIcon className="animate-spin mr-2" />}
                {isEditMode ? 'Update' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
