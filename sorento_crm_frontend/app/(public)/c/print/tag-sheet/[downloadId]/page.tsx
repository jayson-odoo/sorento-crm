'use client';

/**
 * Tag sheet print page: what headless Chromium renders to PDF.
 *
 * Follows the same pattern as the catalogue print page:
 * 1. Fetches the pre-resolved payload (tag sheet doc + resolved product/price data).
 * 2. Renders each sheet as an A4-sized div with absolutely positioned tags.
 * 3. Sets data-dk-print-ready="true" when rendering is complete.
 *
 * Three things this page must get right:
 * 1. It decides nothing about prices. The payload arrives already resolved.
 * 2. It says when it is finished (data-dk-print-ready).
 * 3. It is theme-independent: white background, explicit colours, no CSS variables.
 */

import { use, useEffect, useState } from 'react';

import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import { ensureFontsLoaded, type TagFont } from '@/lib/dealer-kit/fonts';
import TagSheetRenderer, {
  type ResolvedLineData,
} from './components/TagSheetRenderer';

interface TagSheetPrintPayload {
  doc: TagSheetDoc;
  resolvedData: Record<string, ResolvedLineData>;
  /** assetId -> signed URL, for every library asset the document names. */
  assets: Record<string, string>;
  /** attachmentId -> signed URL, for the bound products' own photos. */
  images: Record<string, string>;
  /** Brand fonts, loaded before this page reports itself ready. */
  fonts: TagFont[];
  requestDocNumber: string;
  version: number;
}

function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  return env ? env.replace(/\/$/, '') : '';
}

/**
 * Tag sheets are always A4 portrait. No CSS page size declaration: the worker
 * calls page.pdf(format="A4") and Chromium sizes the page box accordingly.
 * Margins are zero: the document's own layout handles positioning.
 */
const PAGE_CSS = `
@page { margin: 0; }
html, body { margin: 0; padding: 0; background: #fff; }
.sheet { break-inside: avoid; }
`;

export default function TagSheetPrintPage({
  params,
  searchParams,
}: {
  params: Promise<{ downloadId: string }>;
  searchParams: Promise<{ token?: string; sheet?: string | string[] }>;
}) {
  const { downloadId } = use(params);
  const resolvedSearch = use(searchParams);
  const token = resolvedSearch.token;

  const [payload, setPayload] = useState<TagSheetPrintPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let live = true;

    // Build the URL with token and optional sheet filters.
    const urlParams = new URLSearchParams();
    urlParams.set('token', token ?? '');

    // Sheet filter comes from searchParams.
    const sheets = resolvedSearch.sheet;
    if (sheets) {
      const sheetArray = Array.isArray(sheets) ? sheets : [sheets];
      for (const s of sheetArray) {
        urlParams.append('sheet', s);
      }
    }

    const url = `${apiBase()}/api/v1/public/print/tag-sheet/${encodeURIComponent(downloadId)}?${urlParams.toString()}`;

    fetch(url, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`Render payload unavailable (${response.status})`);
        return (await response.json()) as TagSheetPrintPayload;
      })
      .then(async (body) => {
        // Fonts BEFORE the ready flag. Chromium prints whatever is loaded at
        // that moment, and a brand face that arrives afterwards prints as the
        // fallback typeface with nothing on screen to say so.
        await ensureFontsLoaded(body.fonts ?? []);
        if (live) setPayload(body);
      })
      .catch((error: unknown) => {
        if (live)
          setFailed(
            error instanceof Error ? error.message : 'Could not load',
          );
      });

    return () => {
      live = false;
    };
  }, [downloadId, token, resolvedSearch.sheet]);

  if (failed) {
    return <main data-dk-print-failed>{failed}</main>;
  }

  return (
    <main
      data-dk-print-ready={payload ? 'true' : 'false'}
      style={{
        width: '100%',
        background: '#ffffff',
      }}
    >
      <style dangerouslySetInnerHTML={{ __html: PAGE_CSS }} />

      {payload && (
        <TagSheetRenderer
          doc={payload.doc}
          resolvedData={payload.resolvedData}
          assets={payload.assets}
          images={payload.images}
        />
      )}
    </main>
  );
}
