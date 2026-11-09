/**
 * COMBO-RENAME: the real hook + service path a rename takes. The component suites mock the
 * hook, so this is what pins that a refusal carries its HTTP status (the card reads 409 as
 * "Another combo on this product already has this name") and that a refused rename is not
 * toasted on top of the message under the input. A refused price write still toasts.
 */
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.hoisted(() => vi.fn());
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock('@/lib/api', () => ({ apiFetch }));
vi.mock('@/lib/toast', () => ({ toast }));
vi.mock('@/hooks/useDeferredRowAction', () => ({ useDeferredRowAction: vi.fn() }));

import { useUpdateProductCombo } from './useProductCombos';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function refusal(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useUpdateProductCombo, rename refusals', () => {
  it('a taken name rejects with status 409 and raises no toast', async () => {
    apiFetch.mockResolvedValue(
      refusal(409, { message: 'This product already has a combo called "3 in 1"', code: 'COMBO_NAME_TAKEN' }),
    );
    const { result } = renderHook(() => useUpdateProductCombo('prod-1'), { wrapper: wrapper() });

    let caught: (Error & { status?: number }) | undefined;
    await act(async () => {
      await result.current
        .mutateAsync({ comboId: 'combo-3', write: { name: '3 in 1' } })
        .catch((error) => (caught = error));
    });

    expect(caught?.status).toBe(409);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('a refused price write still toasts', async () => {
    apiFetch.mockResolvedValue(refusal(422, { detail: 'Bad price' }));
    const { result } = renderHook(() => useUpdateProductCombo('prod-1'), { wrapper: wrapper() });

    await act(async () => {
      await result.current
        .mutateAsync({ comboId: 'combo-3', write: { list_price: -1 } })
        .catch(() => undefined);
    });

    expect(toast.error).toHaveBeenCalledWith('Bad price');
  });
});
