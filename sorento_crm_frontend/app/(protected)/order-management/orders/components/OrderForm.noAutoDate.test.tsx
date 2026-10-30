import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';

import OrderForm from './OrderForm';

/**
 * DO-EDIT-NO-AUTODATE: the edit form never invents a DO date. An undated DO (imported with
 * no readable document date) stays out of sales reports until a person types the real date,
 * so opening and saving it must not stamp today. An existing date is never wiped.
 */

const useOrder = vi.fn();
const useOrderStatusSelectQuery = vi.fn();
const updateMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
const createMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

vi.mock('../hooks/useOrders', () => ({
  useOrder: (...a: unknown[]) => useOrder(...a),
  useCreateOrder: () => createMutation,
  useUpdateOrder: () => updateMutation,
}));

vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: (...a: unknown[]) => useOrderStatusSelectQuery(...a),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

function todayInput(): string {
  return new Date().toISOString().slice(0, 10);
}

function mockOrder(overrides: Record<string, unknown>) {
  useOrder.mockReturnValue({
    data: {
      id: 'o-1',
      order_number: 'DO-NODATE-0001',
      order_date: null,
      order_status_id: 's-1',
      debtor_name: 'Seed Debtor',
      driver_name: 'Ali',
      subtotal_amount: 100,
      discount_amount: 0,
      tax_amount: 0,
      total_amount: 100,
      ...overrides,
    },
    isLoading: false,
  });
}

async function renderForm(orderId?: string) {
  render(<OrderForm orderId={orderId} onSuccess={() => {}} />);
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

function doDateInput(): HTMLInputElement {
  return screen.getByLabelText(/Delivery Order Date/) as HTMLInputElement;
}

function sentData(): Record<string, unknown> {
  return updateMutation.mutateAsync.mock.calls[0][0].data as Record<string, unknown>;
}

beforeEach(() => {
  useOrder.mockReset();
  useOrderStatusSelectQuery.mockReset();
  useOrderStatusSelectQuery.mockReturnValue({ data: [] });
  updateMutation.mutateAsync.mockReset();
  updateMutation.mutateAsync.mockResolvedValue({});
  createMutation.mutateAsync.mockReset();
});

describe('OrderForm on an undated DO', () => {
  it('shows an empty DO date, not today', async () => {
    mockOrder({});
    await renderForm('o-1');
    await waitFor(() => screen.getByDisplayValue('Seed Debtor'));
    expect(doDateInput().value).toBe('');
    expect(screen.queryByDisplayValue(todayInput())).not.toBeInTheDocument();
  });

  it('shows an empty estimated delivery date when the DO has none, not today + 2', async () => {
    mockOrder({ estimated_delivery_date: null });
    await renderForm('o-1');
    await waitFor(() => screen.getByDisplayValue('Seed Debtor'));
    expect((screen.getByLabelText(/Estimated Delivery Date/) as HTMLInputElement).value).toBe('');
  });

  it('saving another field leaves the DO date out of the update', async () => {
    mockOrder({});
    await renderForm('o-1');
    const debtor = await waitFor(() => screen.getByDisplayValue('Seed Debtor'));
    fireEvent.change(debtor, { target: { value: 'Seed Debtor Edited' } });
    fireEvent.click(screen.getByRole('button', { name: /Update Delivery Order/i }));
    await waitFor(() => expect(updateMutation.mutateAsync).toHaveBeenCalledTimes(1));
    const sent = sentData();
    expect(sent.debtor_name).toBe('Seed Debtor Edited');
    expect(sent.order_date ?? undefined).toBeUndefined();
    expect(JSON.stringify(sent)).not.toContain('order_date');
    expect(sent.estimated_delivery_date).toBeNull();
  });

  it('still takes a real date the user types', async () => {
    mockOrder({});
    await renderForm('o-1');
    await waitFor(() => screen.getByDisplayValue('Seed Debtor'));
    fireEvent.change(doDateInput(), { target: { value: '2026-10-15' } });
    fireEvent.click(screen.getByRole('button', { name: /Update Delivery Order/i }));
    await waitFor(() => expect(updateMutation.mutateAsync).toHaveBeenCalledTimes(1));
    const sent = sentData();
    expect((sent.order_date as Date).toISOString().slice(0, 10)).toBe('2026-10-15');
  });
});

describe('OrderForm clearing a date', () => {
  it('a typed then cleared DO date shows empty, not today, and is not sent', async () => {
    mockOrder({});
    await renderForm('o-1');
    await waitFor(() => screen.getByDisplayValue('Seed Debtor'));
    fireEvent.change(doDateInput(), { target: { value: '2026-10-15' } });
    fireEvent.change(doDateInput(), { target: { value: '' } });
    await waitFor(() => expect(doDateInput().value).toBe(''));
    fireEvent.click(screen.getByRole('button', { name: /Update Delivery Order/i }));
    await waitFor(() => expect(updateMutation.mutateAsync).toHaveBeenCalledTimes(1));
    expect(JSON.stringify(sentData())).not.toContain('order_date');
  });

  it('clearing a dated DO shows empty and the required message', async () => {
    mockOrder({ order_date: '2026-09-27' });
    await renderForm('o-1');
    await waitFor(() => expect(doDateInput().value).toBe('2026-09-27'));
    fireEvent.change(doDateInput(), { target: { value: '' } });
    await waitFor(() => expect(doDateInput().value).toBe(''));
    fireEvent.click(screen.getByRole('button', { name: /Update Delivery Order/i }));
    await waitFor(() => expect(screen.getByText('Order date is required.')).toBeInTheDocument());
    expect(updateMutation.mutateAsync).not.toHaveBeenCalled();
  });
});

describe('OrderForm on a dated DO', () => {
  it('shows the stored date and refuses to save it cleared', async () => {
    mockOrder({ order_date: '2026-09-27' });
    await renderForm('o-1');
    await waitFor(() => expect(doDateInput().value).toBe('2026-09-27'));
    fireEvent.change(doDateInput(), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /Update Delivery Order/i }));
    await waitFor(() => expect(screen.getByText('Order date is required.')).toBeInTheDocument());
    expect(updateMutation.mutateAsync).not.toHaveBeenCalled();
  });
});

describe('OrderForm in create mode', () => {
  it('keeps today as the default DO date', async () => {
    useOrder.mockReturnValue({ data: undefined, isLoading: false });
    await renderForm();
    expect(doDateInput().value).toBe(todayInput());
  });
});
