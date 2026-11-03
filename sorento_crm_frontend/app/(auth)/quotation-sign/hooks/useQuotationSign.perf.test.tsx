/**
 * QUOTE-PERF-HOTFIX (3 Nov): the public sign page is not read again each time the customer
 * switches back to the tab. Every read inlines the quotation's pictures server side.
 */
import React from 'react';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const getQuotationSignPage = vi.fn();

vi.mock('../services/quotationSignService', () => ({
  getQuotationSignPage: (...a: unknown[]) => getQuotationSignPage(...a),
  acceptQuotation: vi.fn(),
  submitAmendmentRequest: vi.fn(),
  QuotationSignError: class extends Error {},
}));

import { useQuotationSignPage } from './useQuotationSign';

describe('useQuotationSignPage', () => {
  it('does not refetch the page when the window regains focus', async () => {
    getQuotationSignPage.mockResolvedValue({ scopes: [] });
    const client = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useQuotationSignPage('tok'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getQuotationSignPage).toHaveBeenCalledTimes(1);

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await new Promise((r) => setTimeout(r, 20));

    expect(getQuotationSignPage).toHaveBeenCalledTimes(1);
    focusManager.setFocused(undefined);
  });
});
