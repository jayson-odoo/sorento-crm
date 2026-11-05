/**
 * PRICETAG-COMBO-RENDER K7 / AC-A5: the Product select in the template editor.
 *
 * Written test-FIRST. Today the select only shows when the layer's tag has parts, offers
 * `subjectPart` numbers and cannot write `subjectSlot`.
 *
 * Decisions where the plan is open:
 * - The previewed combo's slots reach the panel as a new prop `subjectSlots` (the same shape as
 *   the preview product's `slots`); absent/null = nothing previewed.
 * - Option values: `slot:main`, `slot:fixed:<i>`, `slot:pick:<g>:<i>`, `slot:upgrade:<i>`.
 * - Generic labels with nothing previewed: "Main product", "Fixed part 1..4",
 *   "Choice group 1..3, pick 1..5", "Upgrade 1..2". Previewed: "<role>, pick n" under the group
 *   `<role>`, with the product code in the label or the description.
 * - A layer with neither subjectSlot nor subjectPart shows `slot:main` in the template editor.
 * - Picking a legacy part value clears `subjectSlot` the same way (the slot would win otherwise).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

type Opt = { value: string; label: string; description?: string; group?: string };
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: Opt[];
  }) => (
    <select data-testid="product-select" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value} data-group={o.group ?? ''}>
          {o.label}
          {o.description ? ` | ${o.description}` : ''}
        </option>
      ))}
    </select>
  ),
}));

import type { TagLayer, TagLayerProps } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const part = (code: string) => ({ product_id: `id-${code}`, code, name: code, dimensions: '' });

const S1 = {
  fixed: [],
  groups: [
    {
      role: 'Kitchen tap',
      size: 5,
      picks: ['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'].map(part),
    },
  ],
  upgrades: [part('SRTKT71SS')],
};
const S2 = { fixed: [part('SRTWT7449-BL')], groups: [], upgrades: [] };
const S3 = {
  fixed: [],
  groups: [{ role: 'Tap colour', size: 2, picks: [part('SRTWT7449-BL'), part('SRTWT7449-RG')] }],
  upgrades: [],
};
const S4 = { fixed: [part('SRTMCB8083-BL'), part('SRTWT6203-GM')], groups: [], upgrades: [] };

function baseLayer(props: Record<string, unknown> = {}, overrides: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 'l1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: 'code',
    text_override: null,
    props: { kind: 'text', text: 'Code', ...props } as TagLayerProps,
    ...overrides,
  } as TagLayer;
}

function renderEditor(layer: TagLayer, slots?: unknown) {
  const onUpdateProps = vi.fn();
  const Panel = InspectorPanel as unknown as React.ComponentType<Record<string, unknown>>;
  render(<Panel layer={layer} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} subjectSlots={slots} />);
  return { onUpdateProps };
}

/** The select inside the "Product" section (other sections mount selects of their own). */
const productSelect = () => {
  const section = screen.getByRole('heading', { level: 4, name: 'Product' }).closest('section')!;
  return section.querySelector('select') as HTMLSelectElement;
};
const optionValues = () =>
  [...productSelect().querySelectorAll('option')].map((o) => o.getAttribute('value'));
const optionByValue = (value: string) =>
  [...productSelect().querySelectorAll('option')].find(
    (o) => o.getAttribute('value') === value,
  )!;

