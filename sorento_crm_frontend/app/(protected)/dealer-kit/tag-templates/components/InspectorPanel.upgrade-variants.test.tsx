/**
 * PRICETAG-UPGRADE-VARIANTS FE test 8: the Inspector.
 *  - Accessories box: "List" segmented control (Free items | Upgrades); Upgrades seeds the default
 *    upgrade card and the "UPGRADE" header in ONE onUpdateProps call (one undo step), keeps an own
 *    card and an own header, and names its source.
 *  - Card element: "Shows" offers Top-up and SP with upgrade; "Text before the figure" edits `prefix`.
 *  - Feature icons layer: the Product select offers "All variants" (value `slot:variants`).
 *
 * Written test-FIRST. Chosen: the List control is a ToggleGroup of radios named "Free items" and
 * "Upgrades"; the prefix input is labelled "Text before the figure" and calls
 * onUpdateAccessoryElement(elementId, { prefix }).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

type Option = { value: string; label: string };
const captured = vi.hoisted(() => ({
  selects: [] as { options: Option[]; value?: string; onChange?: (v: string) => void }[],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: {
    value?: string | null;
    onChange?: (v: string) => void;
    options?: Option[];
    'aria-label'?: string;
    id?: string;
  }) => {
    captured.selects.push({ options: p.options ?? [], value: p.value ?? undefined, onChange: p.onChange });
    return (
      <select
        aria-label={p['aria-label']}
        id={p.id}
        value={p.value ?? ''}
        onChange={(e) => p.onChange?.(e.target.value)}
      >
        <option value="" />
        {(p.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import {
  defaultAccessoriesProps,
  type TagLayer,
  type TagSlots,
} from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const base = {
  x_mm: 0, y_mm: 0, width_mm: 60, height_mm: 40, rotation_deg: 0, z_index: 1, locked: false, visible: true,
  slot_binding: null, text_override: null,
};

const box = (over: Record<string, unknown> = {}) =>
  ({ ...base, id: 'acc1', type: 'accessories', props: { ...defaultAccessoriesProps(), ...over } }) as unknown as TagLayer;

const iconsLayer = () =>
  ({
    ...base, id: 'fi1', type: 'feature_icons',
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'left' },
  }) as unknown as TagLayer;

const slots: TagSlots = {
  main: { code: 'SRTWC8354-SH', name: 'WC', dimensions: '' },
  fixed: [],
  groups: [],
  upgrades: [],
};

beforeEach(() => {
  captured.selects.length = 0;
});

describe('Accessories box: List', () => {
  it('offers Free items and Upgrades, Free items selected by default', () => {
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(screen.getByRole('radio', { name: 'Free items' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Upgrades' })).not.toBeChecked();
  });

  it('switching to Upgrades on a box with no card seeds the default card and the UPGRADE header in one update', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Upgrades' }));
    expect(onUpdateProps).toHaveBeenCalledTimes(1);
    const [id, patch] = onUpdateProps.mock.calls[0] as [string, Record<string, unknown>];
    expect(id).toBe('acc1');
    expect(patch).toMatchObject({ list: 'upgrades', headerText: 'UPGRADE' });
    const card = patch.card as { width_mm: number; height_mm: number; elements: { field?: string; kind: string }[] };
    expect([card.width_mm, card.height_mm]).toEqual([71, 21.5]);
    expect(card.elements.some((e) => e.field === 'topup')).toBe(true);
    expect(card.elements.some((e) => e.kind === 'feature_icons')).toBe(true);
    expect(card.elements.some((e) => e.field === 'price_with_upgrade')).toBe(false);
  });

  it('keeps a header the designer already changed', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box({ headerText: 'EXTRA' })} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Upgrades' }));
    const patch = onUpdateProps.mock.calls[0][1] as Record<string, unknown>;
    expect(patch.list).toBe('upgrades');
    expect(patch.headerText === undefined || patch.headerText === 'EXTRA').toBe(true);
  });

  it('keeps a card the box already has', () => {
    const own = { width_mm: 40, height_mm: 30, elements: [{ id: 'n', kind: 'text', field: 'name', x_mm: 0, y_mm: 0, width_mm: 20, height_mm: 5 }] };
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box({ card: own })} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Upgrades' }));
    const patch = onUpdateProps.mock.calls[0][1] as Record<string, unknown>;
    expect(patch.list).toBe('upgrades');
    expect(patch.card === undefined || patch.card === own).toBe(true);
  });

  it('switching back to Free items writes the free list', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box({ list: 'upgrades' })} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    expect(screen.getByRole('radio', { name: 'Upgrades' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: 'Free items' }));
    const patch = onUpdateProps.mock.calls[0][1] as Record<string, unknown>;
    expect(patch.list === 'free' || patch.list === undefined).toBe(true);
    expect('list' in patch).toBe(true);
  });

  it("names its source on an Upgrades box: this combo's upgrade parts", () => {
    render(<InspectorPanel layer={box({ list: 'upgrades' })} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(screen.getByText(/this combo's upgrade parts/i)).toBeInTheDocument();
    expect(screen.getByText(/product page > Combos/i)).toBeInTheDocument();
  });

  it('a Free items box shows no source note', () => {
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(screen.queryByText(/upgrade parts/i)).toBeNull();
  });
});

describe('Card element: Shows and the text before the figure', () => {
  const CARD = {
    width_mm: 71, height_mm: 21.5,
    elements: [
      { id: 'tu', kind: 'text', field: 'topup', prefix: 'TOPUP ', x_mm: 17, y_mm: 1, width_mm: 50, height_mm: 4 },
      { id: 'nm', kind: 'text', field: 'name', x_mm: 17, y_mm: 9, width_mm: 50, height_mm: 4 },
    ],
  };
  const edit = (elementId: string) => ({ accessoryEdit: { layerId: 'acc1', target: 'card', elementId } });
  const mount = (elementId: string) => {
    const onUpdateAccessoryElement = vi.fn();
    render(
      <InspectorPanel
        layer={box({ list: 'upgrades', card: CARD })}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        onUpdateAccessoryElement={onUpdateAccessoryElement}
        {...(edit(elementId) as object)}
      />,
    );
    return onUpdateAccessoryElement;
  };
  const labels = () =>
    Array.from(screen.getByLabelText('Shows').querySelectorAll('option')).map((o) => o.textContent ?? '').filter(Boolean);

  it('Shows lists Top-up and SP with upgrade beside the existing fields', () => {
    mount('tu');
    const shown = labels();
    for (const wanted of ['Name', 'Code', 'Price', 'Top-up', 'SP with upgrade']) expect(shown).toContain(wanted);
  });

  it('choosing SP with upgrade patches the field', () => {
    const onUpdate = mount('nm');
    fireEvent.change(screen.getByLabelText('Shows'), { target: { value: 'price_with_upgrade' } });
    expect(onUpdate).toHaveBeenCalledWith('nm', expect.objectContaining({ field: 'price_with_upgrade' }));
  });

  it('choosing SP with upgrade defaults the text before the figure', () => {
    const onUpdate = mount('nm');
    fireEvent.change(screen.getByLabelText('Shows'), { target: { value: 'price_with_upgrade' } });
    expect(onUpdate).toHaveBeenCalledWith('nm', expect.objectContaining({ prefix: 'SP with upgrade ' }));
  });

  it('Text before the figure shows the prefix and edits it', () => {
    const onUpdate = mount('tu');
    const input = screen.getByLabelText('Text before the figure');
    expect(input).toHaveValue('TOPUP ');
    fireEvent.change(input, { target: { value: 'ADD ' } });
    expect(onUpdate).toHaveBeenCalledWith('tu', expect.objectContaining({ prefix: 'ADD ' }));
  });
});

describe('Feature icons layer: Product select', () => {
  const productSelect = () => captured.selects.find((s) => s.options.some((o) => o.value === 'slot:main'));

  it('offers All variants after the combo positions', () => {
    render(<InspectorPanel layer={iconsLayer()} onUpdate={vi.fn()} onUpdateProps={vi.fn()} subjectSlots={slots} />);
    const select = productSelect();
    expect(select).toBeDefined();
    expect(select!.options.find((o) => o.value === 'slot:variants')?.label).toBe('All variants');
  });

  it('picking it writes subjectSlot variants', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={iconsLayer()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} subjectSlots={slots} />);
    productSelect()!.onChange!('slot:variants');
    expect(onUpdateProps).toHaveBeenCalledWith(
      'fi1',
      expect.objectContaining({ subjectSlot: { kind: 'variants' } }),
    );
  });

  it('shows it selected when the layer already reads All variants', () => {
    const layer = iconsLayer();
    (layer.props as unknown as Record<string, unknown>).subjectSlot = { kind: 'variants' };
    render(<InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={vi.fn()} subjectSlots={slots} />);
    expect(productSelect()!.value).toBe('slot:variants');
  });

  it('is offered on a feature icons layer only, not on an accessories box', () => {
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={vi.fn()} subjectSlots={slots} />);
    const all = captured.selects.flatMap((s) => s.options);
    expect(all.some((o) => o.value === 'slot:variants')).toBe(false);
  });
});
