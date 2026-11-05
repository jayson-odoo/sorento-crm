/**
 * PRICETAG-DESIGNER-GAPS item 3: the Feature icons inspector edits icon size, spacing and
 * alignment, each written through onUpdateProps with the rest of the props kept.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

function iconsLayer(props: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'fi1',
    type: 'feature_icons',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'left', order: ['a1'], ...props },
  } as unknown as TagLayer;
}

function mount(props: Record<string, unknown> = {}) {
  const onUpdateProps = vi.fn();
  render(<InspectorPanel layer={iconsLayer(props)} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
  return onUpdateProps;
}

describe('Inspector feature icons', () => {
  it('shows the current icon size and spacing', () => {
    mount();
    expect(screen.getByLabelText(/icon size/i)).toHaveValue(8);
    expect(screen.getByLabelText(/spacing/i)).toHaveValue(1.5);
  });

  it('writes a new icon size and keeps the other props', () => {
    const onUpdateProps = mount();
    fireEvent.change(screen.getByLabelText(/icon size/i), { target: { value: '12' } });
    expect(onUpdateProps).toHaveBeenCalledWith(
      'fi1',
      expect.objectContaining({ kind: 'feature_icons', iconSize_mm: 12, gap_mm: 1.5, order: ['a1'] }),
    );
  });

  it('writes a new spacing', () => {
    const onUpdateProps = mount();
    fireEvent.change(screen.getByLabelText(/spacing/i), { target: { value: '3' } });
    expect(onUpdateProps).toHaveBeenCalledWith(
      'fi1',
      expect.objectContaining({ gap_mm: 3, iconSize_mm: 8 }),
    );
  });

  it('writes centre and right alignment', () => {
    const onUpdateProps = mount();
    fireEvent.click(screen.getByRole('button', { name: /^(centre|center)$/i }));
    expect(onUpdateProps).toHaveBeenLastCalledWith('fi1', expect.objectContaining({ align: 'center' }));
    fireEvent.click(screen.getByRole('button', { name: /^right$/i }));
    expect(onUpdateProps).toHaveBeenLastCalledWith('fi1', expect.objectContaining({ align: 'right' }));
  });
});
