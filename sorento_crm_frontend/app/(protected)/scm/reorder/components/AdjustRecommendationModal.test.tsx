/**
 * SCM M4 Slice B — AdjustRecommendationModal (AC-M4.7).
 * Override qty and/or switch supplier from the run's ranked alternatives;
 * switching recomputes the live preview; a reason is REQUIRED (blocks submit
 * when empty); submit emits the override payload. The modal must still render
 * when the rec has NO alternatives (empty-alternatives case).
 *
 * SearchableSelect is mocked to a native <select> (the real one is a Radix
 * popover + cmdk list, non-deterministic in jsdom) — same pattern as the
 * policies modal test.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

// Native-select stand-in so supplier switching is deterministic in jsdom.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'Supplier'} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { AdjustRecommendationModal } from './AdjustRecommendationModal';
import type { ReorderRecommendation, SupplierChoice } from '../types/reorder.types';

const primary: SupplierChoice = {
  supplier_code: 'SUP-ACME',
  supplier_name: 'Acme Sanitary',
  unit_cost: 42,
  lead_time_days: 14,
  composite_score: 88,
  is_primary: true,
};
const beta: SupplierChoice = {
  supplier_code: 'SUP-BETA',
  supplier_name: 'Beta Supplies',
  unit_cost: 38,
  lead_time_days: 21,
  composite_score: 80,
  is_primary: false,
};

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'rec-1',
    sku: 'CW-BASIN-450',
    product_name: 'Ceramic Wash Basin 450mm',
    order_qty: 320,
    supplier: primary,
    alternatives: [primary, beta],
    cash_impact: 13440,
    lead_time_days: 14,
    ...(over as ReorderRecommendation),
  } as ReorderRecommendation;
}

function renderModal(over: Partial<React.ComponentProps<typeof AdjustRecommendationModal>> = {}) {
  const onSubmit = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <AdjustRecommendationModal
      rec={rec()}
      open
      onOpenChange={onOpenChange}
      onSubmit={onSubmit}
      isSubmitting={false}
      {...over}
    />,
  );
  return { onSubmit, onOpenChange };
}

beforeEach(() => vi.clearAllMocks());

describe('AdjustRecommendationModal (AC-M4.7)', () => {
  it('seeds the form with the proposed qty + supplier and shows the proposed summary', () => {
    renderModal();
    expect(screen.getByText('Adjust CW-BASIN-450')).toBeInTheDocument();
    expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('320');
    expect((screen.getByLabelText('Select a supplier') as HTMLSelectElement).value).toBe('SUP-ACME');
  });

  it('blocks submit and shows the required-reason error when the reason is empty', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: /Save adjustment/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/A reason is required/i)).toBeInTheDocument();
  });

  it('emits the override payload (qty + switched supplier + reason) on submit', () => {
    const { onSubmit } = renderModal();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Select a supplier'), { target: { value: 'SUP-BETA' } });
    fireEvent.change(screen.getByPlaceholderText(/Why are you adjusting/i), {
      target: { value: 'cheaper alternative' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save adjustment/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      override_qty: 500,
      override_supplier_code: 'SUP-BETA',
      reason_text: 'cheaper alternative',
    });
  });

  it('sends a null supplier code when the proposed supplier is unchanged (qty-only adjust)', () => {
    const { onSubmit } = renderModal();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '400' } });
    fireEvent.change(screen.getByPlaceholderText(/Why are you adjusting/i), {
      target: { value: 'MOQ changed' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save adjustment/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      override_qty: 400,
      override_supplier_code: null,
      reason_text: 'MOQ changed',
    });
  });

  it('recomputes the cash-impact preview off the switched supplier', () => {
    renderModal();
    fireEvent.change(screen.getByLabelText('Select a supplier'), { target: { value: 'SUP-BETA' } });
    // Preview recomputes off Beta (38 × 320 = 12,160).
    expect(screen.getByText(/Recomputed off Beta Supplies/i)).toBeInTheDocument();
    expect(screen.getByText('RM 12,160')).toBeInTheDocument();
  });

  it('still renders when the rec has NO alternatives (empty-alternatives case)', () => {
    const { onSubmit } = renderModal({ rec: rec({ alternatives: [] }) });
    // The modal renders and a qty-only adjust is still possible.
    expect(screen.getByText('Adjust CW-BASIN-450')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '600' } });
    fireEvent.change(screen.getByPlaceholderText(/Why are you adjusting/i), {
      target: { value: 'bulk buy' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save adjustment/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      override_qty: 600,
      override_supplier_code: null,
      reason_text: 'bulk buy',
    });
  });

  it('renders nothing when there is no rec', () => {
    const { container } = render(
      <AdjustRecommendationModal
        rec={null}
        open
        onOpenChange={vi.fn()}
        onSubmit={vi.fn()}
        isSubmitting={false}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
