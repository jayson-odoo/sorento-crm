/**
 * PASSKEY-LOGIN AC-43, AC-45, AC-46: the query/mutation hooks sit between the
 * UI and `services/passkeyService.ts`.
 *
 * Mutation variable shapes (assumed, the brief names only the hooks):
 *   useRenamePasskeyMutation().mutate({ id, name })
 *   useSetUserPasskeyEnabledMutation().mutate({ userId, enabled })
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

const svc = vi.hoisted(() => ({
  fetchMyPasskeys: vi.fn(),
  fetchUserPasskeys: vi.fn(),
  renamePasskey: vi.fn(),
  setUserPasskeyEnabled: vi.fn(),
  fetchPasskeyStatus: vi.fn(),
  fetchPasskeySignInOptions: vi.fn(),
  sendPasskeyReauthCode: vi.fn(),
  fetchPasskeyRegistrationOptions: vi.fn(),
  registerPasskey: vi.fn(),
}));
vi.mock('@/services/passkeyService', () => svc);

import {
  useMyPasskeysQuery,
  useRenamePasskeyMutation,
  useSetUserPasskeyEnabledMutation,
  useUserPasskeysQuery,
} from './usePasskeys';

const PASSKEY = {
  id: 'pk-1',
  name: 'Safari on iPhone',
  created_at: '2026-11-12T09:42:00',
  last_used_at: null,
};

function wrapperWith(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useMyPasskeysQuery', () => {
  it('returns the signed-in user passkeys from fetchMyPasskeys', async () => {
    svc.fetchMyPasskeys.mockResolvedValue([PASSKEY]);
    const { result } = renderHook(() => useMyPasskeysQuery(), {
      wrapper: wrapperWith(newClient()),
    });
    await waitFor(() => expect(result.current.data).toEqual([PASSKEY]));
    expect(svc.fetchMyPasskeys).toHaveBeenCalledTimes(1);
  });

  it('surfaces the service error', async () => {
    svc.fetchMyPasskeys.mockRejectedValue(new Error('Failed to load passkeys'));
    const { result } = renderHook(() => useMyPasskeysQuery(), {
      wrapper: wrapperWith(newClient()),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to load passkeys');
  });
});

describe('useUserPasskeysQuery', () => {
  it('loads the given user passkeys through fetchUserPasskeys(userId)', async () => {
    svc.fetchUserPasskeys.mockResolvedValue([PASSKEY]);
    const { result } = renderHook(() => useUserPasskeysQuery('user-1'), {
      wrapper: wrapperWith(newClient()),
    });
    await waitFor(() => expect(result.current.data).toEqual([PASSKEY]));
    expect(svc.fetchUserPasskeys).toHaveBeenCalledWith('user-1');
  });
});

describe('useRenamePasskeyMutation', () => {
  it('calls renamePasskey(id, name) and refreshes the own list', async () => {
    svc.fetchMyPasskeys.mockResolvedValue([PASSKEY]);
    svc.renamePasskey.mockResolvedValue({ ...PASSKEY, name: 'Work phone' });
    const qc = newClient();
    const { result } = renderHook(
      () => ({ list: useMyPasskeysQuery(), rename: useRenamePasskeyMutation() }),
      { wrapper: wrapperWith(qc) },
    );
    await waitFor(() => expect(result.current.list.data).toBeDefined());
    const callsBefore = svc.fetchMyPasskeys.mock.calls.length;

    await act(async () => {
      await result.current.rename.mutateAsync({ id: 'pk-1', name: 'Work phone' } as never);
    });

    expect(svc.renamePasskey).toHaveBeenCalledWith('pk-1', 'Work phone');
    await waitFor(() =>
      expect(svc.fetchMyPasskeys.mock.calls.length).toBeGreaterThan(callsBefore),
    );
  });

  it('toasts the extracted error message on failure', async () => {
    svc.renamePasskey.mockRejectedValue(new Error('Enter a name.'));
    const { result } = renderHook(() => useRenamePasskeyMutation(), {
      wrapper: wrapperWith(newClient()),
    });
    await act(async () => {
      await result.current.mutateAsync({ id: 'pk-1', name: ' ' } as never).catch(() => null);
    });
    expect(toastError).toHaveBeenCalledWith('Enter a name.');
  });
});

describe('useSetUserPasskeyEnabledMutation', () => {
  it('calls setUserPasskeyEnabled(userId, enabled)', async () => {
    svc.setUserPasskeyEnabled.mockResolvedValue({ user_id: 'user-1', passkey_enabled: true });
    const { result } = renderHook(() => useSetUserPasskeyEnabledMutation(), {
      wrapper: wrapperWith(newClient()),
    });
    await act(async () => {
      await result.current.mutateAsync({ userId: 'user-1', enabled: true } as never);
    });
    expect(svc.setUserPasskeyEnabled).toHaveBeenCalledWith('user-1', true);
  });

  it('toasts the extracted error message on failure', async () => {
    svc.setUserPasskeyEnabled.mockRejectedValue(
      new Error('You do not have permission to edit users.'),
    );
    const { result } = renderHook(() => useSetUserPasskeyEnabledMutation(), {
      wrapper: wrapperWith(newClient()),
    });
    await act(async () => {
      await result.current
        .mutateAsync({ userId: 'user-1', enabled: false } as never)
        .catch(() => null);
    });
    expect(toastError).toHaveBeenCalledWith('You do not have permission to edit users.');
  });
});
