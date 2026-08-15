'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Package, Plus, Search, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { BundleCard } from '../../components/BundleCard';
import { deleteBundle, listBundles } from '../../services/catalogueService';
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
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<ResolvedBundle | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dealer-kit', 'bundles'],
    queryFn: listBundles,
  });

  const bundles = useMemo(() => {
    const all = data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    // A bundle carries no description of its own - what filters here is the
    // name and the parts underneath it, since those are what the card shows.
    return all.filter(
      (bundle) =>
        bundle.name.toLowerCase().includes(needle) ||
        bundle.components.some((component) =>
          component.productName.toLowerCase().includes(needle),
        ),
    );
  }, [data, search]);

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
      <CardHeader className="flex-wrap gap-2 py-5">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="ps-9"
            placeholder="Search bundles"
            aria-label="Search bundles"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" />
          New bundle
        </Button>
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
            <p className="mt-3 text-sm font-medium text-foreground">
              {search.trim() ? 'No bundles match that search' : 'No bundles yet'}
            </p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              {search.trim()
                ? 'Try a different name.'
                : 'A bundle sells several products together under one price. Create one, then drop a bundle block onto any catalogue page.'}
            </p>
            {!search.trim() && (
              <Button className="mt-4" size="sm" onClick={() => setCreating(true)}>
                <Plus className="size-4" />
                New bundle
              </Button>
            )}
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
                  onClick={() => setDeleting(bundle)}
                >
                  <Trash2 className="size-4 text-destructive" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <BundleDialog open={creating} onOpenChange={setCreating} />

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Confirm delete"
        description={
          <>
            Delete <strong>{deleting?.name}</strong>? Any page showing it loses the block&rsquo;s
            contents. This action cannot be undone.
          </>
        }
        successMessage="Bundle deleted"
        queryKeysToInvalidate={[['dealer-kit', 'bundles']]}
        onDelete={async () => {
          if (deleting) await deleteBundle(deleting.id);
        }}
      />
    </Card>
  );
}
