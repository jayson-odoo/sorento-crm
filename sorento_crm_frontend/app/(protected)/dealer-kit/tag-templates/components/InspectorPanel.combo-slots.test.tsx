/**
 * PRICETAG-COMBO: the Inspector's Field list gains a Combo group (AC-4.1).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The five combo slots are not in the list
 * yet. The existing options must keep their labels and their order.
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

const COMBO_SLOTS = [
  'combo_image',
  'combo_name',
  'combo_description',
  'combo_choices',
  'combo_topups',
];

const EXISTING = [
  ['__none__', '(None)'],
  ['product_image', 'Product Image'],
  // PS-SPEC-SHEET: the technical drawing slot.
  ['drawing', 'Drawing'],
  ['code', 'Code'],
  ['name', 'Name'],
  ['dimensions', 'Dimensions'],
  ['spec_lines', 'Spec Lines'],
  ['included_accessories', 'Accessories'],
  ['list_price', 'List Price'],
  ['sell_price', 'Sell Price'],
  ['badges', 'Badges'],
  ['alternatives', 'Alternatives'],
  ['set_members', 'Set Members'],
  ['barcode', 'Barcode'],
];

describe('Inspector Field list, Combo group (AC-4.1)', () => {
  it('offers the five combo slots in a Combo group', () => {
    const options = fieldOptions();
    const combo = options.filter((option) => COMBO_SLOTS.includes(option.value));
    expect(combo.map((option) => option.value)).toEqual(COMBO_SLOTS);
    expect(combo.every((option) => option.group === 'Combo')).toBe(true);
    expect(combo.every((option) => option.label && !option.label.includes('_'))).toBe(true);
  });

  it('puts the Combo group above the existing options', () => {
    const options = fieldOptions();
    const firstCombo = options.findIndex((option) => option.value === 'combo_image');
    const firstExisting = options.findIndex((option) => option.value === 'product_image');
    expect(firstCombo).toBeGreaterThanOrEqual(0);
    expect(firstCombo).toBeLessThan(firstExisting);
  });

  it('keeps the existing options, labels and order', () => {
    const options = fieldOptions();
    const existing = options
      .filter((option) => !COMBO_SLOTS.includes(option.value))
      .map((option) => [option.value, option.label]);
    expect(existing).toEqual(EXISTING);
  });
});
