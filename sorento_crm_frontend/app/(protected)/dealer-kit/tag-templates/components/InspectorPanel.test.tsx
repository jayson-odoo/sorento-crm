/**
 * The barcode inspector's value override + Relink (D23, S9 review S7).
 *
 * Mirrors the text layer's `text_override` pattern one-for-one: typing sets
 * the override, Relink is offered only while one exists and clears it back
 * to the bound value, and clearing the field by hand writes `null` (no
 * override, fall back to the bound barcode) rather than an empty string
 * (which would otherwise read as "this product's barcode IS blank").
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

function barcodeLayer(overrides: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 'bc1',
    type: 'barcode',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 22,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: 'barcode',
    text_override: null,
    props: { kind: 'barcode', show_code: true },
    ...overrides,
  } as TagLayer;
}

describe('InspectorPanel - barcode value override (D23, S9 review S7)', () => {
  it('typing into the barcode value field writes text_override', () => {
    const onUpdate = vi.fn();
    render(
      <InspectorPanel
        layer={barcodeLayer()}
        onUpdate={onUpdate}
        onUpdateProps={vi.fn()}
        resolvedText="4006381333931"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('4006381333931'), {
      target: { value: '111222333' },
    });

    expect(onUpdate).toHaveBeenCalledWith('bc1', { text_override: '111222333' });
  });

  it('offers Relink only while overridden, not on a plain bound layer', () => {
    const { rerender } = render(
      <InspectorPanel
        layer={barcodeLayer()}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        resolvedText="4006381333931"
      />,
    );
    expect(screen.queryByRole('button', { name: /relink/i })).not.toBeInTheDocument();

    rerender(
      <InspectorPanel
        layer={barcodeLayer({ text_override: '111222333' })}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        resolvedText="4006381333931"
      />,
    );
    expect(screen.getByRole('button', { name: /relink/i })).toBeInTheDocument();
  });

  it('Relink clears the override back to null, so it falls back to the bound barcode', () => {
    const onUpdate = vi.fn();
    render(
      <InspectorPanel
        layer={barcodeLayer({ text_override: '111222333' })}
        onUpdate={onUpdate}
        onUpdateProps={vi.fn()}
        resolvedText="4006381333931"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /relink/i }));

    expect(onUpdate).toHaveBeenCalledWith('bc1', { text_override: null });
  });

  it('shows the resolved (bound) value while unoverridden', () => {
    render(
      <InspectorPanel
        layer={barcodeLayer()}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        resolvedText="4006381333931"
      />,
    );

    expect(screen.getByDisplayValue('4006381333931')).toBeInTheDocument();
  });

  it('clearing the field by hand writes null, not an empty string', () => {
    const onUpdate = vi.fn();
    render(
      <InspectorPanel
        layer={barcodeLayer({ text_override: '111222333' })}
        onUpdate={onUpdate}
        onUpdateProps={vi.fn()}
        resolvedText="4006381333931"
      />,
    );

    fireEvent.change(screen.getByDisplayValue('111222333'), { target: { value: '' } });

    expect(onUpdate).toHaveBeenCalledWith('bc1', { text_override: null });
  });
});
