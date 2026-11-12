/**
 * PRICETAG-UPGRADE-VARIANTS review fix round 1, item 11: the "Variants on this tag" trigger shows
 * "N of M ticked", never the joined codes (eight codes overflowed the box at 1280px); the codes
 * stay readable in its title.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div />,
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    options?: { value: string; label: string }[];
    renderTriggerLabel?: (selected: { value: string; label: string }[]) => React.ReactNode;
  }) => {
    const selected = (props.options ?? []).filter((o) => props.value.includes(o.value));
    return <div data-testid="trigger">{props.renderTriggerLabel?.(selected)}</div>;
  },
}));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import type { DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const CODES = ['150', '200', 'P', 'UF', 'UF-150', 'UF-200', 'UF-300'].map((c) => `SRTWC8354-SH-${c}`);

const line = {
  key: 'l1', line_type: 'product', product_id: 'p1', product_set_id: null, name: 'WC', code: 'SRTWC8354-SH',
  quantity: 1, included_accessories: '', remarks: '', guard_error: null, combo_id: null, combos: [],
  combos_loaded: true, host_guarded: false, parts: [], promotion_id: null, promotion_locked: false,
  manual_sell_price: null, pricing: null, own_list_price: 1750,
  variant_members: CODES.map((code) => ({ product_id: `id-${code}`, code, name: code, list_price: 1750, is_discontinued: false })),
  excluded_variant_ids: ['id-SRTWC8354-SH-UF-300'],
  // The row shows only for a chosen template that reads "All variants" (crew re-pass 1).
  tag_template_id: 't-family',
  tag_templates: [{ id: 't-family', name: 'WC FAMILY TEST', reads_variants: true }],
} as unknown as DraftLine;

describe('Variants on this tag trigger', () => {
  it('reads N of M ticked, with the ticked codes in its title', () => {
    const editor = new Proxy({ linePricing: {}, updateLine: vi.fn() }, {
      get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
    }) as never;
    render(<PriceTagLinesTable lines={[line]} priceMode={'list' as never} isMobile={false} editor={editor} showNumberErrors={false} />);
    const trigger = screen.getByTestId('trigger');
    const label = within(trigger).getByText('7 of 8 ticked');
    expect(trigger.textContent).not.toContain('SRTWC8354-SH-150');
    expect(label.getAttribute('title')).toContain('SRTWC8354-SH-150');
    expect(label.getAttribute('title')).not.toContain('UF-300');
    expect(label.className).toContain('truncate');
  });
});
