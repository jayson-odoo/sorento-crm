/**
 * Review round: linking 1,000 contacts must not fire 1,000 requests at once, and a partial
 * failure is ONE summary toast with a count, not every message joined.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const link = vi.hoisted(() => vi.fn());
vi.mock('../[id]/services/contactCustomersService', () => ({ linkContactCustomers: link }));
vi.mock('@/app/(protected)/order-management/customers/hooks/useCustomerMultiPicker', () => ({
  useCustomerMultiPicker: () => ({
    selected: ['cust-1'],
    setSelected: vi.fn(),
    selectedOptions: [],
    fetchOptions: vi.fn(async () => []),
    clear: vi.fn(),
  }),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({ SearchableMultiSelect: () => null }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

import BulkLinkCustomersDialog from './BulkLinkCustomersDialog';

const contacts = Array.from({ length: 20 }, (_, i) => ({
  id: `c-${i + 1}`,
  name: `Contact ${i + 1}`,
  phone_number: `+6010000${i}`,
})) as never[];

function mount(onLinked = vi.fn(), onOpenChange = vi.fn()) {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <BulkLinkCustomersDialog open onOpenChange={onOpenChange} contacts={contacts} onLinked={onLinked} />
    </QueryClientProvider>,
  );
  return onLinked;
}

beforeEach(() => {
  link.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
});

describe('BulkLinkCustomersDialog request volume', () => {
  it('keeps at most 6 link requests in flight at once', async () => {
    let inFlight = 0;
    let peak = 0;
    link.mockImplementation(async () => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight -= 1;
    });
    mount();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
      await new Promise((r) => setTimeout(r, 300));
    });
    expect(link).toHaveBeenCalledTimes(20);
    expect(peak).toBeLessThanOrEqual(6);
  });

  it('reports failures as one summary with a count', async () => {
    link.mockImplementation(async (id: string) => {
      if (['c-2', 'c-9', 'c-15'].includes(id)) throw new Error('Customer locked');
    });
    const onLinked = mount();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
      await new Promise((r) => setTimeout(r, 300));
    });
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).toContain('3 of 20');
    expect(toast.error.mock.calls[0][0]).not.toContain('Contact 2:');
    expect(onLinked).toHaveBeenCalledWith(expect.not.arrayContaining(['c-2', 'c-9', 'c-15']));
  });

  describe('while a link run is in flight', () => {
    async function startRun() {
      const resolvers: (() => void)[] = [];
      link.mockImplementation(() => new Promise<void>((r) => resolvers.push(r)));
      const onOpenChange = vi.fn();
      mount(vi.fn(), onOpenChange);
      fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
      await waitFor(() => expect(link).toHaveBeenCalled());
      return { onOpenChange, resolvers };
    }

    it('S2: Escape does not close the dialog', async () => {
      const { onOpenChange } = await startRun();
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
      expect(onOpenChange).not.toHaveBeenCalledWith(false);
    });

    it('S2: Cancel is disabled and closes nothing', async () => {
      const { onOpenChange } = await startRun();
      const cancel = screen.getByRole('button', { name: 'Cancel' });
      expect(cancel).toBeDisabled();
      fireEvent.click(cancel);
      expect(onOpenChange).not.toHaveBeenCalledWith(false);
    });

    it('S2: an outside click does not close the dialog', async () => {
      const { onOpenChange } = await startRun();
      const overlay = document.querySelector('[data-slot="dialog-overlay"]') as HTMLElement | null;
      fireEvent.pointerDown(overlay ?? document.body);
      fireEvent.click(overlay ?? document.body);
      expect(onOpenChange).not.toHaveBeenCalledWith(false);
    });

    it('S2: after the run settles the dialog closes as today', async () => {
      const { onOpenChange, resolvers } = await startRun();
      await act(async () => {
        // the pool hands out new requests as earlier ones finish
        for (let i = 0; i < 40; i++) {
          resolvers.splice(0).forEach((r) => r());
          await new Promise((r) => setTimeout(r, 5));
        }
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
