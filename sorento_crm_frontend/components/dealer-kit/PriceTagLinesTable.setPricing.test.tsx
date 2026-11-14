/**
 * PRICETAG-MULTI-ADD round 5, F1-7: a set line shows the LP/SP toggle, its list price and its
 * selling price (read-only), and a "-" Promotion cell. Written test-FIRST: today
 * `showPricing = !isSet && !!product_id` hides all of it for a set.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/common/SearchableMultiSelect');
vi.mock('@/components/dealer-kit/DesignViewer', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/dealer-kit/DesignLightbox', () => ({ __esModule: true, default: () => null }));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

function setLine(patch: Partial<DraftLine> = {}): DraftLine {
  return {
    ...emptyDraftLine(),
    key: 'l1',
    line_type: 'product_set',
    product_id: null,
    product_set_id: 's1',
    name: 'ZZT Vanity',
    code: 'ZZT-SET',
    ...patch,
  } as DraftLine;
}

function renderTable(line: DraftLine, listPrice: number | null, sellPrice: number | null) {
  const linePricing = {
    l1: {
      key: 'l1',
      list_price: listPrice,
      promotion_options: [],
      auto_promotion_id: null,
      sell_price: sellPrice,
      sell_price_basis: 'list',
      parts_at_list: [],
      candidates: [],
    },
  };
  const editor = new Proxy(
    { linePricing, fetchItemOptions: async () => [] },
    { get: (target, key) => (key in target ? (target as never)[key] : vi.fn()) },
  ) as never;
  render(
    <PriceTagLinesTable
      lines={[line]}
      priceMode="list"
      isMobile={false}
      editor={editor}
      showNumberErrors={false}
    />,
  );
}

describe('a set line shows its prices', () => {
  it('LP: the toggle and the list price figure', () => {
    renderTable(setLine({ price_type: 'list' }), 900, 900);
    expect(screen.getByRole('radio', { name: 'LP' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'SP' })).toBeInTheDocument();
    expect(screen.getByText('RM 900')).toBeInTheDocument();
  });

  it('SP: selling price is text (no input), the Promotion cell reads "-"', () => {
    renderTable(setLine({ price_type: 'selling' }), 900, 850);
    expect(screen.getByRole('radio', { name: 'SP' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('RM 900')).toBeInTheDocument();
    expect(screen.getByText('RM 850')).toBeInTheDocument();
    expect(screen.queryByLabelText('Selling price for line 1')).toBeNull();
    expect(screen.queryByLabelText('Promotion')).toBeNull();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('a set whose price cannot be worked out shows "-" and no RM figure', () => {
    renderTable(setLine({ price_type: 'list' }), null, null);
    expect(screen.getByRole('radio', { name: 'LP' })).toBeInTheDocument();
    expect(screen.queryByText(/RM/)).toBeNull();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});
