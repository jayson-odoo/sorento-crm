/**
 * `TagSizeControl` (S1, PLAN D1) - lifted out of `RequestTagDesigner.tsx`
 * so the template editor can show the same control (AC-S1-1). The request
 * designer's OWN "Template sizes"/"Saved sizes" grouping, delete-x and
 * "Save as size" coverage lives in `RequestTagDesigner.test.tsx` (that
 * suite already exercises this component end-to-end through the request
 * designer's react-query wiring); this file is the component in isolation
 * - preset pick, custom W/H commit, the floor clamp, and what disappears
 * when a caller (the template editor) hands it fewer props.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TagSizeControl } from './TagSizeControl';
import type { TagSizePreset } from '@/lib/dealer-kit/request-tags';

const PRESETS: TagSizePreset[] = [
  { label: 'Ala carte (60 x 40 mm)', width_mm: 60, height_mm: 40 },
  { label: 'Sink combo (95 x 44.5 mm)', width_mm: 95, height_mm: 44.5 },
];

describe('TagSizeControl - preset pick (AC-S1-1)', () => {
  it('picking a preset from the dropdown resizes to its exact size', async () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={onResize} />,
    );

    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /Sink combo/ }));

    expect(onResize).toHaveBeenCalledWith(95, 44.5);
  });

  it('shows the current size\'s own preset selected, not "Custom"', () => {
    render(
      <TagSizeControl width_mm={95} height_mm={44.5} presets={PRESETS} onResize={vi.fn()} />,
    );

    expect(screen.getByRole('combobox')).toHaveTextContent('Sink combo');
  });

  it('falls through to the "Custom" placeholder once the size matches no preset', () => {
    render(
      <TagSizeControl width_mm={70} height_mm={30} presets={PRESETS} onResize={vi.fn()} />,
    );

    expect(screen.getByRole('combobox')).toHaveTextContent('Custom');
  });
});

describe('TagSizeControl - custom W/H commit (AC-S1-1)', () => {
  it('commits a typed width on blur, not per keystroke', () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={onResize} />,
    );

    fireEvent.change(screen.getByLabelText('Tag width (mm)'), { target: { value: '77' } });
    expect(onResize).not.toHaveBeenCalled();

    fireEvent.blur(screen.getByLabelText('Tag width (mm)'));
    expect(onResize).toHaveBeenCalledWith(77, 40);
  });

  it('commits a typed height on Enter (blurs the field)', () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={onResize} />,
    );

    const input = screen.getByLabelText('Tag height (mm)') as HTMLInputElement;
    // jsdom only fires a real `blur` from `element.blur()` (what the
    // component's own Enter handler calls) when the element is actually the
    // focused one (`document.activeElement`) - `fireEvent.focus` dispatches
    // the event but does not itself move focus, so this calls the native
    // DOM method instead.
    input.focus();
    fireEvent.change(input, { target: { value: '52' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onResize).toHaveBeenCalledWith(60, 52);
  });

  it('a non-numeric draft is discarded on blur without calling onResize', () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={onResize} />,
    );

    fireEvent.change(screen.getByLabelText('Tag width (mm)'), { target: { value: 'abc' } });
    fireEvent.blur(screen.getByLabelText('Tag width (mm)'));

    expect(onResize).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Tag width (mm)')).toHaveValue(60);
  });
});

describe('TagSizeControl - floor clamp (AC-S1-4)', () => {
  it('clamps a value below the 10mm floor UP to it, with the same error text as the request designer', () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={onResize} />,
    );

    fireEvent.change(screen.getByLabelText('Tag width (mm)'), { target: { value: '5' } });
    fireEvent.blur(screen.getByLabelText('Tag width (mm)'));

    expect(onResize).toHaveBeenCalledWith(10, 40);
  });

  it('a bounds prop with a ceiling refuses a value above it, with the reason shown', () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl
        width_mm={60}
        height_mm={40}
        presets={PRESETS}
        onResize={onResize}
        bounds={{ min_mm: 10, max_width_mm: 100, max_height_mm: 100 }}
      />,
    );

    fireEvent.change(screen.getByLabelText('Tag width (mm)'), { target: { value: '400' } });
    fireEvent.blur(screen.getByLabelText('Tag width (mm)'));

    expect(onResize).not.toHaveBeenCalled();
    expect(screen.getByText(/Largest that fits this sheet/)).toBeInTheDocument();
  });

  it('an absent bounds prop means the floor only - no ceiling refusal, however large', () => {
    const onResize = vi.fn();
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={onResize} />,
    );

    fireEvent.change(screen.getByLabelText('Tag width (mm)'), { target: { value: '900' } });
    fireEvent.blur(screen.getByLabelText('Tag width (mm)'));

    expect(onResize).toHaveBeenCalledWith(900, 40);
  });
});

describe('TagSizeControl - optional affordances (AC-S1-1)', () => {
  it('renders no "Apply to all lines" button when onResizeAll is absent (the template editor\'s own case)', () => {
    render(
      <TagSizeControl width_mm={60} height_mm={40} presets={PRESETS} onResize={vi.fn()} />,
    );

    expect(
      screen.queryByRole('button', { name: 'Apply to all lines' }),
    ).not.toBeInTheDocument();
  });

  it('renders "Apply to all lines" when onResizeAll IS given, and it fires with the current size', () => {
    const onResizeAll = vi.fn();
    render(
      <TagSizeControl
        width_mm={60}
        height_mm={40}
        presets={PRESETS}
        onResize={vi.fn()}
        onResizeAll={onResizeAll}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Apply to all lines' }));

    expect(onResizeAll).toHaveBeenCalledWith(60, 40);
  });

  it('renders no delete affordance on a saved size row without onDeleteSavedSize', async () => {
    render(
      <TagSizeControl
        width_mm={60}
        height_mm={40}
        presets={PRESETS}
        savedSizes={[
          {
            id: 'size-1',
            name: 'My favourite',
            width_mm: 80,
            height_mm: 50,
            created_by: null,
            created_by_name: null,
            created_at: '2026-08-01T00:00:00Z',
            updated_at: '2026-08-01T00:00:00Z',
          },
        ]}
        onResize={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('combobox'));
    await screen.findByRole('option', { name: /My favourite/ });

    expect(screen.queryByLabelText(/Delete saved size/)).not.toBeInTheDocument();
  });
});
