/**
 * PRICETAG-REQUEST-LAYOUT, crew browser pass 11 Nov: at 375px the line table (520-560px wide)
 * scrolled inside its card and cut Qty at the edge. On a phone both tables keep only #, Item,
 * Qty (and the edit table's two icons) as columns, with no width floor; prices and remarks stack
 * under the item, as the prices already did (AC-S1-11).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
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
import { PriceTagLinesView } from './PriceTagLinesView';
import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const opt = (id: string) => ({
  id,
  name: `Tpl ${id}`,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
});

function mk(key: string, patch: Record<string, unknown> = {}): DraftLine {
  return {
    ...emptyDraftLine(),
    key,
    product_id: `p-${key}`,
    name: `ZZT ${key}`,
    code: `ZZT-${key}`,
    tag_templates_for: `p-${key}`,
    tag_templates: [opt('a')],
    tag_template_id: 'a',
    ...patch,
  } as DraftLine;
}

function renderTable(
  lines: DraftLine[],
  { priceMode = 'list', onPreviewLine, isMobile = false }: { priceMode?: string; onPreviewLine?: (key: string) => void; isMobile?: boolean } = {},
) {
  const updateLine = vi.fn();
  const linePricing = Object.fromEntries(
    lines.map((l) => [
      l.key,
      {
        key: l.key,
        list_price: 1000,
        promotion_options: [{ id: 'promo-1', description: 'ZZT Promo', sell_price: 800 }],
        auto_promotion_id: null,
        sell_price: l.promotion_id ? 800 : null,
        sell_price_basis: l.promotion_id ? 'promotion' : 'list',
        parts_at_list: [],
        candidates: [],
      },
    ]),
  );
  const editor = new Proxy({ linePricing, updateLine }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  render(
    <PriceTagLinesTable
      lines={lines}
      priceMode={priceMode as never}
      isMobile={isMobile}
      editor={editor}
      showNumberErrors={false}
      {...({ onPreviewLine } as object)}
    />,
  );
  return { updateLine };
}


const headers = () => screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim());

describe('edit table on a phone', () => {
  it('has only #, Item, Qty and the icon column, and no width floor', () => {
    renderTable([mk('a', { remarks: 'Top shelf' })], { isMobile: true });
    expect(headers()).toEqual(['#', 'Item', 'Qty (tags)', '']);
    expect(screen.getByRole('table').className).not.toMatch(/min-w-\[/);
  });

  it('puts the remarks under the item', () => {
    renderTable([mk('a', { remarks: 'Top shelf' })], { isMobile: true });
    const remarks = screen.getByLabelText('Remarks for line 1');
    expect(within(screen.getByTestId('line-pricing-stack').closest('td') as HTMLElement).getByLabelText('Remarks for line 1')).toBe(remarks);
  });

  it('keeps the desktop columns at desktop width', () => {
    renderTable([mk('a')]);
    expect(headers()).toContain('Remarks');
  });
});

describe('read-only table on a phone', () => {
  const LINE = {
    id: 'l-1', line_type: 'product' as const, product_id: 'p-1', name: 'ZZT Basin', code: 'ZZT-1',
    quantity: 2, remarks: 'Top shelf', list_price: 320, parts: [],
  };

  it('has only #, Item and Qty columns, no width floor, and the remarks under the item', () => {
    render(<PriceTagLinesView lines={[LINE] as never} priceMode="list" isMobile />);
    expect(headers()).toEqual(['#', 'Item', 'Qty (tags)']);
    expect(screen.getByRole('table').className).not.toMatch(/min-w-\[/);
    const itemCell = screen.getByText('ZZT Basin').closest('td') as HTMLElement;
    expect(within(itemCell).getByText('Top shelf')).toBeInTheDocument();
  });
});
