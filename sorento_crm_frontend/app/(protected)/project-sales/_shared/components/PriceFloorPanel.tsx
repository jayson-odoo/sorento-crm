'use client';

import * as React from 'react';
import { LoaderCircleIcon, RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useEffectivePriceFloor, usePriceFloorMutations } from '../hooks/useProjects';
import { describeEffectiveFloor, describeFloorSource } from '../lib/priceFloor';
import type { FloorTargetLevel } from '../types/project.types';
import { PriceFloorDialog } from './PriceFloorDialog';

const NOUN: Record<FloorTargetLevel, string> = {
  product: 'product',
  category: 'category',
};

/**
 * The floor for ONE product or ONE category, where the person editing it is standing.
 *
 * Three things, in this order, because that is the order the questions get asked:
 * what applies, where it comes from, and what I can do about it. The middle one is the
 * reason this exists - a product with no rule of its own is still governed by a floor,
 * and a panel that showed only "none set" would be a lie by omission.
 *
 * It saves ON ITS OWN, not with the surrounding form. The floor is a separate row in
 * price_floor_rules, not a product column: folding it into the product's submit would
 * mean one button writing two resources, able to half-succeed, with no honest thing to
 * say when the second write failed after the first had already gone through. So the
 * panel owns its own save, its own toast, and its own failure.
 */
export function PriceFloorPanel({
  target,
  disabledReason,
}: {
  target: { level: FloorTargetLevel; id: string; label: string } | null;
  /** Shown instead of the floor when there is nothing to read it for yet (unsaved record). */
  disabledReason?: string;
}) {
  const query = useEffectivePriceFloor(target ? { level: target.level, id: target.id } : null);
  const { remove } = usePriceFloorMutations();
  const [editing, setEditing] = React.useState(false);
  const [clearing, setClearing] = React.useState(false);

  const noun = target ? NOUN[target.level] : 'record';
  const data = query.data;
  const own = data?.own_rule ?? null;
  const effective = data?.effective ?? null;

  return (
    <section className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="min-w-0 break-words text-sm font-medium">Price floor</h3>
        {own && !own.is_active && <Badge variant="secondary">Switched off</Badge>}
      </div>

      {!target ? (
        <p className="text-sm text-muted-foreground">
          {disabledReason ?? `Save the ${noun} first, then set its floor here.`}
        </p>
      ) : query.isLoading ? (
        <div className="space-y-2" data-testid="price-floor-loading">
          <Skeleton className="h-4 w-52" />
          <Skeleton className="h-3 w-36" />
        </div>
      ) : query.isError ? (
        <div className="space-y-2">
          <p className="text-sm text-destructive">
            {(query.error as Error)?.message ?? 'Could not load the price floor.'}
          </p>
          <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
            <RefreshCw className="size-4" aria-hidden />
            Try again
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {effective ? (
            <div className="space-y-1">
              <p className="min-w-0 break-words text-sm font-medium">
                {describeEffectiveFloor(effective)}
              </p>
              <p className="min-w-0 break-words text-xs text-muted-foreground">
                {describeFloorSource(effective, target.level)}
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No floor applies to this {noun}. Any quoted price is accepted without an
              alert.
            </p>
          )}

          {own && !own.is_active && (
            <p className="text-xs text-muted-foreground">
              This {noun} has a floor of its own, but it is switched off, so the level
              above decides instead.
            </p>
          )}

          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)}>
              {own ? `Change this ${noun}'s floor` : `Set a floor for this ${noun}`}
            </Button>
            {own && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setClearing(true)}
                disabled={remove.isPending}
              >
                {remove.isPending && (
                  <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />
                )}
                Clear this {noun}&apos;s floor
              </Button>
            )}
          </div>
        </div>
      )}

      {editing && target && (
        <PriceFloorDialog
          rule={own}
          lockedTarget={{ level: target.level, id: target.id, label: target.label }}
          onDone={() => setEditing(false)}
        />
      )}

      <ConfirmDeleteDialog
        open={clearing}
        onOpenChange={setClearing}
        title="Confirm delete"
        description={
          own
            ? `Remove the floor set on "${target?.label ?? ''}"? This action cannot be undone. ` +
              `The ${noun} then falls back to whatever the level above it says, which may be no floor at all. ` +
              `Lines already priced keep the floor that applied to them.`
            : ''
        }
        onDelete={async () => {
          if (!own) return;
          await remove.mutateAsync(own.id);
        }}
        onSuccess={() => setClearing(false)}
        successMessage="Price floor removed"
      />
    </section>
  );
}
