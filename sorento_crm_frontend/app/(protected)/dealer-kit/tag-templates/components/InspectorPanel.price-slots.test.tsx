/**
 * PRICETAG-LPSP S6, AC-18: the Inspector's Field list offers the two new price slots.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). Neither "Price (LP or SP)" nor "Price label" is in
 * the list yet. The existing price options keep their labels (Q1: no template is converted).
 */

import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

type Option = { value: string; label: string; group?: string };
const captured = vi.hoisted(() => ({ lists: [] as unknown[][] }));

// The real select is a Radix popover jsdom cannot open: record the options each
// select is given instead.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ options }: { options?: Option[] }) => {
    captured.lists.push(options ?? []);
    return <div data-testid="select" />;
  },
}));

function textLayer(): TagLayer {
  return {
    id: 't1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Hello',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
    },
  } as TagLayer;
}

function fieldOptions(): Option[] {
  captured.lists.length = 0;
  render(<InspectorPanel layer={textLayer()} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
  const list = (captured.lists as Option[][]).find((options) =>
    options.some((option) => option.value === '__none__'),
  );
  expect(list, 'the slot binding select was not rendered').toBeDefined();
  return list as Option[];
}

describe('Inspector Field list, price slots (AC-18)', () => {
  it('offers "Price (LP or SP)" bound to price and "Price label" bound to price_label', () => {
    const options = fieldOptions();
    expect(options.find((option) => option.value === 'price')?.label).toBe('Price (LP or SP)');
    expect(options.find((option) => option.value === 'price_label')?.label).toBe('Price label');
  });

  it('keeps List Price and Sell Price as they were', () => {
    const options = fieldOptions();
    expect(options.find((option) => option.value === 'list_price')?.label).toBe('List Price');
    expect(options.find((option) => option.value === 'sell_price')?.label).toBe('Sell Price');
  });

  it('shows no raw key as a label', () => {
    const options = fieldOptions();
    const added = options.filter((option) => ['price', 'price_label'].includes(option.value));
    expect(added).toHaveLength(2);
    expect(added.every((option) => option.label && !option.label.includes('_'))).toBe(true);
  });
});
