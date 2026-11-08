/**
 * PRICETAG-ACCESSORY-DESIGNER S6 follow-up: when the chosen Columns cannot fit at the card's width the grid
 * draws fewer (never overflows); the inspector says so under Columns.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string | null;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
  }) => (
    <select
      aria-label={props['aria-label']}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="" />
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const CARD = {
  width_mm: 30,
  height_mm: 20,
  elements: [{ id: 'name', kind: 'text', field: 'name', x_mm: 1, y_mm: 1, width_mm: 20, height_mm: 5 }],
};

function box(over: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'acc1', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 80, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), ...over },
  } as TagLayer;
}

function mount(layer: TagLayer, accessoryFit?: { count: number; lines: number }) {
  const onUpdateProps = vi.fn();
  render(
    <InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} accessoryFit={accessoryFit} />,
  );
  return onUpdateProps;
}


describe('Columns hint', () => {
  it('says how many columns fit when the card is too wide for the chosen number', () => {
    // box 100 wide, card 60 wide, 4 asked, 4 previewed: at the 70% floor (42) only 2 fit in 97
    mount(box({ columns: 4, card: { ...CARD, width_mm: 60 } }), { count: 4, lines: 2 });
    expect(screen.getByText('Only 2 columns fit at this card width')).toBeInTheDocument();
  });

  it('says nothing when the chosen columns fit', () => {
    mount(box({ columns: 2, card: CARD }), { count: 4, lines: 2 });
    expect(screen.queryByText(/columns fit at this card width/)).toBeNull();
  });

  it('says nothing for Auto or when no number is chosen', () => {
    mount(box({ columns: 'auto', card: { ...CARD, width_mm: 60 } }), { count: 4, lines: 2 });
    expect(screen.queryByText(/fit at this card width/)).toBeNull();
  });

  it('uses the singular for one column', () => {
    mount(box({ columns: 3, card: { ...CARD, width_mm: 90 } }), { count: 3, lines: 2 });
    expect(screen.getByText('Only 1 column fits at this card width')).toBeInTheDocument();
  });
});
