'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save } from 'lucide-react';
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
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateSLAPolicy, useUpdateSLAPolicy, useSLAPolicy } from '../hooks/useSLAPolicies';
import { SLAPolicySchema, type SLAPolicySchemaType } from '../forms/sla-policy-schema';
import type { SLAPolicyFormData } from '../types/slaPolicy.types';

interface SLAPolicyFormProps {
  slaPolicyId?: string;
  onSuccess?: () => void;
}

export default function SLAPolicyForm({ slaPolicyId, onSuccess }: SLAPolicyFormProps) {
  const router = useRouter();
  const isEditMode = !!slaPolicyId;
  const { data: slaPolicy, isLoading: isLoadingSLAPolicy } = useSLAPolicy(slaPolicyId || null);
  const createMutation = useCreateSLAPolicy();
  const updateMutation = useUpdateSLAPolicy();

  const editValues = useMemo<SLAPolicySchemaType | undefined>(
    () =>
      slaPolicy && isEditMode
        ? {
            code: slaPolicy.code,
            name: slaPolicy.name,
            description: slaPolicy.description || '',
            is_active: slaPolicy.is_active,
          }
        : undefined,
    [slaPolicy, isEditMode],
  );

  const form = useForm<SLAPolicySchemaType>({
    resolver: zodResolver(SLAPolicySchema),
    defaultValues: {
      code: '',
      name: '',
      description: '',
      is_active: true,
    },
    // The record fills the form through `values`, not a reset scheduled in an
    // effect behind a `formInitialized` flag (S7-03): the flag meant a refetched
    // record never reached the inputs. Undefined in create mode, so defaults stand.
    values: editValues,
    // A refetch arriving mid-edit updates the fields nobody has touched and
    // leaves the ones being typed in alone.
    resetOptions: { keepDirtyValues: true },
    // A field answers when the reader leaves it, not on submit and not on every
    // keystroke.
    mode: 'onTouched',
  });

  const onSubmit = async (data: SLAPolicySchemaType) => {
    try {
      // Transform data to ensure proper format
      const formData: SLAPolicyFormData = {
        code: data.code,
        name: data.name,
        description: data.description || undefined,
        is_active: data.is_active,
      };

      if (isEditMode && slaPolicyId) {
        await updateMutation.mutateAsync({ id: slaPolicyId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }

      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/sla-management/sla-policies');
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('SLA policy form submission error:', error);
    }
  };

  if (isEditMode && isLoadingSLAPolicy) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{isEditMode ? 'Edit SLA Policy' : 'Create SLA Policy'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="SLA-001"
                        {...field}
                        disabled={isEditMode}
                      />
                    </FormControl>
                    <FormDescription>
                      Unique SLA policy identifier (alphanumeric, dashes, underscores only)
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
                    <FormLabel>Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="Enter SLA policy name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Enter description..."
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
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active Status</FormLabel>
                    <FormDescription>
                      Enable or disable this SLA policy
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

            <div className="flex justify-end gap-4 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (onSuccess) {
                    onSuccess();
                  } else {
                    router.push('/sla-management/sla-policies');
                  }
                }}
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
                    {isEditMode ? 'Update SLA Policy' : 'Create SLA Policy'}
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
