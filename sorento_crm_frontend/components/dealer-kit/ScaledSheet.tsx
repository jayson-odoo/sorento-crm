'use client';

/**
 * One tag sheet, drawn at a chosen scale, with its artwork and brand fonts.
 *
 * The card and the lightbox both need exactly this and nothing else, so the
 * scaling wrapper lives here rather than twice. `TagSheetRenderer` draws a
 * sheet at its natural millimetre size; a CSS transform does not change the
 * layout box, so the scaled sheet is wrapped in a box of the SCALED size or a
 * shrunk sheet leaves a page of dead space under it.
 */

import { useEffect, useMemo } from 'react';

import TagSheetRenderer from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import { ensureFontsLoaded, ensureSeedFontsLoaded } from '@/lib/dealer-kit/fonts';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import DesignPinLayer, { type DesignReview } from './DesignPinLayer';

/**
 * CSS `mm` resolves to 96px/inch by spec regardless of the screen's actual DPI
 * - the same constant the print route relies on for physical accuracy - so a
 * fit scale is arithmetic off a measured container rather than a hidden render
 * pass.
 */
export const PX_PER_MM = 96 / 25.4;

/** The sheet's natural on-screen size in CSS pixels, at scale 1. */
export function sheetPixelSize(doc: TagSheetDoc | null): {
  width: number;
  height: number;
} {
  return {
    width: (doc?.imposition?.page_width_mm ?? 0) * PX_PER_MM,
    height: (doc?.imposition?.page_height_mm ?? 0) * PX_PER_MM,
  };
}

interface ScaledSheetProps {
  payload: TagSheetDesignPayload;
  /** Which sheet of the document to draw. */
  sheetIndex: number;
  scale: number;
  /** Pinned change requests over the sheet (r9 S2). Absent = none, no placing. */
  review?: DesignReview;
}

export default function ScaledSheet({
  payload,
  sheetIndex,
  scale,
  review,
}: ScaledSheetProps) {
  const { doc, assets, images, fonts, resolvedData } = payload;

  // Brand faces before the tags draw. The DOM renderer re-lays text out by
  // itself once a face arrives (unlike Konva, which measures once), so this
  // needs no readiness flag - only that something asks for the fonts at all.
  // The seeded templates' stand-ins come from a stylesheet rather than the
  // library, so they are loaded alongside rather than instead.
  useEffect(() => {
    void ensureSeedFontsLoaded();
  }, []);
  useEffect(() => {
    if (fonts.length === 0) return;
    void ensureFontsLoaded(fonts);
  }, [fonts]);

  // One sheet at a time: the pager decides which, and the print document's own
  // "every sheet stacked" layout is for the PDF, not for a reader.
  const singleSheetDoc = useMemo(() => {
    if (!doc || !doc.sheets[sheetIndex]) return null;
    return { ...doc, sheets: [doc.sheets[sheetIndex]] } as TagSheetDoc;
  }, [doc, sheetIndex]);

  if (!singleSheetDoc) return null;

  // A doc that reached here with sheets but no `imposition` (r9 review-round
  // leftover: the backend's page-less-request fallback used to omit it) must
  // still draw SOMETHING rather than throw - blank is fine, a crash is not.
  if (!singleSheetDoc.imposition) return null;

  const natural = sheetPixelSize(doc);

  return (
    <div
      style={{
        width: `${natural.width * scale}px`,
        height: `${natural.height * scale}px`,
        // A tag bled past the sheet edge must not paint over the page.
        overflow: 'hidden',
        // The pin layer is absolute against this box.
        position: 'relative',
        // The sheet is white paper whatever the app's theme is.
        backgroundColor: '#ffffff',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.16)',
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          width: `${doc?.imposition?.page_width_mm ?? 0}mm`,
          height: `${doc?.imposition?.page_height_mm ?? 0}mm`,
        }}
      >
        <TagSheetRenderer
          doc={singleSheetDoc}
          resolvedData={resolvedData}
          assets={assets}
          images={images}
        />
      </div>
      {review && (
        <DesignPinLayer
          doc={doc}
          sheetIndex={sheetIndex}
          scale={scale}
          {...review}
        />
      )}
    </div>
  );
}
