'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Image as ImageIcon } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * What the product actually looks like, on the row the buyer is deciding.
 *
 * > "as IT I do not know what a product looks like"
 *
 * A plan row is a code and a name, and a buyer who does not handle the goods cannot tell
 * SRTWCY8840 from SRTWCY8850 from either. The photo is the one already chosen in
 * Dealer Kit -> Brochure images (`product_attachments.is_primary`), so the plan screen and
 * the catalogue can never show a different picture of the same product.
 *
 * The photos are fetched ONCE for the whole run, lazily, the first time any row's icon is
 * opened (`onOpen`) - the same shape as the PO cell's purchase trend. Fetching them per row
 * would sign a URL for every product on a plan the buyer opens two photos of.
 */
export type ProductPhotoStatus = 'idle' | 'loading' | 'ready' | 'error';

export function ProductPhotoPopover({
  sku,
  productName,
  url,
  status = 'idle',
  onOpen,
  label = 'Product photo',
}: {
  sku: string;
  productName?: string | null;
  /** The signed URL for this product's primary photo, or undefined when it has none. */
  url?: string | null;
  /** Where the run's photo map is: not asked for yet, in flight, loaded, or failed. */
  status?: ProductPhotoStatus;
  /** Fired on the first open, so the caller can start the run-wide fetch. */
  onOpen?: () => void;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  // Dimmed only once we KNOW: before the map lands, "no photo" is not yet a fact about this
  // product, and a dimmed icon would tell the buyer something we have not checked.
  const known = status === 'ready';
  const missing = known && !url;

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) onOpen?.();
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          title={label}
          data-testid="product-photo-trigger"
          className={`inline-flex size-5 items-center justify-center rounded-sm transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            missing ? 'text-muted-foreground/50' : 'text-muted-foreground/70'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          <ImageIcon className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        {/* 92vw so the panel still fits a phone, where 336px would run off the screen. */}
        <PopoverContent align="start" collisionPadding={8} className="w-[336px] max-w-[92vw] p-0">
          <div className="border-b px-3 py-2">
            <div className="truncate text-xs font-semibold" title={sku}>
              {sku}
            </div>
            {productName ? (
              <div className="truncate text-2xs text-muted-foreground" title={productName}>
                {productName}
              </div>
            ) : null}
          </div>
          <div className="p-3">
            {status === 'loading' || status === 'idle' ? (
              <Skeleton className="h-40 w-full" data-testid="product-photo-skeleton" />
            ) : status === 'error' ? (
              <p className="text-2xs text-muted-foreground">Failed to load the photo.</p>
            ) : url ? (
              // A plain <img>: the src is a signed, expiring S3/R2 URL, so next/image would
              // need every storage host whitelisted and would re-proxy a link that is
              // already thumbnail-sized and short-lived.
              <img
                src={url}
                alt={sku}
                className="mx-auto max-h-[320px] w-auto max-w-full rounded object-contain"
              />
            ) : (
              <div className="space-y-1">
                <p className="text-xs">No primary photo yet</p>
                <Link
                  href="/dealer-kit/brochure-images"
                  className="text-2xs text-primary hover:underline"
                >
                  Choose one in Dealer Kit -&gt; Brochure images
                </Link>
              </div>
            )}
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default ProductPhotoPopover;
