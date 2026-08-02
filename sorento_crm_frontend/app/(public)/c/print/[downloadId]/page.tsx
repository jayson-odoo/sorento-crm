'use client';

/**
 * The page headless Chromium prints.
 *
 * It renders the SAME `CatalogueRenderer` the editor and the public catalogue
 * use, which is what makes "the PDF matches the screen" structural rather than
 * a promise. A separate print template would drift, and the drift would only be
 * visible in a document that has already gone to a printer.
 *
 * Three things this page must get right:
 *
 * 1. **It decides nothing about prices.** The payload arrives already resolved
 *    for the audience recorded when the export was requested. This page has no
 *    idea who it is rendering for and cannot ask for more than it was given.
 * 2. **It says when it is finished.** The worker waits for
 *    `data-dk-print-ready="true"` rather than a fixed delay, so a slow
 *    catalogue is not silently truncated halfway down page three.
 * 3. **It decides nothing about the paper either.** See `PAGE_CSS`.
 */

import { use, useEffect, useState } from 'react';

import { CatalogueRenderer } from '@/app/(protected)/dealer-kit/components/CatalogueRenderer';
import { paperBreakpoint } from '@/lib/dealer-kit/paginate';
import { DEFAULT_PRINT_PROFILE, type PageDoc, type ResolvedTile, type TileField } from '@/lib/dealer-kit/types';

interface PrintPayload {
  pageName: string;
  version: number;
  audience: string;
  doc: PageDoc;
  collections: Record<string, ResolvedTile[]>;
  /**
   * tileTemplateId -> the fields that design binds, sent with the payload so
   * this page never fetches a design of its own. It has to be PASSED ON: the
   * renderer falls back to a default field list when it gets nothing, and a
   * default is by definition not the design the brochure on screen is using.
   */
  tileTemplates?: Record<string, TileField[]>;
  /**
   * assetId -> signed URL for the section backgrounds. Sent with the payload for
   * the same reason as the templates, and with one extra consequence: these
   * become CSS backgrounds, which are not `<img>` elements and therefore are not
   * covered by `document.images`. See the readiness effect below.
   */
  assets?: Record<string, string>;
}

function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  return env ? env.replace(/\/$/, '') : '';
}

/**
 * There is ONE owner of the page geometry, and it is not this file.
 *
 * The worker calls `page.pdf(format=..., landscape=...)` with the document's
 * print profile, and Chromium ignores a CSS `@page size` unless it is asked for
 * `prefer_css_page_size`. This stylesheet used to declare `size: <W>mm auto` as
 * well: measured on a real A4 export, the MediaBox came back 210 x 297mm, so
 * the declaration decided nothing and only looked like it did.
 *
 * Two declarations of one fact are the defect even while they agree, and these
 * two would have stopped agreeing the moment anyone turned
 * `prefer_css_page_size` on. The CSS width had already swapped itself for
 * landscape, and `landscape=True` rotates the paper again, so the rotation
 * would have been applied twice: a 297mm-wide document on a 210mm-wide page.
 *
 * Hence: the CSS says nothing about size, and <main> is `width: 100%` - the
 * page box, which is the paper the worker asked for, in either orientation,
 * with no arithmetic here that could disagree with it. `margin: 0` stays,
 * because the document's own margins are applied as padding on <main> and a
 * second set would shrink every page by a margin nobody chose.
 */
const PAGE_CSS = `
@page { margin: 0; }
html, body { margin: 0; padding: 0; background: #fff; }
/*
  Taking <body> back out of the app shell's flex row is NOT here. A printed
  document is a block that flows onto as many pages as it needs rather than a
  flex item sized by a sidebar layout, but so is a public catalogue, so the
  rule belongs to the (public) layout that both routes share. It was stated
  here alone for a while, which is why the catalogue rendered 274px wide while
  the PDF came out fine.
*/
/*
  Where a fold is allowed to land.

  A section is atomic, which is what Print Preview's paginator assumes when it
  draws a break line. But break-inside is a request, not a law: a
  section taller than one page cannot be kept whole, and Chromium then breaks it
  wherever the fold happens to fall. Measured on a 40-product A4 export, that
  was through the middle of a tile row - the product names printed on page one
  and their prices on page two, 47.6pt of a 57pt tile on the first sheet.

  So the second rule states the guarantee we can actually keep, at the grain the
  reader recognises: whatever else a fold does, it does not cut a product in
  half. The paginator promises sections do not split; this makes the case it
  cannot promise survivable rather than silently wrong.
*/
[data-dk-section-id] { break-inside: avoid; }
[data-dk-tile] { break-inside: avoid; }
`;

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
  //
  // Section BACKGROUNDS have to be waited for explicitly. They are CSS
  // `background-image`, not `<img>`, so `document.images` does not see them at
  // all - and a section background is the largest thing on the page, so the one
  // asset most likely to still be in flight is the one nothing was watching.
  // Loading each URL through an Image object puts it in the same HTTP cache the
  // CSS reads, so this waits for the real fetch rather than a copy of it.
  useEffect(() => {
    if (!payload) return;

    let cancelled = false;
    const pending: HTMLImageElement[] = Array.from(document.images).filter(
      (image) => !image.complete,
    );

    for (const url of Object.values(payload.assets ?? {})) {
      const preload = new Image();
      preload.src = url;
      if (!preload.complete) pending.push(preload);
    }

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

  const profile = payload?.doc?.printProfile ?? DEFAULT_PRINT_PROFILE;
  const margins = profile.margins ?? DEFAULT_PRINT_PROFILE.margins;

  /**
   * The paper IS a breakpoint, and the document is rendered at exactly one.
   *
   * Not a preference: A4 portrait is 210mm, which is 794 CSS pixels, and 794px
   * is a tablet. A3 landscape is 1587px, which is a desktop. So it is read off
   * the print profile the export was requested with, and the renderer then uses
   * that one breakpoint for BOTH the block placements and the tile density.
   *
   * Naming none was the bug. Tile density fell back to desktop while the
   * renderer's media queries went on resolving against the width of the sheet
   * and handed back tablet placements, so one sheet of paper carried half of
   * each layout.
   */
  const breakpoint = paperBreakpoint(profile);

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
        // Fills the page box, whatever paper the worker asked Chromium for.
        // See PAGE_CSS: the paper is not this page's decision to restate.
        width: '100%',
        // The margins are INSIDE that width. Stated here rather than inherited
        // from a global reset, because this document also has to be right when
        // it is rendered by a browser that never loaded the app's stylesheet.
        boxSizing: 'border-box',
        paddingTop: `${margins.top}mm`,
        paddingRight: `${margins.right}mm`,
        paddingBottom: `${margins.bottom}mm`,
        paddingLeft: `${margins.left}mm`,
        background: '#ffffff',
      }}
    >
      <style dangerouslySetInnerHTML={{ __html: PAGE_CSS }} />

      {payload && (
        <CatalogueRenderer
          name={payload.pageName}
          sections={payload.doc?.sections ?? []}
          resolvedCollections={payload.collections}
          tileTemplates={payload.tileTemplates}
          assets={payload.assets}
          breakpoint={breakpoint}
        />
      )}
    </main>
  );
}
