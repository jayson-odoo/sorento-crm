/**
 * SPARE-PART-OR-B fix round 1, red-first. Item 9a: the Approve toast.
 * "Approved and sent to purchasing" only when the approval was FINAL: the saved request is
 * raised AND no revision is still open (`revision_state` null after the call). A non-final
 * approval, a first one (`pending_approval`) or a revision's (`raised` with
 * `revision_state: 'pending_approval'`), says the plain "Approved" the first-approval path
 * already uses.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));
const approveSpy = vi.hoisted(() => vi.fn());
vi.mock('../services/sparePartRequestService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  approveSparePartRequest: (...a: unknown[]) => approveSpy(...a),
}));

import { useApproveSparePartRequest } from './useSparePartRequest';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function approveReturning(saved: Record<string, unknown>) {
  approveSpy.mockResolvedValue({ id: 'spr-1', ...saved });
  const { result } = renderHook(() => useApproveSparePartRequest('spr-1', null), { wrapper });
  await act(async () => {
    await result.current.mutateAsync(undefined);
  });
  return toast.success.mock.calls.map((c) => c[0]);
}

beforeEach(() => vi.clearAllMocks());

describe('item 9a: the Approve toast names a hand-off only when final', () => {
  it('first approval, final: sent to purchasing', async () => {
    expect(await approveReturning({ state: 'raised', revision_state: null })).toEqual([
      'Approved and sent to purchasing',
    ]);
  });

  it('first approval, another level open: plain Approved', async () => {
    expect(await approveReturning({ state: 'pending_approval', revision_state: null })).toEqual(['Approved']);
  });

  it('revision, another level open: plain Approved, never "sent to purchasing"', async () => {
    expect(await approveReturning({ state: 'raised', revision_state: 'pending_approval' })).toEqual([
      'Approved',
    ]);
  });

  it('revision, final: sent to purchasing', async () => {
    expect(await approveReturning({ state: 'raised', revision_state: null })).toEqual([
      'Approved and sent to purchasing',
    ]);
  });
});
