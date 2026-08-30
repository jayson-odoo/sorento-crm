'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Package, Plus, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import {
  useDeferredRowAction,
  useRowPending,
} from '@/hooks/useDeferredRowAction';
import { Skeleton } from '@/components/ui/skeleton';
import { BundleCard } from '../../components/BundleCard';
import { listBundles } from '../../services/catalogueService';
import { BundleDialog } from './BundleDialog';
import type { ResolvedBundle } from '@/lib/dealer-kit/types';

/**
 * Bundles, shown as the cards they render as.
 *
 * A grid of real `BundleCard`s rather than a DataGrid, because the thing worth
 * checking about a bundle is what a customer sees: one price, the parts
 * beneath, and whether it can actually be ordered. A table of names and totals
 * would hide exactly the detail that matters.
 *
 * Availability comes back derived from the components on every load, so a
 * bundle whose part was discontinued this morning reads as unavailable here
 * without anyone having edited it.
 */
export function BundlesList() {
  const [creating, setCreating] = useState(false);
  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel.
  const deletion = useDeferredRowAction({
    actionKey: 'dk_bundle.delete',
    entityType: 'dk_bundle',
    successMessage: 'Bundle deleted',
    invalidateKeys: [['dealer-kit', 'bundles']],
  });
  const rowPending = useRowPending<ResolvedBundle>('dk_bundle');

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dealer-kit', 'bundles'],
    queryFn: listBundles,
  });

  const bundles = useMemo(() => data ?? [], [data]);

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load bundles</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : 'Something went wrong. Try again.'}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card>
      <CardHeader className="block py-5">
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            New bundle
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((row) => (
              <Skeleton key={row} className="h-40 w-full" />
            ))}
          </div>
        )}

        {!isLoading && bundles.length === 0 && (
          <div className="py-10 text-center">
            <Package className="mx-auto size-6 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium text-foreground">No bundles yet</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              A bundle sells several products together under one price. Create one, then drop a
              bundle block onto any catalogue page.
            </p>
            <Button className="mt-4" size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-4" />
              New bundle
            </Button>
          </div>
        )}

        {!isLoading && bundles.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {bundles.map((bundle) => (
              // The action belongs ON the card. Stacked underneath it reads as a
              // detached control that could apply to anything.
              <div key={bundle.id} className="relative">
                <BundleCard bundle={bundle} />
                <Button
                  variant="ghost"
                  size="sm"
                  className="absolute end-1 top-1 bg-background/80"
                  aria-label={`Delete ${bundle.name}`}
                  onClick={() => deletion.run({ id: bundle.id, subject: bundle.name })}
                >
                  <Trash2 className="size-4 text-destructive" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <BundleDialog open={creating} onOpenChange={setCreating} />

    </Card>
  );
}
