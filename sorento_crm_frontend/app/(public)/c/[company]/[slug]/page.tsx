'use client';

/**
 * The published catalogue, at `/c/{companyCode}/{slug}`.
 *
 * No login, no CRM chrome. This is the link a dealer forwards to a customer.
 *
 * The company segment is not decoration: `slug` is unique PER COMPANY by
 * design, so Sorento and Mocha may each publish a "bathroom-2026". Without the
 * code the address could not resolve to one of them, and guessing would be a
 * cross-company leak.
 */

import { use, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, Box } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { CatalogueRenderer } from '@/app/(protected)/dealer-kit/components/CatalogueRenderer';
import { CataloguePickingProvider } from '@/app/(protected)/dealer-kit/components/TileGrid';
import { readPicks, togglePick, writePicks } from '@/lib/dealer-kit/cataloguePicks';
import {
  CatalogueNotFoundError,
  readPublishedCatalogue,
  type PublishedCatalogue,
} from '../../lib/publicCatalogueService';

type Status =
  | { state: 'loading' }
  | { state: 'ready'; page: PublishedCatalogue }
  | { state: 'missing' }
  | { state: 'error'; message: string };

export default function PublicCataloguePage({
  params,
}: {
  params: Promise<{ company: string; slug: string }>;
}) {
  const { company, slug } = use(params);
  const [status, setStatus] = useState<Status>({ state: 'loading' });

  /**
   * Products ticked while reading.
   *
   * This page is anonymous - it is the link a dealer forwards - so there is no
   * Selection to write to yet. The picks are kept in this browser and the room
   * designer turns them into real lines when it opens, which is also where the
   * login (if any) happens.
   */
  const [picked, setPicked] = useState<string[]>([]);
  useEffect(() => setPicked(readPicks()), []);
  useEffect(() => writePicks(picked), [picked]);

  useEffect(() => {
    let live = true;

    readPublishedCatalogue(company, slug)
      .then((page) => {
        if (live) setStatus({ state: 'ready', page });
      })
      .catch((error: unknown) => {
        if (!live) return;
        if (error instanceof CatalogueNotFoundError) {
          setStatus({ state: 'missing' });
          return;
        }
        setStatus({
          state: 'error',
          message: error instanceof Error ? error.message : 'Something went wrong.',
        });
      });

    return () => {
      live = false;
    };
  }, [company, slug]);

  if (status.state === 'loading') {
    return (
      <div className="mx-auto w-full max-w-[1400px] space-y-4 px-4 py-10 sm:px-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (status.state === 'missing') {
    return (
      <div className="mx-auto max-w-xl px-4 py-24 text-center">
        <h1 className="text-xl font-semibold text-foreground">This catalogue is not available</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The link may have expired, or the catalogue may not have been published yet. Ask
          whoever shared it for an up to date link.
        </p>
      </div>
    );
  }

  if (status.state === 'error') {
    return (
      <div className="mx-auto max-w-xl px-4 py-24">
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>Could not load this catalogue</AlertTitle>
          <AlertDescription>{status.message}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-background pb-24">
      <CataloguePickingProvider
        value={{
          picked,
          onToggle: (productId) => setPicked((current) => togglePick(current, productId)),
        }}
      >
        <CatalogueRenderer
          name={status.page.name}
          sections={status.page.doc.sections ?? []}
          resolvedCollections={status.page.collections}
          tileTemplates={status.page.tileTemplates}
          assets={status.page.assets}
        />
      </CataloguePickingProvider>

      {/*
        The bar appears only once something is ticked. A permanent call to
        action on a catalogue somebody is still reading is noise; one that shows
        up the moment they choose is an answer to what they just did.
      */}
      {picked.length > 0 && (
        <div
          className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 p-3 backdrop-blur"
          data-dk-picks-bar
        >
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-foreground">
              {picked.length} product{picked.length === 1 ? '' : 's'} chosen
            </span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setPicked([])}>
                Clear
              </Button>
              <Button size="sm" asChild>
                <Link href="/dealer-kit/design?picks=1">
                  <Box className="size-4" />
                  Put them in a room
                </Link>
              </Button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
