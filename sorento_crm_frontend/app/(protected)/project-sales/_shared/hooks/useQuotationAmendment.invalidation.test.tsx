/**
 * QUOTE-CUSTOMER-AMEND fix round 2 (D2): opening a revision must refresh the customer's
 * suggestions on the Lines tab, because its `blocked_scopes` (a hand-made draft stands in the
 * way of Apply) is what the summary row explains. Without it the cached "nothing blocked" stayed
 * on screen and the reason never showed.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const reviseQuotation = vi.fn();

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return { ...actual, reviseQuotation: (...args: unknown[]) => reviseQuotation(...args) };
});
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useQuotationMutations } from './useProjects';
import { quotationAmendmentKey } from './useQuotationDocuments';

describe('a scope revise and the suggestions read', () => {
  it('invalidates the amendment request, so blocked_scopes is read again', async () => {
    reviseQuotation.mockResolvedValue({ id: 'v2', quotation_id: 'q1', version_no: 2 });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidated: unknown[][] = [];
    const original = client.invalidateQueries.bind(client);
    client.invalidateQueries = ((filters?: { queryKey?: unknown[] }) => {
      invalidated.push(filters?.queryKey ?? []);
      return original(filters);
    }) as typeof client.invalidateQueries;

    let api: ReturnType<typeof useQuotationMutations> | null = null;
    function Harness() {
      api = useQuotationMutations('p1');
      return null;
    }
    render(
      <QueryClientProvider client={client}>
        <Harness />
      </QueryClientProvider>,
    );
    await act(async () => {
      await api!.revise.mutateAsync('q1');
    });

    const amendmentPrefix = quotationAmendmentKey('p1', 'd1')[0];
    expect(invalidated.some((key) => key[0] === amendmentPrefix)).toBe(true);
  });
});
