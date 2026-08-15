/**
 * What the product looks like, on the row being decided (AC-7).
 *
 * > "as IT I do not know what a product looks like"
 *
 * Two facts drive this component and they arrive separately: the run-wide map says whether
 * the icon is lit, and the per-product fetch (made on the open, in here) brings the picture.
 * The states pinned below are the ones the buyer can actually land on: still loading, a
 * chosen photo, a photo nobody nominated (which keeps the way back to the picker on screen),
 * no photo at all, and a photo we could not load.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const useProductPhoto = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useProductPhoto: (...a: unknown[]) => useProductPhoto(...a),
}));

import { ProductPhotoPopover } from './ProductPhotoPopover';

function photo(data: unknown, extra: Record<string, unknown> = {}) {
  useProductPhoto.mockReturnValue({ data, isLoading: false, isError: false, ...extra });
}

async function open() {
  fireEvent.click(screen.getByRole('button', { name: /product photo/i }));
  await waitFor(() => expect(screen.getAllByText('SRTWCY8840').length).toBeGreaterThan(0));
}

describe('ProductPhotoPopover', () => {
  beforeEach(() => {
    useProductPhoto.mockReset();
    photo(undefined, { isLoading: true });
  });

  it("asks for the run's photo map only when a row is actually opened", async () => {
    const onOpen = vi.fn();
    render(<ProductPhotoPopover sku="SRTWCY8840" onOpen={onOpen} />);

    expect(onOpen).not.toHaveBeenCalled();

    await open();
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('costs nothing until the popover opens', () => {
    render(<ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" />);

    // The body holds the query, and the body only mounts on open: a plan of thousands of
    // rows must not hold a subscription each for panels nobody opened.
    expect(useProductPhoto).not.toHaveBeenCalled();
  });

  it('shows a placeholder while the photo is still in flight', async () => {
    render(<ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" status="ready" />);
    await open();

    expect(screen.getByTestId('product-photo-skeleton')).toBeInTheDocument();
    // Nothing is claimed about the product until the answer lands.
    expect(screen.queryByText(/no primary photo yet/i)).not.toBeInTheDocument();
  });

  it('shows the photo with the product it belongs to', async () => {
    photo({ url: 'https://cdn.test.invalid/products/a.jpg?Signature=stub', is_primary: true });
    render(
      <ProductPhotoPopover
        runId="run-1"
        productId="p1"
        sku="SRTWCY8840"
        productName="Wall hung water closet"
        hasPhoto
        status="ready"
      />,
    );
    await open();

    const img = screen.getByRole('img', { name: 'Wall hung water closet' });
    expect(img).toHaveAttribute('src', 'https://cdn.test.invalid/products/a.jpg?Signature=stub');
    expect(screen.getByText('Wall hung water closet')).toBeInTheDocument();
    // Nobody has to be sent anywhere: this IS the chosen photo.
    expect(screen.queryByRole('link', { name: /choose the primary photo/i })).not.toBeInTheDocument();
  });

  it('offers the way to Brochure images when the photo is only a fallback', async () => {
    photo({ url: 'https://cdn.test.invalid/products/a.jpg', is_primary: false });
    render(
      <ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" hasPhoto status="ready" />,
    );
    await open();

    expect(screen.getByRole('img', { name: 'SRTWCY8840' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /choose the primary photo/i })).toHaveAttribute(
      'href',
      '/dealer-kit/brochure-images',
    );
  });

  it('says there is no photo yet and where to choose one', async () => {
    photo({ url: null, is_primary: false });
    render(<ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" status="ready" />);
    await open();

    expect(screen.getByText('No primary photo yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /brochure images/i })).toHaveAttribute(
      'href',
      '/dealer-kit/brochure-images',
    );
  });

  it('keeps the answer it already has when a background refetch fails', async () => {
    photo({ url: null, is_primary: false });
    const { rerender } = render(
      <ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" status="ready" />,
    );
    await open();
    expect(screen.getByText('No primary photo yet')).toBeInTheDocument();

    // react-query holds the last good answer through a failed refetch. Reading the error
    // first turned a true statement about the product ("nobody has given it a photo") into
    // a false one ("we could not load its photo"), on a network blip the buyer never saw.
    photo({ url: null, is_primary: false }, { isError: true });
    rerender(
      <ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" status="ready" />,
    );

    expect(screen.getByText('No primary photo yet')).toBeInTheDocument();
    expect(screen.queryByText(/failed to load the photo/i)).not.toBeInTheDocument();
  });

  it('says the photo failed rather than pretending the product has none', async () => {
    photo(undefined, { isError: true });
    render(
      <ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" hasPhoto status="ready" />,
    );
    await open();

    expect(screen.getByText(/failed to load the photo/i)).toBeInTheDocument();
    expect(screen.queryByText(/no primary photo yet/i)).not.toBeInTheDocument();
  });

  it('says so when the signed url has expired under the browser', async () => {
    photo({ url: 'https://cdn.test.invalid/products/a.jpg?Signature=expired', is_primary: true });
    render(
      <ProductPhotoPopover runId="run-1" productId="p1" sku="SRTWCY8840" hasPhoto status="ready" />,
    );
    await open();

    // A signed URL that expired between the fetch and the render comes back 403, and the
    // browser reports it only through the image's own error event. Without this the buyer
    // stares at a broken-image glyph and no explanation.
    fireEvent.error(screen.getByRole('img', { name: 'SRTWCY8840' }));

    expect(screen.getByText(/failed to load the photo/i)).toBeInTheDocument();
  });

  it('dims the icon only once we KNOW the product has no photo', () => {
    const { rerender } = render(<ProductPhotoPopover sku="SRTWCY8840" status="idle" />);
    expect(screen.getByRole('button', { name: /product photo/i }).className).not.toContain(
      'text-muted-foreground/50',
    );

    rerender(<ProductPhotoPopover sku="SRTWCY8840" status="ready" />);
    expect(screen.getByRole('button', { name: /product photo/i }).className).toContain(
      'text-muted-foreground/50',
    );

    rerender(<ProductPhotoPopover sku="SRTWCY8840" status="ready" hasPhoto />);
    expect(screen.getByRole('button', { name: /product photo/i }).className).not.toContain(
      'text-muted-foreground/50',
    );
  });
});
