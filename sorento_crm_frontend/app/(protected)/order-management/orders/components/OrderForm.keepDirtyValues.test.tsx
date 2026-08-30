/**
 * S7-03 - a form takes its record through `values`, and a refetch does not
 * clobber a field the reader is mid-typing into.
 *
 * OrderForm feeds react-hook-form through `values: editValues` with
 * `resetOptions: { keepDirtyValues: true }` (see OrderForm.tsx). This test
 * dirties a field, then simulates a refetch (the `useOrder` mock returning a
 * new object) that changes a DIFFERENT field, and asserts the dirtied field
 * keeps what the reader typed while the untouched field takes the new value.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import OrderForm from './OrderForm';

const useOrder = vi.fn();
const useOrderStatusSelectQuery = vi.fn();
const noopMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

vi.mock('../hooks/useOrders', () => ({
  useOrder: (...a: unknown[]) => useOrder(...a),
  useCreateOrder: () => noopMutation,
  useUpdateOrder: () => noopMutation,
}));

vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: (...a: unknown[]) => useOrderStatusSelectQuery(...a),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

function baseOrder(overrides: Record<string, unknown> = {}) {
  return {
    id: 'o-1',
    order_number: 'REPPS2605-0012',
    debtor_name: 'Acme Corp',
    agent: 'Original Agent',
    ...overrides,
  };
}

beforeEach(() => {
  useOrder.mockReset();
  useOrderStatusSelectQuery.mockReset();
  useOrderStatusSelectQuery.mockReturnValue({ data: [] });
});

describe('OrderForm keeps dirty values through a refetch (S7-03)', () => {
  it('a typed field survives a refetch, and an untouched field picks up the new value', async () => {
    useOrder.mockReturnValue({ data: baseOrder(), isLoading: false });
    const { rerender } = render(<OrderForm orderId="o-1" />);

    const debtorNameInput = await waitFor(() =>
      screen.getByDisplayValue('Acme Corp'),
    ) as HTMLInputElement;

    // Dirty debtor_name by typing something the reader chose.
    fireEvent.change(debtorNameInput, { target: { value: 'Typed By Reader' } });
    await waitFor(() => expect(debtorNameInput.value).toBe('Typed By Reader'));

    // Simulate a refetch: a NEW order object (new reference) where debtor_name
    // is unchanged server-side but `agent` has moved on.
    useOrder.mockReturnValue({
      data: baseOrder({ debtor_name: 'Acme Corp', agent: 'New Agent' }),
      isLoading: false,
    });
    rerender(<OrderForm orderId="o-1" />);

    // The field the reader typed into keeps what they typed...
    await waitFor(() => {
      expect(screen.getByDisplayValue('Typed By Reader')).toBeInTheDocument();
    });
    // ...and the untouched field takes the refetch's new value.
    await waitFor(() => {
      expect(screen.getByDisplayValue('New Agent')).toBeInTheDocument();
    });
    expect(screen.queryByDisplayValue('Original Agent')).not.toBeInTheDocument();
  });
});
