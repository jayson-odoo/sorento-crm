/**
 * NEW-PRODUCT-APP S2: image upload, copy and delete go through useNewProductApplicationMutations
 * (uploadImage, copyImage, deleteImage) and refresh the detail query ['new-product-application', id]
 * once the call resolves.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const svc = vi.hoisted(() => ({
  upload: vi.fn(),
  copy: vi.fn(),
  del: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock('../services/newProductApplicationService', async (orig) => ({
  ...(await orig<object>()),
  uploadNewProductApplicationLineImage: (...a: unknown[]) => svc.upload(...a),
  copyNewProductApplicationLineImage: (...a: unknown[]) => svc.copy(...a),
  deleteNewProductApplicationLineImage: (...a: unknown[]) => svc.del(...a),
}));

import { useNewProductApplicationMutations } from './useNewProductApplications';

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { spy, ...renderHook(() => useNewProductApplicationMutations(), { wrapper }) };
}

const refreshedDetail = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls.some(([f]) => {
    const key = (f as { queryKey?: unknown[] } | undefined)?.queryKey;
    return key?.[0] === 'new-product-application' && key?.[1] === 'npa-1';
  });

beforeEach(() => {
  vi.clearAllMocks();
  svc.upload.mockResolvedValue({ id: 'npa-1', lines: [] });
  svc.copy.mockResolvedValue({ id: 'npa-1', lines: [] });
  svc.del.mockResolvedValue(undefined);
});

describe('image mutations', () => {
  it('uploadImage calls the service and refreshes the detail query', async () => {
    const { result, spy } = setup();
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    await act(() =>
      result.current.uploadImage.mutateAsync({ id: 'npa-1', lineId: 'l-1', file }),
    );
    expect(svc.upload).toHaveBeenCalledWith('npa-1', 'l-1', file);
    expect(refreshedDetail(spy)).toBe(true);
  });

  it('copyImage calls the service and refreshes the detail query', async () => {
    const { result, spy } = setup();
    await act(() =>
      result.current.copyImage.mutateAsync({
        id: 'npa-1',
        lineId: 'l-1',
        attachmentId: 'at-9',
      }),
    );
    expect(svc.copy).toHaveBeenCalledWith('npa-1', 'l-1', 'at-9');
    expect(refreshedDetail(spy)).toBe(true);
  });

  it('deleteImage calls the service and refreshes the detail query after it resolves', async () => {
    const { result, spy } = setup();
    await act(() =>
      result.current.deleteImage.mutateAsync({
        id: 'npa-1',
        lineId: 'l-1',
        linkId: 'k-1',
      }),
    );
    expect(svc.del).toHaveBeenCalledWith('npa-1', 'l-1', 'k-1');
    expect(refreshedDetail(spy)).toBe(true);
  });
});
