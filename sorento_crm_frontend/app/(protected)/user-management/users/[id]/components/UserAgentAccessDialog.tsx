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
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { UserAgentAccessSchema, type UserAgentAccessSchemaType } from '../../forms/user-agent-access-schema';

interface UserAgentAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId: string;
  agentId: string;
  agentName?: string;
  onSubmit?: (data: {
    agent_id: string;
    is_allowed: boolean;
    valid_from?: Date | null;
    valid_to?: Date | null;
  }) => void;
}

export default function UserAgentAccessDialog({
  open,
  onOpenChange,
  userId,
  agentId,
  agentName,
  onSubmit: onSubmitCallback,
}: UserAgentAccessDialogProps) {
  const queryClient = useQueryClient();
  const [formInitialized, setFormInitialized] = useState(false);
  const isInlineMode = !!onSubmitCallback;

  const form = useForm<UserAgentAccessSchemaType>({
    resolver: zodResolver(UserAgentAccessSchema),
    defaultValues: {
      agent_id: agentId,
      is_allowed: true,
      valid_from: undefined,
      valid_to: undefined,
    },
    mode: 'onSubmit',
  });

  // Reset form when dialog opens
  useEffect(() => {
    if (open && !formInitialized) {
      form.reset({
        agent_id: agentId,
        is_allowed: true,
        valid_from: undefined,
        valid_to: undefined,
      });
      setFormInitialized(true);
    }
  }, [open, agentId, form, formInitialized]);

  // Reset formInitialized when dialog closes
  useEffect(() => {
    if (!open) {
      setFormInitialized(false);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: async (data: UserAgentAccessSchemaType) => {
      const response = await apiFetch(`/api/user-management/users/${userId}/agents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          agent_id: data.agent_id,
          is_allowed: data.is_allowed,
          valid_from: data.valid_from ? data.valid_from.toISOString() : null,
          valid_to: data.valid_to ? data.valid_to.toISOString() : null,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || error.message || 'Failed to create user agent access');
      }

      return response.json();
    },
    onSuccess: () => {
      toast.success('Access agent added successfully');
      queryClient.invalidateQueries({ queryKey: ['user-user', userId] });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to add access agent');
    },
  });

  const onSubmit = async (data: UserAgentAccessSchemaType) => {
    try {
      if (isInlineMode && onSubmitCallback) {
        // Inline mode: just call the callback
        onSubmitCallback({
          agent_id: data.agent_id,
          is_allowed: data.is_allowed,
          valid_from: data.valid_from,
          valid_to: data.valid_to,
        });
        onOpenChange(false);
      } else {
        // Normal mode: create via API
        await mutation.mutateAsync(data);
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('User agent access form submission error:', error);
    }
  };

  const isLoading = mutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Add Access Agent</DialogTitle>
          <DialogDescription>
            {agentName ? `Configure access settings for ${agentName}` : 'Configure access settings for this agent'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
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
                    Adding...
                  </>
                ) : (
                  <>
                    <Save className="mr-2 size-4" />
                    Add Access Agent
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
