/**
 * PRICETAG-HEADER-DRAG round 2: with the box's header selected, the Inspector shows the header as an
 * element, built from the shared sections a text layer uses (TypographyControls, ColorPicker,
 * NumberInput, SidesInput): text, font / size / weight / colour / alignment, background (Transparent
 * = none), corner radius, padding, X / Y / W / H, and Reset. Box sections are not shown meanwhile.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const RECT = { x_mm: 3, y_mm: 1, width_mm: 12, height_mm: 4.5 };

function box(extra: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'acc1', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 45, height_mm: 40, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), headerText: 'FREE', ...extra },
  } as TagLayer;
}

const lastCall = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.at(-1)![1] as Record<string, unknown>;

function mount(layer: TagLayer, onUpdateProps = vi.fn()) {
  render(
    <InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} accessoryHeaderSelected={RECT} />,
  );
  return onUpdateProps;
}

describe('Inspector with the accessories header selected', () => {
  it('shows the header element controls and hides the box sections', () => {
    mount(box());
    expect(screen.getByText('Header')).toBeInTheDocument();
    expect(screen.getByLabelText('Header text')).toHaveValue('FREE');
    expect(screen.getByText('Font Family')).toBeInTheDocument();
    expect(screen.getByText('Background')).toBeInTheDocument();
    expect(screen.getByLabelText('Corner Radius')).toBeInTheDocument();
    expect(screen.getByLabelText('W (mm)')).toBeInTheDocument();
    expect(screen.getByText('Padding (mm)')).toBeInTheDocument();
    expect(screen.queryByText('Edit card')).toBeNull();
    expect(screen.queryByText('Direction')).toBeNull();
  });

  it('corner radius writes headerRadius_mm', () => {
    const fn = mount(box());
    fireEvent.change(screen.getByLabelText('Corner Radius'), { target: { value: '2' } });
    fireEvent.blur(screen.getByLabelText('Corner Radius'));
    expect(lastCall(fn).headerRadius_mm).toBe(2);
  });

  it('a width typed on an unpinned header pins it at its drawn spot with the new size', () => {
    const fn = mount(box());
    fireEvent.change(screen.getByLabelText('W (mm)'), { target: { value: '20' } });
    fireEvent.blur(screen.getByLabelText('W (mm)'));
    const sent = lastCall(fn);
    expect(sent.headerPos).toEqual({ x_mm: 3, y_mm: 1 });
    expect(sent.headerSize).toEqual({ width_mm: 20, height_mm: 4.5 });
  });

  it('padding on an unpinned header pins it too (a padded band is a sized band)', () => {
    const fn = mount(box());
    fireEvent.change(screen.getByLabelText('Left'), { target: { value: '1' } });
    fireEvent.blur(screen.getByLabelText('Left'));
    const sent = lastCall(fn);
    expect(sent.headerPadding).toEqual({ top: 0, right: 0, bottom: 0, left: 1 });
    expect(sent.headerPos).toEqual({ x_mm: 3, y_mm: 1 });
    expect(sent.headerSize).toEqual({ width_mm: 12, height_mm: 4.5 });
  });

  it('Reset header sends the reset patch (position, size and style back to the default look)', () => {
    const fn = mount(box({ headerPos: { x_mm: 1, y_mm: 1 }, headerFill: '#000000', headerFontSize: 20 }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset header' }));
    const sent = lastCall(fn);
    expect('headerPos' in sent && sent.headerPos === undefined).toBe(true);
    expect('headerFill' in sent && sent.headerFill === undefined).toBe(true);
    expect(sent.headerFontSize).toBe(defaultAccessoriesProps().headerFontSize);
  });
});
