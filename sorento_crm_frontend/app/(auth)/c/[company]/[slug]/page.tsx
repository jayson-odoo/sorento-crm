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
import { AlertCircle } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { CatalogueRenderer } from '@/app/(protected)/dealer-kit/components/CatalogueRenderer';
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
    <main className="min-h-screen bg-background">
      <CatalogueRenderer
        name={status.page.name}
        sections={status.page.doc.sections ?? []}
        resolvedCollections={status.page.collections}
        tileTemplates={status.page.tileTemplates}
      />
    </main>
  );
}
