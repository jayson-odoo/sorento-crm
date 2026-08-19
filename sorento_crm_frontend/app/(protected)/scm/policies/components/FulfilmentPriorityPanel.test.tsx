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
  buy_all_horizon_days: 180,
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
    expect(screen.getByLabelText(/Buy-all horizon/i)).toHaveValue(180);
    expect(screen.getByLabelText(/borrow cap \(qty\)/i)).toHaveValue(50);
    expect(screen.getByLabelText(/borrow cap \(%\)/i)).toHaveValue(10);
  });

  it('save sends the edited weights and settings', async () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);

    fireEvent.change(screen.getByLabelText('Delivery date'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/Buy-all horizon/i), { target: { value: '90' } });
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
      buy_all_horizon_days: 90,
      cross_group_borrow_max_qty: 50,
      cross_group_borrow_max_pct: 10,
    });
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
});
