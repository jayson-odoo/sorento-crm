/**
 * PRICETAG-LPSP S6: the lines table gives each line its own LP/SP (AC-19), a typed selling price
 * only where it can apply (AC-19) and an eye icon that previews that line's tag (AC-20).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The table has one header-driven price mode and no
 * per-line control or preview button yet.
 *
 * Contract this file pins (the captain confirms with the coder):
 * - per line, a radiogroup with two radios named exactly "LP" and "SP"; the checked one is
 *   `line.price_type`, else the table's `priceMode` prop (the header default);
 * - a click reports through `editor.updateLine(key, { price_type })`;
 * - the typed selling price keeps its label "Selling price for line N"; it is absent or disabled on
 *   an LP line and on a line with a promotion, and present and enabled on an SP line without one,
 *   whatever the header says;
 * - the eye is a button named "Preview tag for line N", disabled while the line has no template; a
 *   click calls the table's optional `onPreviewLine(key)` prop (the form owns the lightbox).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

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
  { priceMode = 'list', onPreviewLine }: { priceMode?: string; onPreviewLine?: (key: string) => void } = {},
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
      isMobile={false}
      editor={editor}
      showNumberErrors={false}
      {...({ onPreviewLine } as object)}
    />,
  );
  return { updateLine };
}

const radio = (name: 'LP' | 'SP', index = 0) => screen.getAllByRole('radio', { name })[index];

function typedPriceBlocked(index: number) {
  const input = screen.queryByLabelText(`Selling price for line ${index}`) as HTMLInputElement | null;
  // absent counts as blocked; present must be disabled
  return input === null || input.disabled === true;
}

describe('PriceTagLinesTable per-line LP/SP (AC-19)', () => {
  it('gives every line its own LP and SP radios, showing the line type', () => {
    renderTable([mk('l1', { price_type: 'list' }), mk('l2', { price_type: 'selling' })]);
    expect(screen.getAllByRole('radio', { name: 'LP' })).toHaveLength(2);
    expect(screen.getAllByRole('radio', { name: 'SP' })).toHaveLength(2);
    expect(radio('LP', 0)).toHaveAttribute('aria-checked', 'true');
    expect(radio('SP', 0)).toHaveAttribute('aria-checked', 'false');
    expect(radio('LP', 1)).toHaveAttribute('aria-checked', 'false');
    expect(radio('SP', 1)).toHaveAttribute('aria-checked', 'true');
  });

  it('a list-mode table can show an SP line next to an LP line', () => {
    renderTable([mk('l1', { price_type: 'list' }), mk('l2', { price_type: 'selling' })], {
      priceMode: 'list',
    });
    expect(radio('SP', 1)).toHaveAttribute('aria-checked', 'true');
  });

  it('a line with no type of its own shows the header default', () => {
    renderTable([mk('l1')], { priceMode: 'selling' });
    expect(radio('SP')).toHaveAttribute('aria-checked', 'true');
    expect(radio('LP')).toHaveAttribute('aria-checked', 'false');
  });

  it('clicking SP on an LP line reports the new type for that line only', () => {
    const { updateLine } = renderTable([mk('l1', { price_type: 'list' }), mk('l2', { price_type: 'list' })]);
    fireEvent.click(radio('SP', 1));
    expect(updateLine).toHaveBeenCalledTimes(1);
    expect(updateLine).toHaveBeenCalledWith('l2', expect.objectContaining({ price_type: 'selling' }));
  });

  it('clicking LP on an SP line reports list', () => {
    const { updateLine } = renderTable([mk('l1', { price_type: 'selling' })]);
    fireEvent.click(radio('LP'));
    expect(updateLine).toHaveBeenCalledWith('l1', expect.objectContaining({ price_type: 'list' }));
  });
});

describe('PriceTagLinesTable typed selling price (AC-19)', () => {
  it('is enabled on an SP line without a promotion, even under a List header', () => {
    renderTable([mk('l1', { price_type: 'selling' })], { priceMode: 'list' });
    const input = screen.getByLabelText('Selling price for line 1') as HTMLInputElement;
    expect(input.disabled).toBe(false);
  });

  it('is blocked on an LP line, even under a Selling header', () => {
    renderTable([mk('l1', { price_type: 'list' })], { priceMode: 'selling' });
    expect(typedPriceBlocked(1)).toBe(true);
  });

  it('is blocked on an SP line that has a promotion', () => {
    renderTable([mk('l1', { price_type: 'selling', promotion_id: 'promo-1' })], {
      priceMode: 'selling',
    });
    expect(typedPriceBlocked(1)).toBe(true);
  });

  it('is decided line by line in a mixed request', () => {
    renderTable(
      [
        mk('l1', { price_type: 'list' }),
        mk('l2', { price_type: 'selling' }),
        mk('l3', { price_type: 'selling', promotion_id: 'promo-1' }),
      ],
      { priceMode: 'list' },
    );
    expect(typedPriceBlocked(1)).toBe(true);
    expect(typedPriceBlocked(2)).toBe(false);
    expect(typedPriceBlocked(3)).toBe(true);
  });
});

describe('PriceTagLinesTable preview eye (AC-20)', () => {
  it('has a Preview tag button on every line', () => {
    renderTable([mk('l1'), mk('l2')]);
    expect(screen.getAllByRole('button', { name: /^Preview tag/ })).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Preview tag for line 2' })).toBeInTheDocument();
  });

  it('opens that line: a click reports its key', () => {
    const onPreviewLine = vi.fn();
    renderTable([mk('l1'), mk('l2')], { onPreviewLine });
    fireEvent.click(screen.getByRole('button', { name: 'Preview tag for line 2' }));
    expect(onPreviewLine).toHaveBeenCalledTimes(1);
    expect(onPreviewLine).toHaveBeenCalledWith('l2');
  });

  it('is enabled on a line with a picked template', () => {
    renderTable([mk('l1', { tag_templates: [opt('a'), opt('b')], tag_template_id: 'b' })]);
    expect(screen.getByRole('button', { name: 'Preview tag for line 1' })).toBeEnabled();
  });

  it('is disabled, and the row says so, when the product has no template', () => {
    const onPreviewLine = vi.fn();
    renderTable([mk('l1', { tag_templates: [], tag_template_id: null })], { onPreviewLine });
    const eye = screen.getByRole('button', { name: 'Preview tag for line 1' });
    expect(eye).toBeDisabled();
    fireEvent.click(eye);
    expect(onPreviewLine).not.toHaveBeenCalled();
    expect(screen.getByText('No tag template yet')).toBeInTheDocument();
  });

  it('is disabled on a row with no item yet', () => {
    renderTable([{ ...emptyDraftLine(), key: 'l1' } as DraftLine]);
    expect(screen.getByRole('button', { name: 'Preview tag for line 1' })).toBeDisabled();
  });
});
