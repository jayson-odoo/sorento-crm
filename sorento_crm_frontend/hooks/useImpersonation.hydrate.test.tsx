/**
 * PORTAL-IMPERSONATION-ISOLATE (PII-1): the protected shell's hydrate() must never copy the
 * admin's server-side view-as into a tab that did not start it. It only checks the tab's own.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { impersonationStore } from '@/lib/impersonation-store';
import { useImpersonation } from '@/hooks/useImpersonation';

const TARGET = { id: 'u-sales', name: 'Test Salesperson', email: null, avatar: null, role_name: 'salesperson' };
const SERVER_ROW = { session_id: 's1', started_at: '2026-11-05T00:00:00Z', target_user: TARGET };

function current(body: unknown) {
  apiFetch.mockResolvedValue({ ok: true, status: 200, json: async () => body });
}

function mount() {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useImpersonation(), { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
  window.localStorage.clear();
  impersonationStore.setSession(null);
});

describe('hydrate() validates this tab, never adopts', () => {
  it('a tab with no view-as stays the admin even though the server has an open row', async () => {
    current(SERVER_ROW);
    const { result } = mount();
    await act(async () => {
      await result.current.hydrate();
    });
    expect(impersonationStore.getState()).toBeNull();
    expect(result.current.isImpersonating).toBe(false);
  });

  it('a tab whose view-as the server has ended drops it', async () => {
    impersonationStore.setSession({ sessionId: 's1', startedAt: SERVER_ROW.started_at, targetUser: TARGET });
    current(null);
    const { result } = mount();
    await act(async () => {
      await result.current.hydrate();
    });
    expect(impersonationStore.getState()).toBeNull();
  });

  it('a tab whose view-as the server replaced with another target drops it', async () => {
    impersonationStore.setSession({ sessionId: 's0', startedAt: SERVER_ROW.started_at, targetUser: { ...TARGET, id: 'u-other' } });
    current(SERVER_ROW);
    const { result } = mount();
    await act(async () => {
      await result.current.hydrate();
    });
    expect(impersonationStore.getState()).toBeNull();
  });

  it('a tab whose view-as is still open keeps it', async () => {
    impersonationStore.setSession({ sessionId: 's1', startedAt: SERVER_ROW.started_at, targetUser: TARGET });
    current(SERVER_ROW);
    const { result } = mount();
    await act(async () => {
      await result.current.hydrate();
    });
    expect(impersonationStore.getState()?.targetUser.id).toBe('u-sales');
  });

  it('a tab with no view-as does not even ask the server', async () => {
    current(SERVER_ROW);
    const { result } = mount();
    await act(async () => {
      await result.current.hydrate();
    });
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
