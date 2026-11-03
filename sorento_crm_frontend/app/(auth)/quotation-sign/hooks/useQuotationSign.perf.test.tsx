/**
 * QUOTE-PERF-HOTFIX (3 Nov): the public sign page is not read again each time the customer
 * switches back to the tab. Every read inlines the quotation's pictures server side. The app's
 * own QueryProvider (root layout) is what guarantees it, so the hook is rendered inside it.
 */
import React from 'react';
import { focusManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const getQuotationSignPage = vi.fn();

vi.mock('../services/quotationSignService', () => ({
  getQuotationSignPage: (...a: unknown[]) => getQuotationSignPage(...a),
  acceptQuotation: vi.fn(),
  submitAmendmentRequest: vi.fn(),
  QuotationSignError: class extends Error {},
}));

import { QueryProvider } from '@/providers/query-provider';

import { useQuotationSignPage } from './useQuotationSign';

describe('useQuotationSignPage', () => {
  it('does not refetch the page when the window regains focus', async () => {
    getQuotationSignPage.mockResolvedValue({ scopes: [] });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );
    const { result } = renderHook(() => useQuotationSignPage('tok'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getQuotationSignPage).toHaveBeenCalledTimes(1);

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await new Promise((r) => setTimeout(r, 50));

    expect(getQuotationSignPage).toHaveBeenCalledTimes(1);
    focusManager.setFocused(undefined);
  });
});
