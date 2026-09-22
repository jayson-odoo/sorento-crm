/**
 * Settings > Chatbot > Stock low threshold card (S0, AC-1732, AC-1733; D7).
 *
 * RED, written before `./StockLowThresholdCard.tsx` exists.
 *
 * Presentational only (coordinator correction, 22 Sep 2026): the Chatbot settings page was
 * deliberately consolidated to ONE Save button (16 Sep 2026 browser pass; `page.test.tsx`'s
 * `saveButton()` helper, `getByRole('button', { name: /save/i })`, throws the moment a second
 * accessible "Save" button exists anywhere on the page). So this card owns no query, no
 * mutation, no service call and no toast, and it renders no Save button of its own - exactly
 * the controlled shape `TierOrderCard`/`MemorySettingsCard` already use for the rest of the
 * blob. `chatbot_stock_low_threshold_pct` becomes a field of the SAME `ChatbotSettings`
 * draft/save the page already owns (`useChatbotSettings` state, the page's single Save posting
 * it alongside the other keys) - see the new cases added to `page.test.tsx` for that wiring.
 *
 * Expected component, `./StockLowThresholdCard.tsx` (default export):
 *   props `{ value: number | null; onChange: (value: number) => void }`
 *   - a `Card` titled "Stock low threshold" with a percentage `<input type="number" min={1}
 *     max={100}>` labelled "Stock low threshold (%)", seeded from `value`
 *   - `onChange` fires with the typed number when it is in [1, 100]
 *   - a typed value above 100 is CLAMPED to 100 before `onChange` fires; below 1 is clamped to
 *     1 - the native `min`/`max` attributes alone do not stop a typed (non-stepper) value
 *     outside that range, so the component clamps in its own change handler
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import StockLowThresholdCard from './StockLowThresholdCard';

afterEach(() => cleanup());

describe('StockLowThresholdCard - renders the value (AC-1732)', () => {
  it('shows the card title and the current value as a percentage input', () => {
    render(<StockLowThresholdCard value={50} onChange={vi.fn()} />);

    expect(screen.getByText(/stock low threshold/i)).toBeInTheDocument();
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    expect(input.value).toBe('50');
    expect(input).toHaveAttribute('min', '1');
    expect(input).toHaveAttribute('max', '100');
  });
});

describe('StockLowThresholdCard - onChange (AC-1732)', () => {
  it('calls onChange with the typed in-range number', () => {
    const onChange = vi.fn();
    render(<StockLowThresholdCard value={50} onChange={onChange} />);

    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '75' } });

    expect(onChange).toHaveBeenCalledWith(75);
  });

  it('clamps a value above 100 to 100 before calling onChange', () => {
    const onChange = vi.fn();
    render(<StockLowThresholdCard value={50} onChange={onChange} />);

    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '150' } });

    expect(onChange).toHaveBeenCalledWith(100);
  });

  it('clamps a value below 1 to 1 before calling onChange', () => {
    const onChange = vi.fn();
    render(<StockLowThresholdCard value={50} onChange={onChange} />);

    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '0' } });

    expect(onChange).toHaveBeenCalledWith(1);
  });
});

describe('StockLowThresholdCard - no Save button of its own', () => {
  it('renders no button with an accessible name matching /save/i (the page owns exactly one)', () => {
    render(<StockLowThresholdCard value={50} onChange={vi.fn()} />);

    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });
});
