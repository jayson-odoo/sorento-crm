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

function textLayer(overrides: Record<string, unknown> = {}): TagLayer {
  return {
    id: 't1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Hello',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
      ...overrides,
    },
  } as TagLayer;
}

describe('InspectorPanel - text B/I/U/S toggle group (S2, AC-S2-5)', () => {
  it('reflects an already-formatted layer as pressed', () => {
    render(
      <InspectorPanel
        layer={textLayer({ fontWeight: 700, italic: true, underline: true, strikethrough: true })}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Bold' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Italic' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Underline' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Strikethrough' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('shows nothing pressed for a plain layer', () => {
    render(
      <InspectorPanel layer={textLayer()} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />,
    );

    expect(screen.getByRole('button', { name: 'Bold' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Italic' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('pressing Bold sets fontWeight to 700', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={textLayer({ fontWeight: 400 })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));

    expect(onUpdateProps).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ fontWeight: 700 }),
    );
  });

  it('unpressing Bold drops fontWeight to 400 (D10)', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={textLayer({ fontWeight: 900 })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));

    expect(onUpdateProps).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ fontWeight: 400 }),
    );
  });

  it('pressing Italic sets the italic flag without touching the others', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={textLayer({ underline: true })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Italic' }));

    expect(onUpdateProps).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ italic: true, underline: true }),
    );
  });

  it('pressing Italic on a 600-weight layer leaves fontWeight at 600, not collapsed to 700', () => {
    // Regression: a `type="multiple"` ToggleGroup reports every currently
    // pressed item (including Bold, since 600 >= 600 reads as pressed) on
    // every click - toggling an unrelated flag must not rewrite the weight.
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={textLayer({ fontWeight: 600 })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Italic' }));

    expect(onUpdateProps).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ fontWeight: 600, italic: true }),
    );
  });

  it('pressing Bold on a 600-weight layer drops it to 400 (D10), since 600 already reads as bold', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={textLayer({ fontWeight: 600 })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));

    expect(onUpdateProps).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ fontWeight: 400 }),
    );
  });
});

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
