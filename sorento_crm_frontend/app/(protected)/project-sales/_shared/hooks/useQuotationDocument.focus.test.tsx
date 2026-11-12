/**
 * QUOTE-AUTOSAVE crew pass: the proposal page reads "Unsaved draft" off the record, and the draft
 * is written from the edit form (or another tab). Under the app's own query defaults (no refetch
 * on focus, 30 s fresh), the page must still re-read the record when the reader comes back to it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const getQuotationDocument = vi.fn();
vi.mock('../services/quotationDocumentService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/quotationDocumentService')>()),
  getQuotationDocument: (...args: unknown[]) => getQuotationDocument(...args),
}));

import { useQuotationDocument } from './useQuotationDocuments';

describe('useQuotationDocument', () => {
  it('re-reads the record when the window regains focus, despite the app-wide default', async () => {
    getQuotationDocument.mockResolvedValue({ id: 'd1', has_form_draft: false });
    // The QueryProvider's own defaults (providers/query-provider.tsx).
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000, refetchOnWindowFocus: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useQuotationDocument('p1', 'd1'), { wrapper });
    await waitFor(() => expect(result.current.data?.has_form_draft).toBe(false));

    getQuotationDocument.mockResolvedValue({ id: 'd1', has_form_draft: true });
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => expect(result.current.data?.has_form_draft).toBe(true));
    focusManager.setFocused(undefined);
  });
});
