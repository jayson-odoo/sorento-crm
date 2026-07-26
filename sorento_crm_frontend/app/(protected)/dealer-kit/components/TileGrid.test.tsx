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