describe('the template editor with nothing previewed', () => {
  it('shows the Product select with no parts and no combo', () => {
    renderEditor(baseLayer());
    expect(screen.getByRole('heading', { level: 4, name: 'Product' })).toBeInTheDocument();
  });

  it('lists the generic positions', () => {
    renderEditor(baseLayer());
    const values = optionValues();
    expect(values).toContain('slot:main');
    for (let i = 0; i < 4; i += 1) expect(values).toContain(`slot:fixed:${i}`);
    expect(values).not.toContain('slot:fixed:4');
    for (let g = 0; g < 3; g += 1) {
      for (let i = 0; i < 5; i += 1) expect(values).toContain(`slot:pick:${g}:${i}`);
    }
    expect(values).not.toContain('slot:pick:3:0');
    expect(values).not.toContain('slot:pick:0:5');
    for (let i = 0; i < 2; i += 1) expect(values).toContain(`slot:upgrade:${i}`);
    expect(values).not.toContain('slot:upgrade:2');
  });

  it('names them generically', () => {
    renderEditor(baseLayer());
    expect(optionByValue('slot:main').textContent).toBe('Main product');
    expect(optionByValue('slot:fixed:1').textContent).toBe('Fixed part 2');
    expect(optionByValue('slot:pick:0:1').textContent).toBe('Choice group 1, pick 2');
    expect(optionByValue('slot:pick:2:4').textContent).toBe('Choice group 3, pick 5');
    expect(optionByValue('slot:upgrade:0').textContent).toBe('Upgrade 1');
  });

  it('shows the layer position as the current value', () => {
    renderEditor(baseLayer({ subjectSlot: { kind: 'pick', group: 1, index: 2 } }));
    expect(productSelect().value).toBe('slot:pick:1:2');
  });

  it('a layer with no position reads as the main product', () => {
    renderEditor(baseLayer());
    expect(productSelect().value).toBe('slot:main');
  });

  it('choosing a position writes subjectSlot and clears subjectPart', () => {
    const { onUpdateProps } = renderEditor(baseLayer({ subjectPart: 1 }));
    fireEvent.change(productSelect(), { target: { value: 'slot:pick:0:1' } });
    expect(onUpdateProps).toHaveBeenCalledTimes(1);
    const arg = onUpdateProps.mock.calls[0][1];
    expect(arg.subjectSlot).toEqual({ kind: 'pick', group: 0, index: 1 });
    expect('subjectPart' in arg).toBe(true);
    expect(arg.subjectPart).toBeUndefined();
  });

  it.each([
    ['slot:main', { kind: 'main' }],
    ['slot:fixed:2', { kind: 'fixed', index: 2 }],
    ['slot:upgrade:1', { kind: 'upgrade', index: 1 }],
  ])('%s writes %j', (value, slot) => {
    const { onUpdateProps } = renderEditor(baseLayer());
    fireEvent.change(productSelect(), { target: { value } });
    expect(onUpdateProps.mock.calls[0][1].subjectSlot).toEqual(slot);
  });

  it('no Product select on a layer that reads no product data', () => {
    const shape = baseLayer(
      { kind: 'shape', shape: 'rect' },
      { type: 'shape', slot_binding: null } as Partial<TagLayer>,
    );
    renderEditor(shape);
    expect(screen.queryByRole('heading', { level: 4, name: 'Product' })).toBeNull();
  });
});

describe('the template editor with a combo previewed', () => {
  it('S1: lists the combo own positions, grouped, with codes', () => {
    renderEditor(baseLayer(), S1);
    expect(optionValues()).toEqual([
      'slot:main',
      'slot:pick:0:0',
      'slot:pick:0:1',
      'slot:pick:0:2',
      'slot:pick:0:3',
      'slot:pick:0:4',
      'slot:upgrade:0',
    ]);
    const second = optionByValue('slot:pick:0:1');
    expect(second.textContent).toContain('Kitchen tap, pick 2');
    expect(second.textContent).toContain('SRTKT1863SS');
    expect(second.getAttribute('data-group')).toBe('Kitchen tap');
    expect(optionByValue('slot:upgrade:0').textContent).toContain('SRTKT71SS');
  });

  it('S2: one fixed part', () => {
    renderEditor(baseLayer(), S2);
    expect(optionValues()).toEqual(['slot:main', 'slot:fixed:0']);
    expect(optionByValue('slot:fixed:0').textContent).toContain('Fixed part 1');
    expect(optionByValue('slot:fixed:0').textContent).toContain('SRTWT7449-BL');
  });

  it('S3: two finishes', () => {
    renderEditor(baseLayer(), S3);
    expect(optionValues()).toEqual(['slot:main', 'slot:pick:0:0', 'slot:pick:0:1']);
    expect(optionByValue('slot:pick:0:1').textContent).toContain('Tap colour, pick 2');
    expect(optionByValue('slot:pick:0:1').textContent).toContain('SRTWT7449-RG');
  });

  it('S4: two fixed parts and nothing to pick', () => {
    renderEditor(baseLayer(), S4);
    expect(optionValues()).toEqual(['slot:main', 'slot:fixed:0', 'slot:fixed:1']);
    expect(optionByValue('slot:fixed:1').textContent).toContain('SRTWT6203-GM');
  });

  it('choosing a previewed position writes the same subjectSlot', () => {
    const { onUpdateProps } = renderEditor(baseLayer(), S1);
    fireEvent.change(productSelect(), { target: { value: 'slot:pick:0:3' } });
    expect(onUpdateProps.mock.calls[0][1].subjectSlot).toEqual({ kind: 'pick', group: 0, index: 3 });
  });
});

describe('the request designer (a line with parts) is not changed', () => {
  it('a legacy part value writes subjectPart and clears subjectSlot', () => {
    const onUpdateProps = vi.fn();
    const Panel = InspectorPanel as unknown as React.ComponentType<Record<string, unknown>>;
    render(
      <Panel
        layer={baseLayer({ subjectSlot: { kind: 'main' } })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
        subjectParts={[{ code: 'SRTOLD1', name: 'Old', dimensions: '' }]}
        subjectParentCode="SRTHOST01"
      />,
    );
    const values = optionValues();
    expect(values).toContain('-1');
    expect(values).toContain('0');
    fireEvent.change(productSelect(), { target: { value: '0' } });
    const arg = onUpdateProps.mock.calls[0][1];
    expect(arg.subjectPart).toBe(0);
    expect('subjectSlot' in arg).toBe(true);
    expect(arg.subjectSlot).toBeUndefined();
  });
});
