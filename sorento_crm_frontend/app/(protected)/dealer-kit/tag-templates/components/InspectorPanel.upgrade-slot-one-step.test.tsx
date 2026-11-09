/**
 * PRICETAG-UPGRADE-VARIANTS review fix round 1, item 9: picking "Upgrade top-up" on a text layer
 * sets the binding and the default text before the figure in ONE onUpdate call (one undo step).
 */
import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

type Option = { value: string; label: string };
const captured = vi.hoisted(() => ({
  selects: [] as { options: Option[]; onChange?: (v: string) => void }[],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: { onChange?: (v: string) => void; options?: Option[] }) => {
    captured.selects.push({ options: p.options ?? [], onChange: p.onChange });
    return <div />;
  },
}));

import { defaultTextProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const textLayer = (props: Record<string, unknown> = {}) =>
  ({
    id: 't1', type: 'text', x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 8, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultTextProps(), ...props },
  }) as unknown as TagLayer;

const slotSelect = () => captured.selects.find((s) => s.options.some((o) => o.value === 'upgrade_topup'));

beforeEach(() => {
  captured.selects.length = 0;
});

describe('Slot Binding: an upgrade figure', () => {
  it('binds and seeds the prefix in one update, nothing through onUpdateProps', () => {
    const onUpdate = vi.fn();
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={textLayer()} onUpdate={onUpdate} onUpdateProps={onUpdateProps} />);
    slotSelect()!.onChange!('upgrade_topup');
    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdateProps).not.toHaveBeenCalled();
    const [id, patch] = onUpdate.mock.calls[0] as [string, { slot_binding: string; props: { prefix: string } }];
    expect(id).toBe('t1');
    expect(patch.slot_binding).toBe('upgrade_topup');
    expect(patch.props.prefix).toBe('TOPUP ');
  });

  it('keeps a prefix the layer already has', () => {
    const onUpdate = vi.fn();
    render(<InspectorPanel layer={textLayer({ prefix: 'ADD ' })} onUpdate={onUpdate} onUpdateProps={vi.fn()} />);
    slotSelect()!.onChange!('sell_price_with_upgrade');
    expect(onUpdate).toHaveBeenCalledWith('t1', { slot_binding: 'sell_price_with_upgrade' });
  });

  it('any other slot is the binding alone', () => {
    const onUpdate = vi.fn();
    render(<InspectorPanel layer={textLayer()} onUpdate={onUpdate} onUpdateProps={vi.fn()} />);
    slotSelect()!.onChange!('code');
    expect(onUpdate).toHaveBeenCalledWith('t1', { slot_binding: 'code' });
  });
});
