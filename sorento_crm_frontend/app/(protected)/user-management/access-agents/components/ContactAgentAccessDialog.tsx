'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { apiFetch } from '@/lib/api';
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import { ChevronDown, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useCreateContactAgentAccess, useUpdateContactAgentAccess } from '../hooks/useAccessAgents';
import { useQueryClient } from '@tanstack/react-query';
import { ContactAgentAccessSchema, type ContactAgentAccessSchemaType } from '../forms/access-agent-schema';
import type { ContactAgentAccess } from '../types/accessAgent.types';

interface ContactAgentAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessAgentId?: string;
  contactAccess?: ContactAgentAccess | null;
  defaultContactPhone?: string; // Contact phone number (required)
  defaultContactName?: string; // Contact name (optional)
  contactId?: string; // Contact ID for query invalidation
  accessAgents?: Array<{ id: string; name: string; code: string; is_active: boolean }>;
  showAgentSelection?: boolean; // If true, show agent selection dropdown
}

export default function ContactAgentAccessDialog({
  open,
  onOpenChange,
  accessAgentId = '',
  contactAccess,
  defaultContactPhone,
  defaultContactName,
  contactId,
  accessAgents = [],
  showAgentSelection = false,
}: ContactAgentAccessDialogProps) {
  const queryClient = useQueryClient();
  const isEditMode = !!contactAccess;
  const createMutation = useCreateContactAgentAccess();
  const updateMutation = useUpdateContactAgentAccess();
  const [formInitialized, setFormInitialized] = useState(false);
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [agentSearchQuery, setAgentSearchQuery] = useState('');

  const form = useForm<ContactAgentAccessSchemaType>({
    resolver: zodResolver(ContactAgentAccessSchema),
    defaultValues: {
      respond_contact_phone: '',
      respond_contact_name: '',
      agent_id: accessAgentId || '',
      agent_ids: [] as string[],
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
          respond_contact_phone: contactAccess.respond_contact_phone,
          respond_contact_name: contactAccess.respond_contact_name || '',
          agent_id: contactAccess.agent_id,
          agent_ids: [],
          is_allowed: contactAccess.is_allowed,
          valid_from: contactAccess.valid_from ? new Date(contactAccess.valid_from) : undefined,
          valid_to: contactAccess.valid_to ? new Date(contactAccess.valid_to) : undefined,
        });
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    } else if (!isEditMode && open) {
form.reset({
          respond_contact_phone: defaultContactPhone || '',
          respond_contact_name: '',
          agent_id: accessAgentId || '',
          agent_ids: [],
          is_allowed: true,
          valid_from: undefined,
          valid_to: undefined,
        });
      setFormInitialized(true);
    }
  }, [contactAccess, isEditMode, form, open, accessAgentId, formInitialized, defaultContactPhone]);

  // Reset formInitialized when dialog closes
  useEffect(() => {
    if (!open) {
      setFormInitialized(false);
    }
  }, [open]);

  const onSubmit = async (data: ContactAgentAccessSchemaType) => {
    try {
      // Use defaultContactPhone and defaultContactName from contact
      const contactPhone = defaultContactPhone || data.respond_contact_phone;
      const contactName = defaultContactName || data.respond_contact_name || undefined;

      if (isEditMode && contactAccess) {
        await updateMutation.mutateAsync({
          agentId: accessAgentId || '',
          contactId: contactAccess.id,
          data: {
            respond_contact_phone: contactPhone,
            respond_contact_name: contactName,
            is_allowed: data.is_allowed,
            valid_from: data.valid_from ?? undefined,
            valid_to: data.valid_to ?? undefined,
          },
        });
      } else {
        const agentIds = (data.agent_ids?.length ? data.agent_ids : [data.agent_id || accessAgentId].filter(Boolean)) as string[];
        if (!agentIds.length) {
          throw new Error('Select at least one access agent');
        }
        if (!contactPhone) {
          throw new Error('Contact phone is required');
        }
        for (const agentId of agentIds) {
          await createMutation.mutateAsync({
            agentId,
            data: {
              respond_contact_phone: contactPhone,
              respond_contact_name: contactName,
              agent_id: agentId,
              is_allowed: data.is_allowed,
              valid_from: data.valid_from ?? undefined,
              valid_to: data.valid_to ?? undefined,
            },
          });
        }
      }
      // Invalidate contact-specific queries if contactId is provided
      if (contactId) {
        queryClient.invalidateQueries({ queryKey: ['contact-access-agents', contactId] });
      }
      onOpenChange(false);
    } catch (error: any) {
      // Error is handled by the mutation hook, but we can add additional handling here if needed
      console.error('Contact access agent form submission error:', error);
      // The mutation hook will show the error toast
    }
  };

  // Removed lookup function as respond_contact_name doesn't exist in database

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
              : 'Add a new contact access agent by configuring the access settings.'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {showAgentSelection && !isEditMode && (
              <FormField
                control={form.control}
                name="agent_ids"
                render={({ field }) => {
                  const activeAgents = accessAgents.filter((a) => a.is_active);
                  const q = (agentSearchQuery ?? '').trim().toLowerCase();
                  const filteredAgents = q
                    ? activeAgents.filter(
                        (a) =>
                          a.name.toLowerCase().includes(q) || a.code.toLowerCase().includes(q),
                      )
                    : activeAgents;
                  const selectedIds = field.value ?? [];
                  const allFilteredSelected =
                    filteredAgents.length > 0 &&
                    filteredAgents.every((a) => selectedIds.includes(a.id));
                  const someFilteredSelected = filteredAgents.some((a) => selectedIds.includes(a.id));
                  return (
                    <FormItem>
                      <FormLabel>Access Agent(s) *</FormLabel>
                      <FormControl>
<Popover
                          onOpenChange={(open) => {
                            if (!open) setAgentSearchQuery('');
                          }}
                        >
                        <PopoverTrigger asChild>
                            <Button
                              variant="outline"
                              role="combobox"
                              className={cn(
                                'w-full justify-between font-normal',
                                !field.value?.length && 'text-muted-foreground',
                              )}
                            >
                              {field.value?.length
                                ? `${field.value.length} agent${field.value.length !== 1 ? 's' : ''} selected`
                                : 'Select access agent(s)'}
                              <ChevronDown className="ml-2 size-4 shrink-0 opacity-50" />
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent
                            className="w-[var(--radix-popover-trigger-width)] p-0"
                            align="start"
                            onOpenAutoFocus={(e) => e.preventDefault()}
                          >
                            <div className="p-2 border-b">
                              <div className="relative">
                                <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                  placeholder="Search agents..."
                                  value={agentSearchQuery}
                                  onChange={(e) => setAgentSearchQuery(e.target.value)}
                                  className="pl-8 h-9"
                                />
                              </div>
                            </div>
                            <label className="flex items-center gap-2 px-3 py-2 text-sm font-medium cursor-pointer border-b hover:bg-accent/50">
                              <Checkbox
                                checked={allFilteredSelected ? true : someFilteredSelected ? 'indeterminate' : false}
                                onCheckedChange={(checked) => {
                                  if (checked) {
                                    const add = filteredAgents.map((a) => a.id);
                                    field.onChange(Array.from(new Set([...selectedIds, ...add])));
                                  } else {
                                    const remove = new Set(filteredAgents.map((a) => a.id));
                                    field.onChange(selectedIds.filter((id) => !remove.has(id)));
                                  }
                                }}
                              />
                              Select all
                            </label>
                            <ScrollArea className="h-[280px]">
                              <div className="p-2 space-y-0.5">
                                {filteredAgents.length === 0 ? (
                                  <p className="py-4 text-center text-sm text-muted-foreground">
                                    No agents match your search.
                                  </p>
                                ) : (
                                  filteredAgents.map((agent) => (
                                    <label
                                      key={agent.id}
                                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground"
                                    >
                                      <Checkbox
                                        checked={selectedIds.includes(agent.id)}
                                        onCheckedChange={(checked) => {
                                          const next = checked
                                            ? [...selectedIds, agent.id]
                                            : selectedIds.filter((id) => id !== agent.id);
                                          field.onChange(next);
                                        }}
                                      />
                                      {agent.name} ({agent.code})
                                    </label>
                                  ))
                                )}
                              </div>
                            </ScrollArea>
                          </PopoverContent>
                        </Popover>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  );
                }}
              />
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
