/**
 * PRICETAG-UPGRADE-VARIANTS FE test 9 (AC-F2b, F2c, F7): "Variants on this tag" on a request line.
 *
 * Written test-FIRST. Chosen draft-line fields (loaded by the line editor from the chooser lookup):
 *   variant_members?: { product_id, code, name, list_price, is_discontinued }[]
 *   own_list_price?: number | null
 *   excluded_variant_ids?: string[]      the UNTICKED members
 * The control is a SearchableMultiSelect labelled "Variants on this tag" whose `value` is the ticked
 * ids INCLUDING the line's own product (locked: its option is `disabled`), and whose onChange is turned
 * into `editor.updateLine(key, { excluded_variant_ids })`. Counting: "N of M ticked" counts the own
 * product plus live members; discontinued members are shown with a "Discontinued" hint, not counted.
 * The warning reads "Variants price differently: RM x to RM y" over the own price and ticked live members.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

type Option = { value: string; label: string; disabled?: boolean; badgeText?: string; description?: string };
const captured = vi.hoisted(() => ({
  multi: [] as { value: string[]; options: Option[]; onChange: (v: string[]) => void; placeholder?: string; id?: string; 'aria-label'?: string }[],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: { placeholder?: string; options?: { value: string; label: string }[] }) => (
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
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    options?: Option[];
    onChange: (v: string[]) => void;
    placeholder?: string;
    id?: string;
    'aria-label'?: string;
  }) => {
    captured.multi.push({ ...props, options: props.options ?? [] });
    return (
      <div data-testid="multi" aria-label={props['aria-label']}>
        {(props.options ?? []).map((o) => (
          <span key={o.value} data-testid={`opt-${o.label.split(' ')[0]}`}>
            {o.label} {o.badgeText ?? ''} {o.description ?? ''}
          </span>
        ))}
      </div>
    );
  },
}));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import type { DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const member = (code: string, list: number, over: Record<string, unknown> = {}) => ({
  product_id: `id-${code}`, code, name: code, list_price: list, is_discontinued: false, ...over,
});

const MEMBERS = [
  member('SRTWC8354-SH-150', 1750),
  member('SRTWC8354-SH-200', 1750),
  member('SRTWC8354-SH-P', 1750, { is_discontinued: true }),
  member('SRTWC8354-SH-UF-300', 1800),
];

function line(extra: Record<string, unknown> = {}): DraftLine {
  return {
    key: 'l1', line_type: 'product', product_id: 'p1', product_set_id: null, name: 'WC', code: 'SRTWC8354-SH',
    quantity: 1, included_accessories: '', remarks: '', guard_error: null, combo_id: null, combos: [],
    combos_loaded: true, host_guarded: false, parts: [], promotion_id: null, promotion_locked: false,
    manual_sell_price: null, pricing: null,
    variant_members: MEMBERS, own_list_price: 1750, excluded_variant_ids: [],
    ...extra,
  } as unknown as DraftLine;
}

function renderTable(l: DraftLine) {
  const updateLine = vi.fn();
  const editor = new Proxy({ linePricing: {}, updateLine }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  render(<PriceTagLinesTable lines={[l]} priceMode={'list' as never} isMobile={false} editor={editor} showNumberErrors={false} />);
  return { updateLine, multi: () => captured.multi[captured.multi.length - 1] };
}

beforeEach(() => {
  captured.multi.length = 0;
});

describe('Variants on this tag', () => {
  it('lists the line own product and every member, all ticked by default', () => {
    const { multi } = renderTable(line());
    const control = multi();
    expect(control).toBeDefined();
    const codes = control.options.map((o) => o.label.split(' ')[0]);
    expect(codes).toEqual(expect.arrayContaining(['SRTWC8354-SH', 'SRTWC8354-SH-150', 'SRTWC8354-SH-200', 'SRTWC8354-SH-UF-300']));
    expect([...control.value].sort()).toEqual(
      ['p1', 'id-SRTWC8354-SH-150', 'id-SRTWC8354-SH-200', 'id-SRTWC8354-SH-UF-300', 'id-SRTWC8354-SH-P'].sort(),
    );
  });

  it('is labelled Variants on this tag', () => {
    renderTable(line());
    expect(screen.getByText('Variants on this tag')).toBeInTheDocument();
  });

  it('locks the line own product on', () => {
    const { multi } = renderTable(line());
    const own = multi().options.find((o) => o.value === 'p1');
    expect(own?.disabled).toBe(true);
  });

  it('shows a Discontinued hint on a discontinued member', () => {
    const { multi } = renderTable(line());
    const p = multi().options.find((o) => o.value === 'id-SRTWC8354-SH-P');
    expect(`${p?.label} ${p?.badgeText ?? ''} ${p?.description ?? ''}`).toMatch(/Discontinued/);
    const live = multi().options.find((o) => o.value === 'id-SRTWC8354-SH-150');
    expect(`${live?.label} ${live?.badgeText ?? ''} ${live?.description ?? ''}`).not.toMatch(/Discontinued/);
  });

  it('counts N of M ticked without the discontinued member', () => {
    renderTable(line());
    expect(screen.getByText('4 of 4 ticked')).toBeInTheDocument();
  });

  it('counts an unticked member out', () => {
    renderTable(line({ excluded_variant_ids: ['id-SRTWC8354-SH-UF-300'] }));
    expect(screen.getByText('3 of 4 ticked')).toBeInTheDocument();
  });

  it('unticking a member sends it as excluded_variant_ids', () => {
    const { updateLine, multi } = renderTable(line());
    const ticked = multi().value.filter((id) => id !== 'id-SRTWC8354-SH-UF-300');
    multi().onChange(ticked);
    expect(updateLine).toHaveBeenCalledWith('l1', expect.objectContaining({ excluded_variant_ids: ['id-SRTWC8354-SH-UF-300'] }));
  });

  it('re-ticking everything sends an empty list', () => {
    const { updateLine, multi } = renderTable(line({ excluded_variant_ids: ['id-SRTWC8354-SH-150'] }));
    multi().onChange(multi().options.map((o) => o.value));
    expect(updateLine).toHaveBeenCalledWith('l1', expect.objectContaining({ excluded_variant_ids: [] }));
  });

  it('never sends the line own product as excluded, whatever the control returns', () => {
    const { updateLine, multi } = renderTable(line());
    multi().onChange([]);
    const patch = updateLine.mock.calls[0][1] as { excluded_variant_ids: string[] };
    expect(patch.excluded_variant_ids).not.toContain('p1');
  });

  it('is not shown for a product with no members', () => {
    renderTable(line({ variant_members: [] }));
    expect(captured.multi).toHaveLength(0);
    expect(screen.queryByText('Variants on this tag')).toBeNull();
  });

  it('is not shown before the members were asked (absent)', () => {
    renderTable(line({ variant_members: undefined }));
    expect(screen.queryByText('Variants on this tag')).toBeNull();
  });
});

describe('Variants price differently (Q5 a, AC-F7)', () => {
  it('warns with the lowest and highest list price of the line product and ticked live members', () => {
    renderTable(line());
    expect(screen.getByText('Variants price differently: RM 1,750 to RM 1,800')).toBeInTheDocument();
  });

  it('hides once the differing member is unticked', () => {
    renderTable(line({ excluded_variant_ids: ['id-SRTWC8354-SH-UF-300'] }));
    expect(screen.queryByText(/Variants price differently/)).toBeNull();
  });

  it('hides when every price is equal', () => {
    renderTable(line({ variant_members: [member('SRTWC8354-SH-150', 1750), member('SRTWC8354-SH-200', 1750)] }));
    expect(screen.queryByText(/Variants price differently/)).toBeNull();
  });

  it('ignores a discontinued member price', () => {
    renderTable(line({ variant_members: [member('SRTWC8354-SH-150', 1750), member('SRTWC8354-SH-P', 900, { is_discontinued: true })] }));
    expect(screen.queryByText(/Variants price differently/)).toBeNull();
  });

  it('counts the line own price in the range', () => {
    renderTable(line({ own_list_price: 1600, variant_members: [member('SRTWC8354-SH-150', 1750)] }));
    expect(screen.getByText('Variants price differently: RM 1,600 to RM 1,750')).toBeInTheDocument();
  });

  it('is a warning only: the row still renders its other controls', () => {
    renderTable(line());
    expect(screen.getByLabelText('Quantity for line 1')).toBeInTheDocument();
  });
});
