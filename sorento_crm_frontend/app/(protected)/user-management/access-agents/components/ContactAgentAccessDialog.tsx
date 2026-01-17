'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Switch } from '@/components/ui/switch';
import { useCreateContactAgentAccess, useUpdateContactAgentAccess } from '../hooks/useAccessAgents';
import { ContactAgentAccessSchema, type ContactAgentAccessSchemaType } from '../forms/access-agent-schema';
import type { ContactAgentAccess } from '../types/accessAgent.types';

interface ContactAgentAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessAgentId: string;
  contactAccess?: ContactAgentAccess | null;
}

export default function ContactAgentAccessDialog({
  open,
  onOpenChange,
  accessAgentId,
  contactAccess,
}: ContactAgentAccessDialogProps) {
  const isEditMode = !!contactAccess;
  const createMutation = useCreateContactAgentAccess();
  const updateMutation = useUpdateContactAgentAccess();
  const [formInitialized, setFormInitialized] = useState(false);

  const form = useForm<ContactAgentAccessSchemaType>({
    resolver: zodResolver(ContactAgentAccessSchema),
    defaultValues: {
      respond_contact_id: '',
      agent_id: accessAgentId,
      is_allowed: true,
      valid_from: undefined,
      valid_to: undefined,
    },
    mode: 'onSubmit',
  });

  // Load contact access data when editing
  useEffect(() => {
    if (contactAccess && isEditMode && !formInitialized && open) {
      const timeoutId = setTimeout(() => {
        form.reset({
          respond_contact_id: contactAccess.respond_contact_id,
          agent_id: contactAccess.agent_id,
          is_allowed: contactAccess.is_allowed,
          valid_from: contactAccess.valid_from ? new Date(contactAccess.valid_from) : undefined,
          valid_to: contactAccess.valid_to ? new Date(contactAccess.valid_to) : undefined,
        });
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    } else if (!isEditMode && open) {
      form.reset({
        respond_contact_id: '',
        agent_id: accessAgentId,
        is_allowed: true,
        valid_from: undefined,
        valid_to: undefined,
      });
      setFormInitialized(true);
    }
  }, [contactAccess, isEditMode, form, open, accessAgentId, formInitialized]);

  // Reset formInitialized when dialog closes
  useEffect(() => {
    if (!open) {
      setFormInitialized(false);
    }
  }, [open]);

  const onSubmit = async (data: ContactAgentAccessSchemaType) => {
    try {
      if (isEditMode && contactAccess) {
        await updateMutation.mutateAsync({
          agentId: accessAgentId,
          contactId: contactAccess.id,
          data: {
            respond_contact_id: data.respond_contact_id,
            is_allowed: data.is_allowed,
            valid_from: data.valid_from ?? undefined,
            valid_to: data.valid_to ?? undefined,
          },
        });
      } else {
        await createMutation.mutateAsync({
          agentId: accessAgentId,
          data: {
            respond_contact_id: data.respond_contact_id,
            agent_id: accessAgentId,
            is_allowed: data.is_allowed,
            valid_from: data.valid_from ?? undefined,
            valid_to: data.valid_to ?? undefined,
          },
        });
      }
      onOpenChange(false);
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('Contact access agent form submission error:', error);
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? 'Edit Contact Access Agent' : 'Add Contact Access Agent'}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? 'Update the contact access agent details.'
              : 'Add a new contact access agent by specifying the respond contact ID and validity period.'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="respond_contact_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Respond Contact ID *</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Enter contact ID"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="valid_from"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Valid From</FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        {...field}
                        value={field.value ? field.value.toISOString().split('T')[0] : ''}
                        onChange={(e) => field.onChange(e.target.value ? new Date(e.target.value) : undefined)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="valid_to"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Valid To</FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        {...field}
                        value={field.value ? field.value.toISOString().split('T')[0] : ''}
                        onChange={(e) => field.onChange(e.target.value ? new Date(e.target.value) : undefined)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="is_allowed"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Allowed</FormLabel>
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

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
                    {isEditMode ? 'Updating...' : 'Creating...'}
                  </>
                ) : (
                  <>
                    <Save className="mr-2 size-4" />
                    {isEditMode ? 'Update' : 'Create'}
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
