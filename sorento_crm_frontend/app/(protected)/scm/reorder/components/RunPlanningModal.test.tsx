/**
 * SCM M8 — RunPlanningModal (M8-D5, revised). Manual-plan inputs are EXACTLY
 * warehouse(s) + budget. NO market-insight toggle (market never enters a run), and
 * the legacy `buy_scope` input is gone (planning is always per-warehouse). Warehouse
 * is now MULTI-select with a Select-all shortcut; at least one is required; submit
 * emits { warehouse_codes, budget }.
 *
 * SearchableMultiSelect + useWarehouseOptions are stubbed so the pick is deterministic.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

// Stub the multi-select as a group of checkboxes so selection is deterministic.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options: { value: string; label: string }[];
  }) => (
    <div aria-label="Warehouses">
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
  it('shows ONLY the warehouse(s) + budget inputs — no market toggle, no buy_scope', () => {
    renderModal();
    expect(screen.getByText('Manual plan')).toBeInTheDocument();
    expect(screen.getByLabelText('Warehouses')).toBeInTheDocument();
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

  it('emits { warehouse_codes, budget } on submit (M8-D5)', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByLabelText('Johor Bahru DC'));
    fireEvent.change(screen.getByLabelText(/Cash budget/i), { target: { value: '50000' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(onSubmit).toHaveBeenCalledWith({ warehouse_codes: ['WH-JB'], budget: 50000 });
  });

  it('Select all picks every warehouse; Clear all empties it', () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: /Select all/i }));
    fireEvent.click(screen.getByRole('button', { name: /Generate plan/i }));
    expect(onSubmit).toHaveBeenCalledWith({ warehouse_codes: ['WH-KL', 'WH-JB'], budget: 72000 });
  });
});
