/** PRICETAG-TEMPLATE-PER-PRODUCT AC-14: the line's Template field (one = text, many = select, none = nothing). */
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

const opt = (id: string) => ({ id, name: `Tpl ${id}`, family: 'ala_carte', published: true, width_mm: 80, height_mm: 50 });

function renderTable(patch: Partial<DraftLine>) {
  const chooseTemplate = vi.fn();
  const editor = new Proxy({ linePricing: {}, chooseTemplate }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  const l = { ...emptyDraftLine(), key: 'l1', product_id: 'p1', name: 'ZZT', code: 'ZZT1', ...patch } as DraftLine;
  render(<PriceTagLinesTable lines={[l]} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />);
  return { chooseTemplate };
}

describe('PriceTagLinesTable Template field', () => {
  it('one template: plain text, no select', () => {
    renderTable({ tag_templates_for: 'p1', tag_templates: [opt('a')], tag_template_id: 'a' });
    expect(screen.getByText('Template: Tpl a')).toBeInTheDocument();
    expect(screen.queryByLabelText('Tag template')).toBeNull();
  });

  it('many templates: a select that reports the pick', () => {
    const { chooseTemplate } = renderTable({ tag_templates_for: 'p1', tag_templates: [opt('a'), opt('b')] });
    fireEvent.change(screen.getByLabelText('Tag template'), { target: { value: 'b' } });
    expect(chooseTemplate).toHaveBeenCalledWith('l1', 'b');
  });

  it('no template: nothing drawn', () => {
    renderTable({ tag_templates_for: 'p1', tag_templates: [] });
    expect(screen.queryByText(/^Template:/)).toBeNull();
    expect(screen.queryByLabelText('Tag template')).toBeNull();
  });

  it('a row refusal carries the anchor Submit scrolls to', () => {
    renderTable({
      tag_templates_for: 'p1',
      tag_templates: [opt('a'), opt('b')],
      guard_error: 'Pick a tag template for this line.',
    });
    const message = screen.getByText('Pick a tag template for this line.');
    expect(message).toHaveAttribute('data-error-anchor', 'line:0');
  });
});
