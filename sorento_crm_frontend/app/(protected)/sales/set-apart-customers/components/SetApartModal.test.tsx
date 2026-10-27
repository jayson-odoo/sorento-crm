import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({
  createSetApart: vi.fn(),
  updateSetApart: vi.fn(),
  getSetApartCustomers: vi.fn(),
  getSetApartCustomerOptions: vi.fn(),
}));
vi.mock('../services/setApartService', () => service);
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import SetApartModal, { buildSetApartPayload } from './SetApartModal';

const ROW = {
  id: 'r1',
  customer_id: 'c1',
  debtor_code: 'A001',
  customer_name: 'Acme',
  from_month: '2026-01',
  to_month: null,
};

function renderModal(row: typeof ROW | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SetApartModal open onOpenChange={vi.fn()} row={row} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.createSetApart.mockResolvedValue(ROW);
  service.updateSetApart.mockResolvedValue(ROW);
  service.getSetApartCustomerOptions.mockResolvedValue([]);
});

describe('buildSetApartPayload', () => {
  it('sends null for an empty To month', () => {
    expect(buildSetApartPayload({ customerId: 'c1', fromMonth: '2026-01', toMonth: '' })).toEqual({
      customer_id: 'c1',
      from_month: '2026-01',
      to_month: null,
    });
  });
  it('keeps a To month', () => {
    expect(buildSetApartPayload({ customerId: 'c1', fromMonth: '2026-01', toMonth: '2026-03' }).to_month).toBe(
      '2026-03',
    );
  });
});

describe('SetApartModal', () => {
  it('saves an edit as a PATCH with the changed To month', async () => {
    renderModal(ROW);
    fireEvent.change(screen.getByLabelText('To month'), { target: { value: '2026-06' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(service.updateSetApart).toHaveBeenCalledWith('r1', {
        customer_id: 'c1',
        from_month: '2026-01',
        to_month: '2026-06',
      }),
    );
    expect(service.createSetApart).not.toHaveBeenCalled();
  });

  it('blocks Save while To month is before From month', () => {
    renderModal(ROW);
    fireEvent.change(screen.getByLabelText('To month'), { target: { value: '2025-12' } });
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
