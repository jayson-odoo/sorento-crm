/**
 * PRICETAG-COMBO AC-3.5 and AC-2.6 on the lines table: the Upgrade row, its option labels,
 * and the combo price shown in the selling box.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// A select that renders its options, so a label is something a test can read.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    options?: { value: string; label: string }[];
  }) => (
    <select aria-label={props.placeholder ?? ''}>
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import type { DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

function line(parts: unknown[], extra: Record<string, unknown> = {}): DraftLine {
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
    combo_id: 'c1',
    combos: [],
    combos_loaded: true,
    host_guarded: true,
    parts,
    promotion_id: null,
    promotion_locked: false,
    manual_sell_price: null,
    pricing: null,
    ...extra,
  } as unknown as DraftLine;
}

function renderTable(l: DraftLine, linePricing: Record<string, unknown> = {}, priceMode = 'list') {
  const editor = new Proxy({ linePricing }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  render(
    <PriceTagLinesTable lines={[l]} priceMode={priceMode as never} isMobile={false} editor={editor} showNumberErrors={false} />,
  );
}

const open = (candidates: unknown[]) => [
  { key: 'u1', product_id: null, code: '', name: '', role: 'Upgrade', candidates },
];

describe('Upgrade row', () => {
  it('labels an option with its top-up', () => {
    renderTable(line(open([{ product_id: 'u', code: 'ZZU', name: 'Stone', topup_amount: 100 }])));
    expect(screen.getByRole('option', { name: /ZZU\s+\+RM 100/ })).toBeInTheDocument();
  });

  it('labels a blank top-up with the bare code, never the list price', () => {
    renderTable(
      line(open([{ product_id: 'u', code: 'ZZU', name: 'Stone' }])),
      { l1: { candidates: [{ product_id: 'u', list_price: 500, sell_price: 500 }] } },
    );
    expect(screen.getByRole('option', { name: 'ZZU' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /RM 500/ })).toBeNull();
  });

  it('reads the top-up from the reloaded package on a reopened draft', () => {
    renderTable(
      line(open([{ product_id: 'u', code: 'ZZU', name: 'Stone' }]), {
        combos: [
          {
            combo_id: 'c1',
            name: '3 in 1',
            parts: [{ product_id: 'u', code: 'ZZU', name: 'Stone', choice_group: null, is_upgrade: true, topup_amount: 250 }],
          },
        ],
      }),
    );
    expect(screen.getByRole('option', { name: /ZZU\s+\+RM 250/ })).toBeInTheDocument();
  });

  it('reads the top-up from the line\'s chosen package, not another one carrying the same upgrade', () => {
    const upgrade = (topup: number) => [
      { product_id: 'u', code: 'ZZU', name: 'Stone', choice_group: null, is_upgrade: true, topup_amount: topup },
    ];
    renderTable(
      line(open([{ product_id: 'u', code: 'ZZU', name: 'Stone' }]), {
        combo_id: 'c2',
        combos: [
          { combo_id: 'c1', name: '3 in 1', parts: upgrade(100) },
          { combo_id: 'c2', name: '4 in 1', parts: upgrade(300) },
        ],
      }),
    );
    expect(screen.getByRole('option', { name: /ZZU\s+\+RM 300/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /RM 100/ })).toBeNull();
  });

  it('a resolved upgrade (reopened draft, no candidates) is a plain row, not No upgrade', () => {
    renderTable(
      line([{ key: 'u1', product_id: 'u', code: 'ZZU', name: 'Stone', role: 'Upgrade', candidates: [] }]),
    );
    expect(screen.queryByLabelText('No upgrade')).toBeNull();
    expect(screen.getByText('Stone')).toBeInTheDocument();
  });
});

describe('Selling price box on a combo line (AC-2.6)', () => {
  it('shows the combo price as its placeholder when the basis is not list', () => {
    renderTable(line([]), { l1: { sell_price: 1099, sell_price_basis: 'promotion', candidates: [] } }, 'selling');
    expect(screen.getByLabelText('Selling price for line 1')).toHaveAttribute('placeholder', 'RM 1,099');
  });

  it('keeps the plain placeholder on a list basis or without a combo', () => {
    renderTable(line([]), { l1: { sell_price: 1090, sell_price_basis: 'list', candidates: [] } }, 'selling');
    expect(screen.getByLabelText('Selling price for line 1')).toHaveAttribute('placeholder', 'Type a price');
  });
});
