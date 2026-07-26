'use client';

/**
 * The page headless Chromium prints.
 *
 * It renders the SAME `CatalogueRenderer` the editor and the public catalogue
 * use, which is what makes "the PDF matches the screen" structural rather than
 * a promise. A separate print template would drift, and the drift would only be
 * visible in a document that has already gone to a printer.
 *
 * Two things this page must get right:
 *
 * 1. **It decides nothing about prices.** The payload arrives already resolved
 *    for the audience recorded when the export was requested. This page has no
 *    idea who it is rendering for and cannot ask for more than it was given.
 * 2. **It says when it is finished.** The worker waits for
 *    `data-dk-print-ready="true"` rather than a fixed delay, so a slow
 *    catalogue is not silently truncated halfway down page three.
 */

import { use, useEffect, useState } from 'react';

import { CatalogueRenderer } from '@/app/(protected)/dealer-kit/components/CatalogueRenderer';
import { PAPER_SIZES_MM, type PageDoc, type ResolvedTile } from '@/lib/dealer-kit/types';

interface PrintPayload {
  pageName: string;
  version: number;
  audience: string;
  doc: PageDoc;
  collections: Record<string, ResolvedTile[]>;
}

function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  return env ? env.replace(/\/$/, '') : '';
}

export default function CataloguePrintPage({
  params,
  searchParams,
}: {
  params: Promise<{ downloadId: string }>;
  searchParams: Promise<{ token?: string }>;
}) {
  const { downloadId } = use(params);
  const { token } = use(searchParams);

  const [payload, setPayload] = useState<PrintPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [imagesSettled, setImagesSettled] = useState(false);

  useEffect(() => {
    let live = true;
    const url = `${apiBase()}/api/v1/public/print/${encodeURIComponent(downloadId)}?token=${encodeURIComponent(token ?? '')}`;

    fetch(url, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Render payload unavailable (${response.status})`);
        return (await response.json()) as PrintPayload;
      })
      .then((body) => {
        if (live) setPayload(body);
      })
      .catch((error: unknown) => {
        if (live) setFailed(error instanceof Error ? error.message : 'Could not load');
      });

    return () => {
      live = false;
    };
  }, [downloadId, token]);

  // Wait for images before declaring the page ready. A half-loaded photo prints
  // as a blank box, and the worker cannot tell the difference.
  useEffect(() => {
    if (!payload) return;

    let cancelled = false;
    const images = Array.from(document.images);
    const pending = images.filter((image) => !image.complete);

    if (pending.length === 0) {
      setImagesSettled(true);
      return;
    }

    let remaining = pending.length;
    const settle = () => {
      remaining -= 1;
      if (remaining <= 0 && !cancelled) setImagesSettled(true);
    };

    pending.forEach((image) => {
      image.addEventListener('load', settle, { once: true });
      // A broken image must not hold the render open forever.
      image.addEventListener('error', settle, { once: true });
    });

    return () => {
      cancelled = true;
    };
  }, [payload]);

  const profile = payload?.doc?.printProfile;
  const paper = PAPER_SIZES_MM[profile?.pageSize ?? 'A4'];
  const landscape = profile?.orientation === 'landscape';
  const widthMm = landscape ? paper.height : paper.width;
  const margins = profile?.margins ?? { top: 15, right: 15, bottom: 15, left: 15 };

  if (failed) {
    // Rendered rather than thrown so the worker's screenshot of a failure is
    // readable, but never marked ready - the download fails on timeout.
    return <main data-dk-print-failed>{failed}</main>;
  }

  return (
    <main
      // The single flag the worker waits on.
      data-dk-print-ready={payload && imagesSettled ? 'true' : 'false'}
      style={{
        width: `${widthMm}mm`,
        paddingTop: `${margins.top}mm`,
        paddingRight: `${margins.right}mm`,
        paddingBottom: `${margins.bottom}mm`,
        paddingLeft: `${margins.left}mm`,
        background: '#ffffff',
      }}
    >
      {/* Chromium's own margins are set to zero by the worker, because the
          document's margins are already applied above. Two sets would shrink
          every page by a margin nobody chose. */}
      <style
        dangerouslySetInnerHTML={{
          __html: `@page { size: ${widthMm}mm auto; margin: 0; }
            html, body { margin: 0; padding: 0; background: #fff; }
            [data-dk-section-id] { break-inside: avoid; }`,
        }}
      />

      {payload && (
        <CatalogueRenderer
          name={payload.pageName}
          sections={payload.doc?.sections ?? []}
          resolvedCollections={payload.collections}
        />
      )}
    </main>
  );
}
