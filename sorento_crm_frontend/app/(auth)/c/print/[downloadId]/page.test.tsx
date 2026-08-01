import { Suspense } from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CataloguePrintPage from './page';
import { DEFAULT_PRINT_PROFILE, type ResolvedTile } from '@/lib/dealer-kit/types';

/**
 * The page headless Chromium prints.
 *
 * The user's requirement is one sentence: the PDF and the brochure on screen
 * must look the same. They share `CatalogueRenderer`, so the only way they can
 * diverge is if one of them hands it different inputs - which is exactly what
 * these cover.
 */

const TILE: ResolvedTile = {
  productId: 'p1',
  productCode: 'SK-3040',
  productName: 'Undermount Kitchen Sink',
  price: 'RM 1,290.00',
  offerPrice: 'RM 599.00',
  invoicePrice: null,
  imageUrl: null,
  dimensions: '760 x 440 mm',
  badges: [],
};

function payload(tileFields: string[]) {
  return {
    pageName: 'ZZT flyer',
    version: 1,
    audience: 'end_user',
    doc: {
      sections: [
        {
          id: 's1',
          name: 'Products',
          style: {},
          printMode: 'include',
          layouts: {
            desktop: { blocks: {}, isDerived: true },
            tablet: { blocks: {}, isDerived: true },
            mobile: { blocks: {}, isDerived: true },
          },
          blocks: [
            {
              id: 'b1',
              type: 'collection',
              props: {
                kind: 'collection',
                collectionId: 'c1',
                tileTemplateId: 't1',
                columns: { desktop: 4, tablet: 2, mobile: 1 },
              },
            },
          ],
        },
      ],
      printProfile: DEFAULT_PRINT_PROFILE,
    },
    collections: { c1: [TILE] },
    tileTemplates: { t1: tileFields },
  };
}

/**
 * The route reads its params through `use()`, so the render has to be flushed
 * inside `act` - otherwise React never gets past the Suspense fallback and
 * every assertion below reads an empty page.
 */
async function renderPrintPage() {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <Suspense fallback={<p>Loading</p>}>
        <CataloguePrintPage
          params={Promise.resolve({ downloadId: 'dl-1' })}
          searchParams={Promise.resolve({ token: 'tok' })}
        />
      </Suspense>,
    );
  });
  return result;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the printed catalogue', () => {
  it('prints the offer with the list price struck through, exactly as the screen does', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload(['name', 'price']) }),
    );

    const { container } = await renderPrintPage();

    expect(await screen.findByText('RM 599.00')).toBeInTheDocument();
    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;
    expect(list).toHaveTextContent('RM 1,290.00');
    expect(list.className).toContain('line-through');
  });

  it('prints the tile design the brochure uses, not a default of its own', async () => {
    // The payload carries the design's field list. Ignoring it would print a
    // different tile from the one on screen - the same product code appearing
    // on paper and not online is how "the PDF looks different" starts.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload(['name', 'offerPrice']) }),
    );

    const { container } = await renderPrintPage();

    expect(await screen.findByText('Undermount Kitchen Sink')).toBeInTheDocument();
    // The design binds the offer alone, so no list price prints beside it.
    expect(container.querySelector('[data-dk-offer-price]')).toHaveTextContent('RM 599.00');
    expect(container.querySelector('[data-dk-list-price]')).toBeNull();
    expect(screen.queryByText('SK-3040')).not.toBeInTheDocument();
  });
});
