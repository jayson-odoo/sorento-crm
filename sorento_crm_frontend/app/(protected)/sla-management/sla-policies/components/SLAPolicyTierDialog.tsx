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
import { useCreateSLAPolicyTier, useUpdateSLAPolicyTier } from '../hooks/useSLAPolicies';
import { SLAPolicyTierSchema, type SLAPolicyTierSchemaType } from '../forms/sla-policy-schema';
import type { SLAPolicyTier } from '../types/slaPolicy.types';

interface SLAPolicyTierDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policyId: string;
  tier?: SLAPolicyTier | null;
}

export default function SLAPolicyTierDialog({
  open,
  onOpenChange,
  policyId,
  tier,
}: SLAPolicyTierDialogProps) {
  const isEditMode = !!tier;
  const createMutation = useCreateSLAPolicyTier();
  const updateMutation = useUpdateSLAPolicyTier();
  const [formInitialized, setFormInitialized] = useState(false);

  const form = useForm<SLAPolicyTierSchemaType>({
    resolver: zodResolver(SLAPolicyTierSchema),
    defaultValues: {
      tier_level: 1,
      tier_name: '',
      response_hours: 24,
    },
    mode: 'onSubmit',
  });

  // Load tier data when editing
  useEffect(() => {
    if (tier && isEditMode && !formInitialized && open) {
      const timeoutId = setTimeout(() => {
        form.reset({
          tier_level: tier.tier_level,
          tier_name: tier.tier_name,
          response_hours: tier.response_hours,
        });
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    } else if (!isEditMode && open) {
      form.reset({
        tier_level: 1,
        tier_name: '',
        response_hours: 24,
      });
      setFormInitialized(true);
    }
  }, [tier, isEditMode, form, open, formInitialized]);

  // Reset formInitialized when dialog closes
  useEffect(() => {
    if (!open) {
      setFormInitialized(false);
    }
  }, [open]);

  const onSubmit = async (data: SLAPolicyTierSchemaType) => {
    try {
      if (isEditMode && tier) {
        await updateMutation.mutateAsync({
          policyId,
          tierId: tier.id,
          data: {
            tier_level: data.tier_level,
            tier_name: data.tier_name,
            response_hours: data.response_hours,
          },
        });
      } else {
        await createMutation.mutateAsync({
          policyId,
          data: {
            tier_level: data.tier_level,
            tier_name: data.tier_name,
            response_hours: data.response_hours,
          },
        });
      }
      onOpenChange(false);
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('SLA policy tier form submission error:', error);
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? 'Edit SLA Policy Tier' : 'Add SLA Policy Tier'}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? 'Update the SLA policy tier details.'
              : 'Add a new tier to define response time requirements.'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="tier_level"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tier Level *</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="1"
                      {...field}
                      value={field.value}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 1)}
                      disabled={isEditMode}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="tier_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tier Name *</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Tier 1 - Initial Response"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="response_hours"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Response Hours *</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="24"
                      {...field}
                      value={field.value}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 1)}
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
