/**
 * PRICETAG-UPGRADE-VARIANTS crew browser pass, fix 2: changing the field must not keep the OLD field's
 * default text before the figure (it printed "SP with upgrade RM 150" on a top-up). Rule, for a text
 * layer's Slot Binding and a card element's "Shows" alike: when the current prefix is empty or still the
 * old field's default, it becomes the new field's default (none when the new field has no default);
 * a prefix the designer typed is kept.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

type Option = { value: string; label: string };
const captured = vi.hoisted(() => ({
  selects: [] as { options: Option[]; onChange?: (v: string) => void }[],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: {
    value?: string | null;
    onChange?: (v: string) => void;
    options?: Option[];
    'aria-label'?: string;
  }) => {
    captured.selects.push({ options: p.options ?? [], onChange: p.onChange });
    return (
      <select aria-label={p['aria-label']} value={p.value ?? ''} onChange={(e) => p.onChange?.(e.target.value)}>
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

import { defaultAccessoriesProps, defaultTextProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const base = {
  x_mm: 0, y_mm: 0, width_mm: 60, height_mm: 40, rotation_deg: 0, z_index: 1, locked: false, visible: true,
  text_override: null,
};

const textLayer = (slot: string | null, props: Record<string, unknown> = {}) =>
  ({ ...base, id: 't1', type: 'text', slot_binding: slot, props: { ...defaultTextProps(), ...props } }) as unknown as TagLayer;

const slotSelect = () => captured.selects.find((s) => s.options.some((o) => o.value === 'upgrade_topup'));

beforeEach(() => {
  captured.selects.length = 0;
});

describe('Text layer: Slot Binding switches the default prefix', () => {
  const pick = (layer: TagLayer, next: string) => {
    const onUpdate = vi.fn();
    render(<InspectorPanel layer={layer} onUpdate={onUpdate} onUpdateProps={vi.fn()} />);
    slotSelect()!.onChange!(next);
    expect(onUpdate).toHaveBeenCalledTimes(1);
    return onUpdate.mock.calls[0][1] as { slot_binding: string; props?: { prefix?: string } };
  };

  it('SP with upgrade -> Upgrade top-up takes the top-up default', () => {
    const patch = pick(textLayer('sell_price_with_upgrade', { prefix: 'SP with upgrade ' }), 'upgrade_topup');
    expect(patch.slot_binding).toBe('upgrade_topup');
    expect(patch.props?.prefix).toBe('TOPUP ');
  });

  it('Upgrade top-up -> SP with upgrade takes the SP default', () => {
    const patch = pick(textLayer('upgrade_topup', { prefix: 'TOPUP ' }), 'sell_price_with_upgrade');
    expect(patch.props?.prefix).toBe('SP with upgrade ');
  });

  it('Upgrade top-up -> Code clears the default prefix', () => {
    const patch = pick(textLayer('upgrade_topup', { prefix: 'TOPUP ' }), 'code');
    expect(patch.props).toBeDefined();
    expect(patch.props!.prefix).toBeUndefined();
  });

  it('an empty prefix takes the new default', () => {
    const patch = pick(textLayer('upgrade_topup', { prefix: '' }), 'sell_price_with_upgrade');
    expect(patch.props?.prefix).toBe('SP with upgrade ');
  });

  it('a typed prefix is kept', () => {
    const patch = pick(textLayer('upgrade_topup', { prefix: 'ADD ' }), 'sell_price_with_upgrade');
    expect(patch.props?.prefix ?? 'ADD ').toBe('ADD ');
  });
});

describe('Card element: Shows switches the default prefix', () => {
  const box = (prefix: string) =>
    ({
      ...base,
      id: 'acc1',
      type: 'accessories',
      slot_binding: null,
      props: {
        ...defaultAccessoriesProps(),
        list: 'upgrades',
        card: {
          width_mm: 71,
          height_mm: 21.5,
          elements: [
            { id: 'tu', kind: 'text', field: 'topup', prefix, x_mm: 17, y_mm: 1, width_mm: 50, height_mm: 4 },
          ],
        },
      },
    }) as unknown as TagLayer;

  const choose = (prefix: string, next: string) => {
    const onUpdateAccessoryElement = vi.fn();
    render(
      <InspectorPanel
        layer={box(prefix)}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        onUpdateAccessoryElement={onUpdateAccessoryElement}
        {...({ accessoryEdit: { layerId: 'acc1', target: 'card', elementId: 'tu' } } as object)}
      />,
    );
    fireEvent.change(screen.getByLabelText('Shows'), { target: { value: next } });
    expect(onUpdateAccessoryElement).toHaveBeenCalledTimes(1);
    return onUpdateAccessoryElement.mock.calls[0][1] as Record<string, unknown>;
  };

  it('Top-up -> SP with upgrade takes the SP default', () => {
    expect(choose('TOPUP ', 'price_with_upgrade').prefix).toBe('SP with upgrade ');
  });

  it('Top-up -> Code clears the default prefix', () => {
    const patch = choose('TOPUP ', 'code');
    expect('prefix' in patch).toBe(true);
    expect(patch.prefix).toBeUndefined();
  });

  it('a typed prefix is kept', () => {
    const patch = choose('ADD ', 'price_with_upgrade');
    expect(patch.prefix ?? 'ADD ').toBe('ADD ');
  });
});
