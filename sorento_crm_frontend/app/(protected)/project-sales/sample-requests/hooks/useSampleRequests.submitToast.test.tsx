/**
 * Crew pass 11 Nov (SAMPLE-REQUEST-V2): Submit showed two toasts, "Sample request SR-xxxxxx
 * submitted" from the caller and "Sample request submitted" from this hook. The hook stays quiet on
 * success; each caller says it once, with the number.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../services/sampleRequestService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/sampleRequestService')>();
  return { ...actual, submitSampleRequest: vi.fn(async () => ({ id: 'r-1', request_no: 'SR-000009' })) };
});

import { toast } from '@/lib/toast';
import { useSampleRequestMutations } from './useSampleRequests';

describe('useSampleRequestMutations submit', () => {
  it('shows no toast of its own on success', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useSampleRequestMutations(), { wrapper });
    await result.current.submit.mutateAsync('r-1');
    expect(toast.success).not.toHaveBeenCalled();
  });
});
