'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import {
  Alert,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
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
  FormDescription,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { LoaderCircleIcon } from 'lucide-react';
import {
  ContactCreateSchema,
  ContactCreateSchemaType,
} from '../forms/contact-create-schema';

interface ContactCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ContactCreateDialog({
  open,
  onOpenChange,
}: ContactCreateDialogProps) {
  const queryClient = useQueryClient();

  const form = useForm<ContactCreateSchemaType>({
    resolver: zodResolver(ContactCreateSchema),
    defaultValues: {
      phone_number: '',
      name: '',
      user_type: '',
    },
    mode: 'onSubmit',
  });

  useEffect(() => {
    if (open) {
      form.reset({ phone_number: '', name: '', user_type: '' });
    }
  }, [open, form]);

  const mutation = useMutation({
    mutationFn: async (values: ContactCreateSchemaType) => {
      const response = await apiFetch('/api/user-management/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: values.phone_number,
          name: values.name || null,
          user_type: values.user_type || null,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || error.message || 'Failed to create contact');
      }

      return response.json();
    },
    onSuccess: () => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>Contact created successfully.</AlertTitle>
          </Alert>
        ),
        { position: 'top-center' },
      );

      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message || 'Failed to create contact. Please try again.'}</AlertTitle>
          </Alert>
        ),
        { position: 'top-center' },
      );
    },
  });

  const handleSubmit = (values: ContactCreateSchemaType) => {
    mutation.mutate(values);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Create Contact</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-5">
            <FormField
              control={form.control}
              name="phone_number"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Phone Number</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      id="phone_number"
                      type="tel"
                      placeholder="+1234567890"
                      disabled={mutation.isPending}
                    />
                  </FormControl>
                  <FormDescription>
                    Enter phone number in E.164 format (e.g., +1234567890)
                  </FormDescription>
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
                    <Input
                      {...field}
                      id="name"
                      type="text"
                      placeholder="Contact name (optional)"
                      value={field.value || ''}
                      disabled={mutation.isPending}
                    />
                  </FormControl>
                  <FormDescription>
                    Optional: Contact name
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="user_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>User Type</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      id="user_type"
                      type="text"
                      placeholder="User type (optional)"
                      value={field.value || ''}
                      disabled={mutation.isPending}
                    />
                  </FormControl>
                  <FormDescription>
                    Optional: Synced from Respond.io or set manually
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending && <LoaderCircleIcon className="mr-2 h-4 w-4 animate-spin" />}
                Create Contact
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
