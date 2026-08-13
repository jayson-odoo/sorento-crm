'use client';

import { useId, useState } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { usePlanningMode, useSavePlanningMode } from '../hooks/usePolicies';
import type { PlanningMode } from '../types/policy.types';

const OPTIONS: { value: PlanningMode['mode']; title: string; description: string }[] = [
  {
    value: 'auto',
    title: 'Auto',
    description: 'The engine computes the trigger line from demand, lead time and safety stock.',
  },
  {
    value: 'manual',
    title: 'Manual',
    description: 'The trigger line is the reorder level someone set (AutoCount round-trip).',
  },
];

/**
 * The ONE universal planning-mode switch (S1, UAC A). Reads/writes the GLOBAL
 * reorder_policy row's policy_type; per-product override rows keep winning where
 * they exist (AC-A3) - this only moves the default. Flipping applies to the NEXT
 * run only (AC-A2), so every change is confirmed before it saves.
 */
export function PlanningModePanel() {
  const { data, isLoading, isError } = usePlanningMode();
  const save = useSavePlanningMode();
  const [pending, setPending] = useState<PlanningMode['mode'] | null>(null);
  const groupId = useId();

  const current = data?.mode ?? 'auto';

  const onPick = (value: PlanningMode['mode']) => {
    if (value === current) return;
    setPending(value);
  };

  const onConfirm = async () => {
    if (!pending) return;
    await save.mutateAsync({ mode: pending });
    setPending(null);
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Planning mode</CardTitle>
          </CardHeading>
        </CardHeader>
        <CardContent className="space-y-4">
          {isError ? (
            <Alert variant="destructive">
              <AlertDescription>Failed to load planning mode.</AlertDescription>
            </Alert>
          ) : null}

          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <RadioGroup
              // Bound to the pending pick while the confirm dialog is open, not just
              // `current` - otherwise the radio silently reverts to the OLD value the
              // instant the buyer clicks the other option, until they confirm (Fix 7,
              // 2026-08-12). Cancelling the dialog clears `pending`, which snaps the
              // radio back to `current` on its own - no separate revert needed.
              value={pending ?? current}
              onValueChange={(v) => onPick(v as PlanningMode['mode'])}
              className="gap-3"
            >
              {OPTIONS.map((opt) => {
                const inputId = `${groupId}-${opt.value}`;
                return (
                  <div
                    key={opt.value}
                    className="flex items-start justify-between gap-3 rounded-md border border-border px-4 py-3"
                  >
                    <Label htmlFor={inputId} className="flex flex-col gap-1">
                      <span className="text-sm font-medium text-mono">{opt.title}</span>
                      <span className="text-xs text-secondary-foreground">{opt.description}</span>
                    </Label>
                    <RadioGroupItem
                      id={inputId}
                      value={opt.value}
                      aria-label={opt.title}
                      className="mt-1"
                    />
                  </div>
                );
              })}
            </RadioGroup>
          )}

          <p className="rounded-md bg-muted/40 px-3 py-2 text-2xs text-muted-foreground">
            Per-SKU or per-class overrides (set through policy rows) still win over this
            default - this only moves what a product falls back to.
          </p>
        </CardContent>
      </Card>

      <ConfirmActionDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
        title={pending === 'manual' ? 'Switch to manual planning?' : 'Switch to auto planning?'}
        description={
          pending === 'manual'
            ? 'Every SKU without its own override will trigger on its reorder level instead of a computed reorder point, starting with the next run. Runs already completed keep the basis they ran with.'
            : 'Every SKU without its own override will trigger on a computed reorder point instead of its reorder level, starting with the next run. Runs already completed keep the basis they ran with.'
        }
        confirmLabel={pending === 'manual' ? 'Switch to manual' : 'Switch to auto'}
        onConfirm={() => void onConfirm()}
        isBusy={save.isPending}
      />
    </>
  );
}
