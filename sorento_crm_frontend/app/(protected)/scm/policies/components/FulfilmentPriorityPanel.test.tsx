/**
 * FulfilmentPriorityPanel - loading / empty / error / data states + save.
 * PLAN-demo-followups-19aug-ladder-v2.md C1/C2.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const hooks = vi.hoisted(() => ({
  useFulfilmentPriority: vi.fn(),
  useSaveFulfilmentPriority: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

import { FulfilmentPriorityPanel } from './FulfilmentPriorityPanel';

const DATA = {
  name: 'Fair fulfilment priority (delivery date, document date, customer credit)',
  factors: {
    po_document_sequence: 1,
    demand_class: 3,
    need_by_date: 3,
    document_age: 1,
    customer_credit: 1,
  },
  demand_class_weights: { project: 1, retail: 0.4 },
  reorder_coverage_until: '2026-10-31',
  cross_group_borrow_max_qty: 50,
  cross_group_borrow_max_pct: 10,
  exists: true,
};
const mutateAsync = vi.fn();

beforeEach(() => {
  hooks.useFulfilmentPriority.mockReset();
  hooks.useSaveFulfilmentPriority.mockReset();
  mutateAsync.mockReset().mockResolvedValue(DATA);
  hooks.useSaveFulfilmentPriority.mockReturnValue({ mutateAsync, isPending: false });
});

describe('FulfilmentPriorityPanel', () => {
  it('renders a loading skeleton (no inputs) while loading', () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<FulfilmentPriorityPanel />);
    expect(screen.queryByLabelText('Delivery date')).not.toBeInTheDocument();
  });

  it('renders the error state', () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<FulfilmentPriorityPanel />);
    expect(screen.getByText(/Failed to load the fulfilment priority policy/i)).toBeInTheDocument();
  });

  it('renders the empty state when no policy has been activated yet', () => {
    hooks.useFulfilmentPriority.mockReturnValue({
      data: { ...DATA, exists: false },
      isLoading: false,
      isError: false,
    });
    render(<FulfilmentPriorityPanel />);
    expect(screen.getByText(/No fulfilment priority has been activated yet/i)).toBeInTheDocument();
  });

  it('renders the stored weights and settings using the board labels', () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);
    expect(screen.getByLabelText('Delivery date')).toHaveValue(3);
    expect(screen.getByLabelText('Order date')).toHaveValue(1);
    expect(screen.getByLabelText('Payment terms')).toHaveValue(1);
    expect(screen.getByLabelText('Demand type')).toHaveValue(3);
    expect(screen.getByLabelText('Purchase order sequence')).toHaveValue(1);
    expect(screen.getByLabelText('Project')).toHaveValue(1);
    expect(screen.getByLabelText('Retail')).toHaveValue(0.4);
    expect(screen.getByLabelText(/Purchasing covers demand until/i)).toHaveValue('2026-10-31');
    expect(screen.getByLabelText(/borrow cap \(qty\)/i)).toHaveValue(50);
    expect(screen.getByLabelText(/borrow cap \(%\)/i)).toHaveValue(10);
  });

  it('save sends the edited weights and settings', async () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);

    fireEvent.change(screen.getByLabelText('Delivery date'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/Purchasing covers demand until/i), {
      target: { value: '2026-12-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({
      factors: {
        po_document_sequence: 1,
        demand_class: 3,
        need_by_date: 5,
        document_age: 1,
        customer_credit: 1,
      },
      demand_class_weights: { project: 1, retail: 0.4 },
      reorder_coverage_until: '2026-12-01',
      cross_group_borrow_max_qty: 50,
      cross_group_borrow_max_pct: 10,
    });
  });

  it('save with the date cleared sends null, not an empty string', async () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const payload = mutateAsync.mock.calls[0][0];
    expect(payload.reorder_coverage_until).toBeNull();
  });

  it('blocks a save with a negative weight (client mirror of the backend validation)', () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);

    fireEvent.change(screen.getByLabelText('Delivery date'), { target: { value: '-1' } });
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));

    expect(screen.getByText(/Delivery date weight must be 0 or more/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('blocks a save with an out-of-range cross-group borrow percentage', () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);

    fireEvent.change(screen.getByLabelText(/borrow cap \(%\)/i), { target: { value: '150' } });
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));

    expect(screen.getByText(/must be between 0 and 100/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('an extra factor / demand-class key the backend stored round-trips through save untouched', async () => {
    // `factors` / `demand_class_weights` are open JSONB - a key this screen does not
    // render (a future factor, or one added by another client) must survive a save
    // made through this screen rather than being dropped.
    const withExtras = {
      ...DATA,
      factors: { ...DATA.factors, future_factor: 2.5 },
      demand_class_weights: { ...DATA.demand_class_weights, wholesale: 0.7 },
    };
    hooks.useFulfilmentPriority.mockReturnValue({ data: withExtras, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);

    fireEvent.change(screen.getByLabelText('Delivery date'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const payload = mutateAsync.mock.calls[0][0];
    expect(payload.factors).toEqual({
      po_document_sequence: 1,
      demand_class: 3,
      need_by_date: 5,
      document_age: 1,
      customer_credit: 1,
      future_factor: 2.5,
    });
    expect(payload.demand_class_weights).toEqual({ project: 1, retail: 0.4, wholesale: 0.7 });
  });

  it('a rejected save is not an unhandled promise rejection', async () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    mutateAsync.mockReset().mockRejectedValue(new Error('ZZT save failed'));
    hooks.useSaveFulfilmentPriority.mockReturnValue({ mutateAsync, isPending: false });
    const onUnhandledRejection = vi.fn();
    window.addEventListener('unhandledrejection', onUnhandledRejection);

    render(<FulfilmentPriorityPanel />);
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    // Give the microtask queue a turn so an unhandled rejection would have fired.
    await new Promise((resolve) => setTimeout(resolve, 0));

    window.removeEventListener('unhandledrejection', onUnhandledRejection);
    expect(onUnhandledRejection).not.toHaveBeenCalled();
  });
});
