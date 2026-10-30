/**
 * SET-QUOTE-LINE A7 / F2 and the owner's naming ruling (14 Oct, "just call Non-standard"): a
 * linked product or set outside the series reads "Non-standard" with the series tooltip; the word
 * "custom" appears nowhere, and a line never shows two Non-standard pills.
 *
 * QUOTE-NO-FREE-TEXT AC-11: "Not a catalogue product" never renders - a line with neither a
 * product nor a set is refused on save, so it no longer has a flag of its own.
 *
 * Owner meeting 29 Oct: the below-floor flag leaves the product cell. It sits under the price in
 * the Rate cell (`MinimumPriceFlag`) and reads "Minimum price RM x", never "Below floor".
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationLine } from '../../_shared/types/project.types';

const useLineVerdict = vi.hoisted(() => vi.fn((..._args: unknown[]) => ({ data: undefined as unknown })));
vi.mock('../../_shared/hooks/useProjects', () => ({
  useLineVerdict,
}));
vi.mock('./QuotationsPanel', () => ({
  formatMyr: (value: string) => `RM ${value}`,
}));

import { LineFlags, MinimumPriceFlag } from './QuotationLineFlags';
import { emptyDraft } from './quotationLineDraft';

function line(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 'l1',
    version_id: 'v1',
    product_id: null,
    product_set_id: null,
    set_parts: [],
    unit_price: '900.00',
    is_below_floor: false,
    is_non_standard: false,
    ...overrides,
  } as QuotationLine;
}

describe('LineFlags', () => {
  const draftOf = (extra: Record<string, string> = {}) => ({
    ...emptyDraft(),
    unit_price: '900.00',
    ...extra,
  });

  it('shows no pill at all for a clean line that names a set', () => {
    render(
      <LineFlags
        quotationId="q1"
        line={line({ product_set_id: 'set-1' })}
        draft={draftOf({ product_set_id: 'set-1' })}
      />,
    );
    expect(screen.queryByText('Non-standard')).not.toBeInTheDocument();
    expect(screen.queryByText(/custom/i)).toBeNull();
  });

  it('never reads "Not a catalogue product" for a line with neither product nor set', () => {
    render(<LineFlags quotationId="q1" line={line()} draft={draftOf()} />);
    expect(screen.queryByText(/Not a catalogue product/i)).toBeNull();
    expect(screen.queryByTitle('Not a catalogue product')).toBeNull();
    expect(screen.queryByText('Non-standard')).not.toBeInTheDocument();
    expect(screen.queryByText(/custom/i)).toBeNull();
  });

  it('never reads "Not a catalogue product" even when the server marks a no-product line non-standard', () => {
    render(
      <LineFlags
        quotationId="q1"
        line={line({ is_non_standard: true })}
        draft={draftOf()}
      />,
    );
    expect(screen.queryByText(/Not a catalogue product/i)).toBeNull();
    expect(screen.queryByTitle('Not a catalogue product')).toBeNull();
  });

  it('AC-20: a row with neither product nor set never shows Non-standard, even when the stored line says so', () => {
    render(
      <LineFlags
        quotationId="q1"
        line={line({ is_non_standard: true })}
        draft={draftOf()}
      />,
    );
    expect(screen.queryByText('Non-standard')).toBeNull();
  });

  it('AC-20: an edited row with neither product nor set shows no pill and asks no series verdict', () => {
    useLineVerdict.mockClear();
    useLineVerdict.mockReturnValue({ data: { is_non_standard: true, is_below_floor: false } });
    render(
      <LineFlags
        quotationId="q1"
        line={line()}
        draft={draftOf({ description: 'Bespoke basin test', unit_price: '123.00' })}
      />,
    );
    expect(screen.queryByText('Non-standard')).toBeNull();
    // Third argument is `enabled`: no request may be armed for a row with no product or set.
    expect(useLineVerdict.mock.calls.every((call) => call[2] === false)).toBe(true);
    useLineVerdict.mockReturnValue({ data: undefined });
  });

  it('shows exactly one Non-standard pill for a non-standard product line', () => {
    render(
      <LineFlags
        quotationId="q1"
        line={line({ product_id: 'p1', is_non_standard: true })}
        draft={draftOf({ product_id: 'p1' })}
      />,
    );
    expect(screen.getAllByText('Non-standard')).toHaveLength(1);
    expect(screen.queryByTitle('Not a catalogue product')).toBeNull();
    expect(screen.queryByText(/custom/i)).toBeNull();
  });

  it('keeps the series tooltip on a set line outside the series, as one pill', () => {
    render(
      <LineFlags
        quotationId="q1"
        line={line({ product_set_id: 'set-1', is_non_standard: true })}
        draft={draftOf({ product_set_id: 'set-1' })}
      />,
    );
    expect(screen.getAllByText('Non-standard')).toHaveLength(1);
    expect(screen.getByText('Non-standard')).toHaveAttribute(
      'title',
      'Outside the series this scope is quoted from',
    );
    expect(screen.queryByText(/custom/i)).toBeNull();
  });

  it('keeps the series tooltip on a linked product outside the series', () => {
    render(
      <LineFlags
        quotationId="q1"
        line={line({ product_id: 'p1', is_non_standard: true })}
        draft={draftOf({ product_id: 'p1' })}
      />,
    );
    expect(screen.getByText('Non-standard')).toHaveAttribute(
      'title',
      'Outside the series this scope is quoted from',
    );
  });

  it('keeps the minimum price out of the product cell, and shows no non-standard pill there', () => {
    const below = line({
      product_set_id: 'set-1',
      is_below_floor: true,
      floor_value_applied: '900.00',
      floor_level_applied: 'series',
    });
    render(
      <LineFlags quotationId="q1" line={below} draft={draftOf({ product_set_id: 'set-1' })} />,
    );
    expect(screen.queryByText(/Minimum price/)).toBeNull();
    expect(screen.queryByText(/below floor/i)).toBeNull();
    expect(screen.queryByText('Non-standard')).not.toBeInTheDocument();
    expect(screen.queryByText(/custom/i)).toBeNull();
  });
});

describe('MinimumPriceFlag', () => {
  const draftOf = (extra: Record<string, string> = {}) => ({
    ...emptyDraft(),
    unit_price: '400.00',
    ...extra,
  });

  it('reads Minimum price RM x for a line priced below its floor, with where it was set', () => {
    render(
      <MinimumPriceFlag
        quotationId="q1"
        line={line({
          product_id: 'p1',
          unit_price: '400.00',
          is_below_floor: true,
          floor_value_applied: '700.00',
          floor_level_applied: 'category_ancestor',
        })}
        draft={draftOf({ product_id: 'p1' })}
      />,
    );
    expect(screen.getByText('Minimum price RM 700.00')).toBeInTheDocument();
    expect(screen.getByText('Set on a parent category.')).toBeInTheDocument();
    expect(screen.queryByText(/below floor/i)).toBeNull();
    expect(screen.queryByText(/\bfloor\b/i)).toBeNull();
  });

  it('says the line is below the minimum price when no floor value came back', () => {
    render(
      <MinimumPriceFlag
        quotationId="q1"
        line={line({ product_id: 'p1', unit_price: '400.00', is_below_floor: true })}
        draft={draftOf({ product_id: 'p1' })}
      />,
    );
    expect(screen.getByText('Minimum price')).toBeInTheDocument();
    expect(screen.getByText('Below the minimum price for this item.')).toBeInTheDocument();
  });

  it('renders nothing for a line at or above its floor', () => {
    const { container } = render(
      <MinimumPriceFlag
        quotationId="q1"
        line={line({ product_id: 'p1', unit_price: '400.00' })}
        draft={draftOf({ product_id: 'p1' })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
