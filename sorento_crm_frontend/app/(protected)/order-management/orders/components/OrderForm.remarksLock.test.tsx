import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';

import OrderForm from './OrderForm';

/**
 * UAC-Z3: the order edit form renders Remarks CS readonly (disabled) when the
 * backend marks the order `remarks_cs_locked` (delivered + linked to a complaint).
 *
 * OrderForm populates fields from the loaded order via a `form.reset()` that runs
 * inside a `setTimeout(0)` (see OrderForm.tsx ~L168), and Remarks CS lives inside a
 * non-default "Remarks" tab - so the test must flush the timer, then open the tab.
 */

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

function mockOrder(overrides: Record<string, unknown>) {
  useOrder.mockReturnValue({
    data: { id: 'o-1', order_number: 'REPPS2605-0012', ...overrides },
    isLoading: false,
  });
  useOrderStatusSelectQuery.mockReturnValue({ data: [] });
}

async function renderAndOpenRemarks() {
  render(<OrderForm orderId="o-1" />);
  // Flush the setTimeout(0) inside OrderForm that runs form.reset() with order data.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  // Remarks CS lives in the non-default "Remarks" tab - open it.
  fireEvent.click(screen.getByRole('tab', { name: /Remarks/i }));
}

beforeEach(() => {
  useOrder.mockReset();
  useOrderStatusSelectQuery.mockReset();
});

describe('OrderForm Remarks CS freeze (UAC-Z3)', () => {
  it('disables the Remarks CS field and shows the lock note when remarks_cs_locked is true', async () => {
    mockOrder({ remarks_cs_locked: true, remarks_cs: 'CMP26-0042' });
    await renderAndOpenRemarks();

    const remarksFields = await waitFor(() => {
      const fields = screen
        .getAllByDisplayValue('CMP26-0042')
        .filter((el) => ['INPUT', 'TEXTAREA'].includes((el as HTMLElement).tagName));
      expect(fields.length).toBeGreaterThan(0);
      return fields;
    });
    remarksFields.forEach((el) => expect(el).toBeDisabled());
    expect(screen.getAllByText(/Locked -/i).length).toBeGreaterThan(0);
  });

  it('keeps the Remarks CS field editable when remarks_cs_locked is false', async () => {
    mockOrder({ remarks_cs_locked: false, remarks_cs: 'CMP26-0099' });
    await renderAndOpenRemarks();

    const remarksFields = await waitFor(() => {
      const fields = screen
        .getAllByDisplayValue('CMP26-0099')
        .filter((el) => ['INPUT', 'TEXTAREA'].includes((el as HTMLElement).tagName));
      expect(fields.length).toBeGreaterThan(0);
      return fields;
    });
    remarksFields.forEach((el) => expect(el).not.toBeDisabled());
    expect(screen.queryByText(/Locked -/i)).not.toBeInTheDocument();
  });
});
