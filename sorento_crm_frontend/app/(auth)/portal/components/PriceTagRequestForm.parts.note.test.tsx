/**
 * PRICETAG-COMBO AC-3.1: the sentence under an open choice row says what the tag will be.
 * A line with a combo gets one tag listing every option; a line with none keeps one tag per option.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: { placeholder?: string }) => (
    <select aria-label={props.placeholder ?? ''} />
  ),
}));

import { PriceTagLinesTable } from '@/components/dealer-kit/PriceTagLinesTable';
import type { DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

function line(comboId: string | null, parts?: unknown[]): DraftLine {
  return {
    key: 'l1',
    line_type: 'product',
    product_id: 'p1',
    product_set_id: null,
    name: 'ZZT Cabinet',
    code: 'ZZTC1',
    quantity: 1,
    included_accessories: '',
    remarks: '',
    guard_error: null,
    combo_id: comboId,
    combos: [{ combo_id: 'c1', name: '3 in 1', parts: [] }],
    combos_loaded: true,
    host_guarded: true,
    parts: parts ?? [
      {
        key: 'part-1',
        product_id: null,
        code: '',
        name: '',
        role: 'Basin',
        candidates: [
          { product_id: 'b1', code: 'ZZTB1', name: 'White' },
          { product_id: 'b2', code: 'ZZTB2', name: 'Black' },
        ],
      },
    ],
    promotion_id: null,
    promotion_locked: false,
    manual_sell_price: null,
    pricing: null,
  } as unknown as DraftLine;
}

function renderTable(comboId: string | null, parts?: unknown[]) {
  const editor = new Proxy({ linePricing: {} }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  render(
    <PriceTagLinesTable
      lines={[line(comboId, parts)]}
      priceMode="list"
      isMobile={false}
      editor={editor}
      showNumberErrors={false}
    />,
  );
}

describe('open choice row sentence (AC-3.1)', () => {
  it('a line with a combo says the tag will list every option', () => {
    renderTable('c1');
    expect(screen.getByText('The tag will list every option.')).toBeInTheDocument();
    expect(screen.queryByText('Marketing will prepare one tag per option.')).toBeNull();
  });

  it('a line with no combo keeps one tag per option', () => {
    renderTable(null);
    expect(screen.getByText('Marketing will prepare one tag per option.')).toBeInTheDocument();
    expect(screen.queryByText('The tag will list every option.')).toBeNull();
  });
});

describe('the Upgrade row (AC-3.5)', () => {
  const upgradeRow = (candidates: unknown[]) => [
    { key: 'u1', product_id: null, code: '', name: '', role: 'Upgrade', candidates },
  ];

  it('a single upgrade is still a select, with a No upgrade placeholder', () => {
    renderTable('c1', upgradeRow([{ product_id: 'u', code: 'ZZU', name: 'Stone', topup_amount: 100 }]));
    expect(screen.getByLabelText('No upgrade')).toBeInTheDocument();
    expect(screen.getByText('The tag will list every option.')).toBeInTheDocument();
  });

  it('a single-candidate group that is not an upgrade stays a plain row (AC-S12-1)', () => {
    renderTable('c1', [
      { key: 'g1', product_id: 'b1', code: 'ZZTB1', name: 'White', role: 'Basin',
        candidates: [{ product_id: 'b1', code: 'ZZTB1', name: 'White' }] },
    ]);
    expect(screen.queryByLabelText(/Not sure/)).toBeNull();
    expect(screen.queryByLabelText('No upgrade')).toBeNull();
  });
});
