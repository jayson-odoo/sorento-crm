import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TileGrid } from './TileGrid';
import type { ResolvedTile } from '@/lib/dealer-kit/types';

function tile(overrides: Partial<ResolvedTile> = {}): ResolvedTile {
  return {
    productId: 'p1',
    productCode: 'SK-3040',
    productName: 'Undermount Kitchen Sink',
    price: 'RM 1,290.00',
    offerPrice: null,
    invoicePrice: null,
    imageUrl: null,
    dimensions: '760 x 440 mm',
    badges: ['SIRIM'],
    ...overrides,
  };
}

describe('TileGrid', () => {
  it('renders one tile per member product', () => {
    render(
      <TileGrid
        tiles={[tile(), tile({ productId: 'p2', productCode: 'TP-1180', productName: 'Mixer' })]}
        fields={['name', 'code']}
        columns={2}
      />,
    );

    expect(screen.getByText('Undermount Kitchen Sink')).toBeInTheDocument();
    expect(screen.getByText('Mixer')).toBeInTheDocument();
  });

  it('shows only the fields the tile design binds', () => {
    render(<TileGrid tiles={[tile()]} fields={['name']} columns={1} />);

    expect(screen.getByText('Undermount Kitchen Sink')).toBeInTheDocument();
    // Price is in the payload but not in the design, so it must not render.
    expect(screen.queryByText('RM 1,290.00')).not.toBeInTheDocument();
    expect(screen.queryByText('SK-3040')).not.toBeInTheDocument();
  });

  it('renders no price when the viewer is not allowed one', () => {
    // The server sends null rather than a number it then asks us to hide, so
    // there is nothing in the DOM to reveal (AC-G7).
    render(<TileGrid tiles={[tile({ price: null })]} fields={['name', 'price']} columns={1} />);

    expect(screen.getByText('Undermount Kitchen Sink')).toBeInTheDocument();
    expect(screen.queryByText(/RM/)).not.toBeInTheDocument();
  });

  it('strikes through the LIST price and leads with the offer', () => {
    // The one that must never invert: `price` is the original, higher figure a
    // flyer prints as "LP", `offerPrice` is what the reader actually pays. The
    // line goes through the LIST price. Asserting both numbers appear would
    // pass with the treatment backwards, which is why this asserts WHICH
    // element carries the line.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,290.00', offerPrice: 'RM 599.00' })]}
        fields={['name', 'price', 'offerPrice']}
        columns={1}
      />,
    );

    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;
    const offer = container.querySelector('[data-dk-offer-price]') as HTMLElement;

    expect(list).toHaveTextContent('RM 1,290.00');
    expect(offer).toHaveTextContent('RM 599.00');
    expect(list.className).toContain('line-through');
    expect(offer.className).not.toContain('line-through');
  });

  it('shows the offer on a design written before offers existed', () => {
    // Every design saved so far binds `price` and nothing else. If the offer
    // only appeared once someone re-edited the design, a brochure linked to a
    // promotion would keep printing list prices, which is the defect this
    // slice exists to remove.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,290.00', offerPrice: 'RM 599.00' })]}
        fields={['image', 'name', 'code', 'price']}
        columns={1}
      />,
    );

    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;

    expect(list.className).toContain('line-through');
    expect(container.querySelector('[data-dk-offer-price]')).toHaveTextContent('RM 599.00');
  });

  it('shows the list price plain when no offer applies', () => {
    // A tile with nothing to compare against must not look discounted to
    // itself: no line, and no empty slot where an offer would have gone.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,290.00', offerPrice: null })]}
        fields={['name', 'price', 'offerPrice']}
        columns={1}
      />,
    );

    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;

    expect(list).toHaveTextContent('RM 1,290.00');
    expect(list.className).not.toContain('line-through');
    expect(container.querySelector('[data-dk-offer-price]')).toBeNull();
  });

  it('treats an offer the viewer may not see exactly as no offer', () => {
    // `null` is what a reader outside the promotion's access levels receives -
    // the same payload shape as a product with no promotion at all (AC-G7). It
    // must not render as a struck-through price with a blank beside it.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,290.00', offerPrice: null })]}
        fields={['price']}
        columns={1}
      />,
    );

    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;
    expect(list.className).not.toContain('line-through');
    expect(container.querySelector('[data-dk-offer-price]')).toBeNull();
    expect(container.textContent).not.toContain('RM 599');
  });

  it('prints the offer alone when the design binds only the offer price', () => {
    // A consumer flyer that never quotes LP. Binding the offer on its own is
    // how that is expressed, so there is no struck-through figure to print.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,290.00', offerPrice: 'RM 599.00' })]}
        fields={['offerPrice']}
        columns={1}
      />,
    );

    expect(container.querySelector('[data-dk-offer-price]')).toHaveTextContent('RM 599.00');
    expect(container.querySelector('[data-dk-list-price]')).toBeNull();
  });

  it('falls back to the list price when an offer-only design has no offer', () => {
    // ADR 0008 rule 5: no applicable offer is the list price with no offer
    // styling. Never a blank space where a figure should be.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,290.00', offerPrice: null })]}
        fields={['offerPrice']}
        columns={1}
      />,
    );

    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;
    expect(list).toHaveTextContent('RM 1,290.00');
    expect(list.className).not.toContain('line-through');
  });

  it('wraps a long money string rather than clipping it', () => {
    // At 375px two figures do not fit on one line, and a clipped price shows a
    // number that is not the price. Wrapping is the only safe failure.
    const { container } = render(
      <TileGrid
        tiles={[tile({ price: 'RM 1,234,567.00', offerPrice: 'RM 999,999.00' })]}
        fields={['price', 'offerPrice']}
        columns={1}
      />,
    );

    const row = container.querySelector('[data-dk-price-row]') as HTMLElement;
    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;
    const offer = container.querySelector('[data-dk-offer-price]') as HTMLElement;

    expect(row.className).toContain('flex-wrap');
    expect(list.className).not.toContain('truncate');
    expect(offer.className).not.toContain('truncate');
  });

  it('renders badges as text, never as a link to the certificate', () => {
    render(<TileGrid tiles={[tile()]} fields={['badges']} columns={1} />);

    expect(screen.getByText('SIRIM')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('explains an empty result rather than rendering nothing', () => {
    render(<TileGrid tiles={[]} fields={['name']} columns={3} />);

    expect(screen.getByText(/no products to show/i)).toBeInTheDocument();
  });

  it('applies the requested column count', () => {
    const { container } = render(<TileGrid tiles={[tile()]} fields={['name']} columns={4} />);

    const grid = container.querySelector('[data-dk-tile-grid]') as HTMLElement;
    expect(grid.style.gridTemplateColumns).toBe('repeat(4, minmax(0, 1fr))');
  });

  it('never emits a zero-column grid', () => {
    const { container } = render(<TileGrid tiles={[tile()]} fields={['name']} columns={0} />);

    const grid = container.querySelector('[data-dk-tile-grid]') as HTMLElement;
    expect(grid.style.gridTemplateColumns).toBe('repeat(1, minmax(0, 1fr))');
  });
});
