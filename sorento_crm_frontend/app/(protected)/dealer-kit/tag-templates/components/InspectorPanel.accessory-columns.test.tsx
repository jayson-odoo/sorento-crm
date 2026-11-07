/**
 * PRICETAG-ACCESSORY-DESIGNER S6: the box inspector's "Columns" select (Auto, 1, 2, 3, 4).
 * Plan: "S6 Layout flexibility / Columns". Written test-FIRST.
 *
 * Invented: a SearchableSelect with aria-label "Columns" and options labelled Auto, 1, 2, 3, 4 (values
 * 'auto', '1'..'4'); choosing one calls onUpdateProps(layerId, { columns: 'auto' | 1 | 2 | 3 | 4 }) with
 * a NUMBER for 1-4. On a box with no `card` the same patch also carries the card built by
 * `cardFromLegacy` (`card: { width_mm, height_mm, elements: [...] }`), as Edit card does.
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

function mount(layer: TagLayer) {
  const onUpdateProps = vi.fn();
  render(<InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
  return onUpdateProps;
}

const optionLabels = () =>
  Array.from(screen.getByLabelText('Columns').querySelectorAll('option'))
    .map((o) => o.textContent ?? '')
    .filter(Boolean);

describe('Inspector, accessories box Columns', () => {
  it('offers Auto, 1, 2, 3 and 4', () => {
    mount(box({ card: CARD }));
    expect(optionLabels()).toEqual(['Auto', '1', '2', '3', '4']);
  });

  it('choosing 4 sets columns: 4 (a number)', () => {
    const onUpdateProps = mount(box({ card: CARD }));
    fireEvent.change(screen.getByLabelText('Columns'), { target: { value: '4' } });
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ columns: 4 }));
  });

  it('choosing Auto sets columns: auto', () => {
    const onUpdateProps = mount(box({ card: CARD }));
    fireEvent.change(screen.getByLabelText('Columns'), { target: { value: 'auto' } });
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ columns: 'auto' }));
  });

  it('shows the current choice', () => {
    mount(box({ card: CARD, columns: 3 }));
    expect((screen.getByLabelText('Columns') as HTMLSelectElement).value).toBe('3');
  });

  it('a box without a card is converted when a column count is chosen', () => {
    const onUpdateProps = mount(box());
    fireEvent.change(screen.getByLabelText('Columns'), { target: { value: '2' } });
    expect(onUpdateProps).toHaveBeenCalledWith(
      'acc1',
      expect.objectContaining({
        columns: 2,
        card: expect.objectContaining({ elements: expect.any(Array) }),
      }),
    );
    const patch = onUpdateProps.mock.calls[0][1] as { card: { elements: { field?: string }[] } };
    expect(patch.card.elements.map((e) => e.field)).toEqual(expect.arrayContaining(['picture', 'name']));
  });

  it('a box that already has a card keeps it untouched', () => {
    const onUpdateProps = mount(box({ card: CARD }));
    fireEvent.change(screen.getByLabelText('Columns'), { target: { value: '2' } });
    const patch = onUpdateProps.mock.calls[0][1] as { card?: unknown };
    expect(patch.card).toBeUndefined();
  });
});
