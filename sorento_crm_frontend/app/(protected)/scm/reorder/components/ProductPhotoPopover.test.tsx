/**
 * What the product looks like, on the row being decided (AC-7).
 *
 * > "as IT I do not know what a product looks like"
 *
 * The four states this popover can be in are the whole component: the map has not been
 * asked for yet, it is in flight, it landed with a photo, it landed WITHOUT one (which is
 * a fact worth saying, plus where to fix it), or it failed.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ProductPhotoPopover } from './ProductPhotoPopover';

async function open() {
  fireEvent.click(screen.getByRole('button', { name: /product photo/i }));
  await waitFor(() => expect(screen.getAllByText('SRTWCY8840').length).toBeGreaterThan(0));
}

describe('ProductPhotoPopover', () => {
  it("asks for the run's photos only when a row is actually opened", async () => {
    const onOpen = vi.fn();
    render(<ProductPhotoPopover sku="SRTWCY8840" onOpen={onOpen} />);

    expect(onOpen).not.toHaveBeenCalled();

    await open();
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('shows a placeholder while the photos are still in flight', async () => {
    render(<ProductPhotoPopover sku="SRTWCY8840" status="loading" />);
    await open();

    expect(screen.getByTestId('product-photo-skeleton')).toBeInTheDocument();
    // Nothing is claimed about the product until the answer lands.
    expect(screen.queryByText(/no primary photo yet/i)).not.toBeInTheDocument();
  });

  it('shows the photo with the product it belongs to', async () => {
    render(
      <ProductPhotoPopover
        sku="SRTWCY8840"
        productName="Wall hung water closet"
        url="https://cdn.test.invalid/products/a.jpg?Signature=stub"
        status="ready"
      />,
    );
    await open();

    const img = screen.getByRole('img', { name: 'SRTWCY8840' });
    expect(img).toHaveAttribute('src', 'https://cdn.test.invalid/products/a.jpg?Signature=stub');
    expect(screen.getByText('Wall hung water closet')).toBeInTheDocument();
  });

  it('says there is no photo yet and where to choose one', async () => {
    render(<ProductPhotoPopover sku="SRTWCY8840" status="ready" />);
    await open();

    expect(screen.getByText('No primary photo yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /brochure images/i })).toHaveAttribute(
      'href',
      '/dealer-kit/brochure-images',
    );
  });

  it('says the photos failed rather than pretending the product has none', async () => {
    render(<ProductPhotoPopover sku="SRTWCY8840" status="error" />);
    await open();

    expect(screen.getByText(/failed to load the photo/i)).toBeInTheDocument();
    expect(screen.queryByText(/no primary photo yet/i)).not.toBeInTheDocument();
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

    rerender(<ProductPhotoPopover sku="SRTWCY8840" status="ready" url="https://x/y.jpg" />);
    expect(screen.getByRole('button', { name: /product photo/i }).className).not.toContain(
      'text-muted-foreground/50',
    );
  });
});
