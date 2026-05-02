'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { listRespondWorkspaceSelect } from '@/app/(protected)/system-management/respond-workspaces/services/respondWorkspaceService';
import type { RespondContact } from '../../types/contact.types';
import {
  ContactEditSchema,
  ContactEditSchemaType,
} from '../../forms/contact-edit-schema';

interface ContactEditDialogProps {
  open: boolean;
  closeDialog: () => void;
  contact: RespondContact;
}

export default function ContactEditDialog({
  open,
  closeDialog,
  contact,
}: ContactEditDialogProps) {
  const queryClient = useQueryClient();

  const form = useForm<ContactEditSchemaType>({
    resolver: zodResolver(ContactEditSchema),
    defaultValues: {
      phone_number: contact?.phone_number || '',
      name: contact?.name || '',
      user_type: contact?.user_type || '',
      workspace_id: contact?.workspace_id || '',
    },
    mode: 'onSubmit',
  });

  useEffect(() => {
    if (open && contact) {
      form.reset({
        phone_number: contact.phone_number || '',
        name: contact.name || '',
        user_type: contact.user_type || '',
        workspace_id: contact.workspace_id || '',
      });
    }
  }, [open, contact, form]);

  const { data: workspaces = [] } = useQuery({
    queryKey: ['respond-workspace-select'],
    queryFn: listRespondWorkspaceSelect,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const workspaceOptions = useMemo(
    () =>
      workspaces.map((w) => ({
        value: w.id,
        label: w.name?.trim() ? w.name : `Workspace ${w.space_id}`,
        description: `Space ID: ${w.space_id}${w.is_default ? ' • default' : ''}`,
        searchText: `${w.name ?? ''} ${w.space_id}`.trim(),
      })),
    [workspaces],
  );

  const mutation = useMutation({
    mutationFn: async (values: ContactEditSchemaType) => {
      const response = await apiFetch(`/api/user-management/contacts/${contact.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phone_number: values.phone_number,
          name: values.name || null,
          user_type: values.user_type || null,
          workspace_id: values.workspace_id ? values.workspace_id : null,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || error.message || 'Failed to update contact');
      }

      return response.json();
    },
    onSuccess: () => {
      const message = 'Contact updated successfully.';
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>{message}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );

      // Invalidate queries to refresh the data
      queryClient.invalidateQueries({ queryKey: ['respond-contact', contact.id] });
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });

      closeDialog();
    },
    onError: (error: Error) => {
      const message = error.message || 'Failed to update contact. Please try again.';
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{message}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );
    },
  });

  const handleSubmit = (values: ContactEditSchemaType) => {
    mutation.mutate(values);
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Edit Contact</DialogTitle>
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
                      placeholder="Contact name"
                      value={field.value || ''}
                      disabled={mutation.isPending}
                    />
                  </FormControl>
                  <FormDescription>
                    Optional: Contact name from Respond.io
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

            <FormField
              control={form.control}
              name="workspace_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Respond.io Workspace</FormLabel>
                  <FormControl>
                    <SearchableSelect
                      value={field.value ?? ''}
                      onChange={(v) => field.onChange(v || null)}
                      options={workspaceOptions}
                      placeholder={
                        workspaceOptions.length === 0
                          ? 'No workspaces configured'
                          : 'Select workspace…'
                      }
                      emptyMessage="No matching workspaces"
                      disabled={mutation.isPending || workspaceOptions.length === 0}
                    />
                  </FormControl>
                  <FormDescription>
                    Workspace this contact belongs to. Configure workspaces under{' '}
                    <span className="font-medium">System Management → Respond.io Workspaces</span>.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={closeDialog}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending && <LoaderCircleIcon className="mr-2 h-4 w-4 animate-spin" />}
                Update Contact
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
