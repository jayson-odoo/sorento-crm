/**
 * PRICETAG-ACCESSORIES review B1 (card rule A4): an "Accessories" box picks which product's list it
 * reads. Its default is the TAG's own list (the combo's on a combo tag), never "Main product".
 */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

type Option = { value: string; label: string };
const captured = vi.hoisted(() => ({
  selects: [] as { options: Option[]; value?: string; onChange?: (v: string) => void }[],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: { options?: Option[]; value?: string; onChange?: (v: string) => void }) => {
    captured.selects.push({ options: p.options ?? [], value: p.value, onChange: p.onChange });
    return <div data-testid="select" />;
  },
}));

import { defaultAccessoriesProps, type TagLayer, type TagSlots } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const layer = {
  id: 'acc1',
  type: 'accessories',
  x_mm: 0,
  y_mm: 0,
  width_mm: 45,
  height_mm: 40,
  rotation_deg: 0,
  z_index: 1,
  locked: false,
  visible: true,
  slot_binding: null,
  text_override: null,
  props: defaultAccessoriesProps(),
} as TagLayer;

const slots: TagSlots = {
  main: { code: 'SRTKS7061-BL', name: 'SRTKS7061-BL', dimensions: '' },
  fixed: [{ code: 'SRTKT1632SS', name: 'SRTKT1632SS', dimensions: '' }],
  groups: [],
  upgrades: [],
};

function subjectSelect() {
  return captured.selects.find((s) => s.options.some((o) => o.value === 'slot:main'));
}

describe('Accessories box: which list it reads', () => {
  it('offers "This tag\'s list" first and selects it by default', () => {
    captured.selects.length = 0;
    render(<InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={vi.fn()} subjectSlots={slots} />);
    const select = subjectSelect();
    expect(select).toBeDefined();
    expect(select!.options[0]).toEqual({ value: 'default', label: "This tag's list" });
    expect(select!.value).toBe('default');
  });

  it('picking a combo position writes that position', () => {
    captured.selects.length = 0;
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} subjectSlots={slots} />);
    subjectSelect()!.onChange!('slot:fixed:0');
    expect(onUpdateProps).toHaveBeenCalledWith(
      'acc1',
      expect.objectContaining({ subjectSlot: { kind: 'fixed', index: 0 }, subjectPart: undefined }),
    );
  });

  it('picking the default clears any position', () => {
    captured.selects.length = 0;
    const onUpdateProps = vi.fn();
    const pointed = { ...layer, props: { ...layer.props, subjectSlot: { kind: 'fixed', index: 0 } } } as TagLayer;
    render(<InspectorPanel layer={pointed} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} subjectSlots={slots} />);
    subjectSelect()!.onChange!('default');
    expect(onUpdateProps).toHaveBeenCalledWith(
      'acc1',
      expect.objectContaining({ subjectSlot: undefined, subjectPart: undefined }),
    );
  });
});
