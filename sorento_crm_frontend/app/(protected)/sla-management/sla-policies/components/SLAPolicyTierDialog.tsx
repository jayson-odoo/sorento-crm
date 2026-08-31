'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { SLAPolicyTierSchema, type SLAPolicyTierFormInputType } from '../forms/sla-policy-schema';
import type { SLAPolicyTier } from '../types/slaPolicy.types';

interface SLAPolicyTierDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policyId: string;
  tier?: SLAPolicyTier | null;
}

/** Keep only digits and a single decimal point as the user types. */
function sanitizeDecimal(raw: string): string {
  const cleaned = raw.replace(/[^0-9.]/g, '');
  const firstDot = cleaned.indexOf('.');
  if (firstDot === -1) return cleaned;
  // collapse any dots after the first
  return cleaned.slice(0, firstDot + 1) + cleaned.slice(firstDot + 1).replace(/\./g, '');
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
  // Local string state for number inputs so user can clear and type (e.g. 72) without being blocked
  const [tierLevelStr, setTierLevelStr] = useState('');
  const [responseHoursStr, setResponseHoursStr] = useState('');
  const [resolutionHoursStr, setResolutionHoursStr] = useState('');

  // What the dialog opens on, fed through `values` rather than a reset scheduled
  // in an effect (S7-03). Both branches are the ones the effect had: the tier
  // being edited, or a blank first tier. The component stays mounted between
  // openings, so create mode has to name its values too - `undefined` there
  // would reopen on whatever the last tier left in the fields.
  const openValues = useMemo<SLAPolicyTierFormInputType | undefined>(() => {
    if (!open) return undefined;
    return tier && isEditMode
      ? {
          tier_level: tier.tier_level,
          tier_name: tier.tier_name,
          response_hours: Number(tier.response_hours),
          resolution_hours: Number(tier.resolution_hours ?? 24),
        }
      : { tier_level: 1, tier_name: '', response_hours: 24, resolution_hours: 24 };
  }, [open, tier, isEditMode]);

  const form = useForm<SLAPolicyTierFormInputType>({
    resolver: zodResolver(SLAPolicyTierSchema),
    defaultValues: {
      tier_level: 1,
      tier_name: '',
      response_hours: 24,
      resolution_hours: 24,
    },
    values: openValues,
    // A field answers when the reader leaves it, not on submit.
    mode: 'onTouched',
  });

  // The three number inputs keep their own string state so a half-typed "7" is
  // not coerced, so they still have to be seeded when the dialog opens - and
  // cleared when it closes, or reopening on a different tier shows the last one.
  useEffect(() => {
    if (!open) {
      setTierLevelStr('');
      setResponseHoursStr('');
      setResolutionHoursStr('');
      return;
    }
    setTierLevelStr(String(tier && isEditMode ? tier.tier_level : 1));
    setResponseHoursStr(String(tier && isEditMode ? Number(tier.response_hours) : 24));
    setResolutionHoursStr(
      String(tier && isEditMode ? Number(tier.resolution_hours ?? 24) : 24),
    );
  }, [open, tier, isEditMode]);

  const onSubmit = async (data: SLAPolicyTierFormInputType) => {
    // Use local number strings so values are correct; allow empty -> 1
    const tierLevel = Math.max(1, parseInt(tierLevelStr, 10) || 1);
    // Decimals allowed (0.5 = 30 min); floor at a small positive value.
    const responseHours = Math.max(0.01, parseFloat(responseHoursStr) || 0.01);
    const resolutionHours = Math.max(0.01, parseFloat(resolutionHoursStr) || 0.01);
    try {
      if (isEditMode && tier) {
        await updateMutation.mutateAsync({
          policyId,
          tierId: tier.id,
          data: {
            tier_level: tierLevel,
            tier_name: data.tier_name,
            response_hours: responseHours,
            resolution_hours: resolutionHours,
          },
        });
      } else {
        await createMutation.mutateAsync({
          policyId,
          data: {
            tier_level: tierLevel,
            tier_name: data.tier_name,
            response_hours: responseHours,
            resolution_hours: resolutionHours,
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
                      type="text"
                      inputMode="numeric"
                      placeholder="1"
                      {...field}
                      value={tierLevelStr}
                      onChange={(e) => setTierLevelStr(e.target.value.replace(/\D/g, ''))}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">Escalation order (1 = first tier).</p>
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
                      type="text"
                      inputMode="decimal"
                      placeholder="e.g. 0.5, 24 or 72"
                      {...field}
                      value={responseHoursStr}
                      onChange={(e) => setResponseHoursStr(sanitizeDecimal(e.target.value))}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">Hours to respond. Decimals allowed (0.5 = 30 minutes).</p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="resolution_hours"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Resolution Hours *</FormLabel>
                  <FormControl>
                    <Input
                      type="text"
                      inputMode="decimal"
                      placeholder="e.g. 0.5, 24 or 72"
                      {...field}
                      value={resolutionHoursStr}
                      onChange={(e) => setResolutionHoursStr(sanitizeDecimal(e.target.value))}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">Hours to resolve (KPI for resolution time). Decimals allowed (0.5 = 30 minutes).</p>
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
