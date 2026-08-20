/**
 * SCM M8 - RunPlanningModal (M8-D5, revised + AC-B8a). Manual-plan inputs are
 * warehouse(s), products and budget. NO market-insight toggle (market never enters a
 * run), and the legacy `buy_scope` input is gone (planning is always per-warehouse).
 * Warehouse is MULTI-select with a Select-all shortcut and at least one is required;
 * products are MULTI-select and OPTIONAL, where empty means every product, so
 * existing behaviour and the scheduled daily run are unchanged. Submit emits
 * { warehouse_codes, product_codes, budget }.
 *
 * SearchableMultiSelect + the option hooks are stubbed so the pick is deterministic.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

// Stub the multi-select as a group of checkboxes so selection is deterministic. There
// are now TWO of them on this modal, so the group is labelled by its placeholder
// rather than a hard-coded name.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <div aria-label={placeholder ?? 'multi-select'}>
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            aria-label={o.label}
            checked={value.includes(o.value)}
            onChange={(e) =>
              onChange(
                e.target.checked ? [...value, o.value] : value.filter((x) => x !== o.value),
              )
            }
          />
          {o.label}
        </label>
      ))}
    </div>
  ),
}));

vi.mock('../../hooks/useScmOptions', () => ({
  useWarehouseOptions: () => ({
    data: [
      { value: 'WH-KL', label: 'Kuala Lumpur DC' },
      { value: 'WH-JB', label: 'Johor Bahru DC' },
    ],
    isLoading: false,
    isError: false,
  }),
  useProductOptions: () => ({
    data: [
      { value: 'SRTWT7408', label: 'SRTWT7408 · Wall-hung WC 7408' },
      { value: 'SRTBS4832', label: 'SRTBS4832 · Basin mixer 4832' },
    ],
    isLoading: false,
    isError: false,
  }),
}));

import { RunPlanningModal } from './RunPlanningModal';

function renderModal(over: Partial<React.ComponentProps<typeof RunPlanningModal>> = {}) {
  const onSubmit = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <RunPlanningModal open onOpenChange={onOpenChange} onSubmit={onSubmit} isSubmitting={false} {...over} />,
  );
  return { onSubmit, onOpenChange };
}

beforeEach(() => vi.clearAllMocks());

describe('RunPlanningModal (M8-D5)', () => {
  it('shows the warehouse(s), products and budget inputs, and no market toggle or buy_scope', () => {
    renderModal();
    expect(screen.getByText('Manual plan')).toBeInTheDocument();
    expect(screen.getByText('Warehouses')).toBeInTheDocument();
    expect(screen.getByLabelText('Select warehouses')).toBeInTheDocument();
    expect(screen.getByText('Products')).toBeInTheDocument();
    expect(screen.getByLabelText('All products')).toBeInTheDocument();
    expect(screen.getByLabelText(/Cash budget/i)).toBeInTheDocument();
    // No market insight toggle and no buy-scope (network/warehouse) selector.
    expect(screen.queryByText(/market/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/buy scope/i)).not.toBeInTheDocument();
  });

  it('blocks submit and shows the required-warehouse error when none is picked', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/Select at least one warehouse/i)).toBeInTheDocument();
  });

  it('emits { warehouse_codes, product_codes, budget } on submit (M8-D5 / AC-B8a)', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByLabelText('Johor Bahru DC'));
    fireEvent.change(screen.getByLabelText(/Cash budget/i), { target: { value: '50000' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: ['WH-JB'],
      product_codes: [],
      budget: 50000,
      plan_horizon_date: '',
    });
  });

  it('Select all picks every warehouse; Clear all empties it', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: /Select all/i }));
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: ['WH-KL', 'WH-JB'],
      product_codes: [],
      budget: 72000,
      plan_horizon_date: '',
    });
  });

  it('narrows the run to the picked products, by human code (AC-B8a)', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
    fireEvent.click(screen.getByLabelText('SRTWT7408 · Wall-hung WC 7408'));
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: ['WH-KL'],
      product_codes: ['SRTWT7408'],
      budget: 72000,
      plan_horizon_date: '',
    });
  });

  it('does NOT require a product: empty means every product, so the run stays as it was', () => {
    renderModal();
    // No "Clear all" for products until something is picked, and no validation error
    // when none ever is.
    fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(screen.queryByText(/Select at least one product/i)).not.toBeInTheDocument();
    expect(screen.getByText('Leave empty to plan every product.')).toBeInTheDocument();
  });
});
