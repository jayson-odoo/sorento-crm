'use client';

import * as React from 'react';
import Link from 'next/link';
import { ImageOff } from 'lucide-react';
import type { QuotationLine } from '../../_shared/types/project.types';

/**
 * Where somebody goes to say which photograph is the product.
 *
 * The product's own Attachments tab, because that is where its files already are and where the
 * chosen one is already marked. The EDIT route, because choosing is a write on master data and
 * the read-only detail page only shows which one was picked. The choice is
 * `product_attachments.is_primary` - the same flag the brochure reads - so recording it there
 * answers it for every consumer at once, rather than pinning a picture to this one quotation.
 */
export function productPhotoHref(productId: string): string {
  return `/master-data-management/products/${productId}/edit?tab=attachments`;
}

/**
 * The line's product photograph, or the reason there isn't one.
 *
 * On day one there usually isn't: 30 of the 535 products with candidate photographs carry a
 * choice, so this cell is far more often an empty state than a picture, and the empty state is
 * the part that has to earn its place. It names WHAT is missing and links to WHERE it is fixed -
 * "No photo chosen" and "No photo on file" are different problems (a click versus a photo shoot)
 * and they get different words.
 *
 * The customer-facing artifacts do the opposite: a line with no chosen photograph prints an
 * EMPTY cell in the PDF and the workbook, and a scope with none at all prints no picture column.
 * Our internal to-do list belongs on the screen where somebody can act on it, not on the page the
 * customer reads.
 */
export function QuotationLinePhoto({
  line,
  onPreview,
}: {
  line: QuotationLine | null;
  /**
   * Open the viewer on THIS line. Omitted where there is nothing to open into (the print
   * preview, a read-only render), and the cell then stays a plain picture rather than
   * advertising an action that does nothing.
   */
  onPreview?: () => void;
}) {
  // A row staged in this edit session has no stored line yet, so nothing has been resolved for
  // it. Rendering "no photo chosen" here would be a claim we cannot support: we do not know.
  // Same rule the row's other server-decided facts (Off-catalog, Below floor, Non-standard)
  // already follow.
  if (!line) return null;

  const image = line.product_image;
  if (!image || image.state === 'off_catalog') {
    // No product, so there is nothing a flag could point at. Not "nobody has chosen yet".
    return (
      <span className="block text-sm text-muted-foreground" aria-hidden>
        -
      </span>
    );
  }

  if (image.state === 'chosen' && image.url) {
    // A plain <img>, not next/image: the src is a signed CDN URL, so there is nothing for the
    // image optimiser to re-sign. It IS cacheable - the backend reuses the same signature for
    // a window precisely so the browser can keep the bytes.
    const picture = (
      <img
        src={image.url}
        alt={line.product_code ? `${line.product_code} product photo` : 'Product photo'}
        title={image.filename ?? undefined}
        className="size-12 rounded border border-border bg-white object-contain"
        loading="lazy"
      />
    );

    if (!onPreview) return picture;

    return (
      <button
        type="button"
        onClick={onPreview}
        // A cell in an editable table: stop the click reaching the row, which would otherwise
        // put the line into edit mode behind the viewer.
        onMouseDown={(event) => event.stopPropagation()}
        className="rounded focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        title={image.filename ? `Preview ${image.filename}` : 'Preview photo'}
        aria-label={
          line.product_code ? `Preview ${line.product_code} photo` : 'Preview product photo'
        }
      >
        {picture}
      </button>
    );
  }

  const chosenButUnreachable = image.state === 'chosen';
  const label = chosenButUnreachable
    ? 'Photo unavailable'
    : image.state === 'not_chosen'
      ? 'No photo chosen'
      : 'No photo on file';

  const body = (
    <span className="flex flex-col items-start gap-0.5 text-start">
      <ImageOff className="size-4 text-muted-foreground" aria-hidden />
      <span className="text-[11px] leading-tight font-normal">{label}</span>
      {image.state === 'not_chosen' && image.candidate_count > 0 && (
        <span className="text-[11px] leading-tight font-normal text-muted-foreground">
          {image.candidate_count === 1 ? '1 photo' : `${image.candidate_count} photos`}
        </span>
      )}
    </span>
  );

  // Unreachable storage is not something the salesperson can fix by choosing again, so it is
  // stated and left alone rather than dressed up as an action.
  if (!line.product_id || chosenButUnreachable) {
    return <span className="block text-muted-foreground">{body}</span>;
  }

  return (
    <Link
      href={productPhotoHref(line.product_id)}
      className="block text-muted-foreground hover:text-primary hover:underline"
    >
      {body}
    </Link>
  );
}
