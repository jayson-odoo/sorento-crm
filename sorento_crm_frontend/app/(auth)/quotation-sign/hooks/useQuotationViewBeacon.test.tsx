import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const getSession = vi.fn();
vi.mock('next-auth/react', () => ({ getSession: () => getSession() }));
const recordQuotationView = vi.fn();
vi.mock('../services/quotationSignService', () => ({
  recordQuotationView: (...args: unknown[]) => recordQuotationView(...args),
}));

import { useQuotationViewBeacon, VISITOR_KEY } from './useQuotationViewBeacon';

beforeEach(() => {
  getSession.mockReset();
  recordQuotationView.mockReset().mockResolvedValue(undefined);
  window.localStorage.clear();
});

describe('useQuotationViewBeacon', () => {
  it('waits until the quotation has loaded', async () => {
    getSession.mockResolvedValue(null);
    const { rerender } = renderHook(
      ({ loaded }) => useQuotationViewBeacon('tok', loaded),
      {
        initialProps: { loaded: false },
      },
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(recordQuotationView).not.toHaveBeenCalled();
    rerender({ loaded: true });
    await waitFor(() => expect(recordQuotationView).toHaveBeenCalledTimes(1));
  });

  it('sends once per page load with the id this browser keeps', async () => {
    getSession.mockResolvedValue(null);
    const { rerender } = renderHook(() => useQuotationViewBeacon('tok', true));
    await waitFor(() => expect(recordQuotationView).toHaveBeenCalledTimes(1));
    rerender();
    await new Promise((r) => setTimeout(r, 0));
    expect(recordQuotationView).toHaveBeenCalledTimes(1);
    const kept = window.localStorage.getItem(VISITOR_KEY);
    expect(kept).toBeTruthy();
    expect(recordQuotationView).toHaveBeenCalledWith('tok', kept);
  });

  it('sends nothing from a browser signed in as staff', async () => {
    getSession.mockResolvedValue({
      user: { id: 'u1', homePath: '/dashboard' },
    });
    renderHook(() => useQuotationViewBeacon('tok', true));
    await new Promise((r) => setTimeout(r, 10));
    expect(recordQuotationView).not.toHaveBeenCalled();
  });

  it('still counts a portal contact (a customer with a session)', async () => {
    getSession.mockResolvedValue({
      user: { id: 'c1', homePath: '/my-requests' },
    });
    renderHook(() => useQuotationViewBeacon('tok', true));
    await waitFor(() => expect(recordQuotationView).toHaveBeenCalledTimes(1));
  });

  it('counts when the session check fails', async () => {
    getSession.mockRejectedValue(new Error('offline'));
    renderHook(() => useQuotationViewBeacon('tok', true));
    await waitFor(() => expect(recordQuotationView).toHaveBeenCalledTimes(1));
  });
});
