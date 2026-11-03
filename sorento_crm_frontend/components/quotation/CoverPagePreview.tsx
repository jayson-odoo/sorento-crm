'use client';

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import type { CoverPageData } from '@/lib/quotation-cover';
import { CoverPageCard } from './CoverPageCard';

/** A4 at 96 dpi, the page the card is drawn on before it is scaled to the available width. */
const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

/**
 * Page 1 of the quotation, shown on an A4-shaped sheet scaled to fit its box. A CSS transform does
 * not change the layout box, so the scaled page sits in a box of the scaled size (the pattern of
 * `components/dealer-kit/ScaledSheet.tsx`).
 */
export function CoverPagePreview({
  cover,
  isLoading = false,
  noun,
}: {
  cover: CoverPageData | undefined;
  isLoading?: boolean;
  noun?: string;
}) {
  const box = React.useRef<HTMLDivElement>(null);
  const [scale, setScale] = React.useState(1);

  React.useEffect(() => {
    const node = box.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const fit = () => {
      const width = node.clientWidth;
      if (width > 0) setScale(Math.min(1, width / PAGE_WIDTH));
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={box} className="w-full min-w-0">
      {cover ? (
        // The page grows with its content (a long closing must stay visible); `zoom` scales the
        // layout box too, so there is no fixed-height wrapper to clip it.
        <div
          className="bg-white p-[57px] text-black shadow-sm ring-1 ring-border"
          style={{ width: PAGE_WIDTH, minHeight: PAGE_HEIGHT, zoom: scale }}
        >
          <CoverPageCard cover={cover} testId="cover-page-preview" noun={noun} wide />
        </div>
      ) : (
        isLoading && <Skeleton className="h-64 w-full" />
      )}
    </div>
  );
}
