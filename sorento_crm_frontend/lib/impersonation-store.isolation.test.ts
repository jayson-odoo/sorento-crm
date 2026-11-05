/**
 * PORTAL-IMPERSONATION-ISOLATE (PII-1, PII-2): the view-as lives in the tab that started it.
 * sessionStorage is per tab; localStorage is shared by every tab of the browser, so a view-as kept
 * there turned the admin's whole account into the target.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const KEY = 'impersonation-session-v1';
const VIEW_AS = {
  sessionId: 's1',
  startedAt: '2026-11-05T00:00:00Z',
  targetUser: { id: 'u-sales', name: 'Test Salesperson', email: null, avatar: null, role_name: 'salesperson' },
};

async function load() {
  vi.resetModules();
  return import('@/lib/impersonation-store');
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('impersonation store is tab-scoped', () => {
  it('a started view-as is written to sessionStorage, never localStorage', async () => {
    const { impersonationStore } = await load();
    impersonationStore.setSession(VIEW_AS);
    expect(JSON.parse(window.sessionStorage.getItem(KEY) || 'null')?.targetUser.id).toBe('u-sales');
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it('a reload of the same tab keeps its view-as (PII-2)', async () => {
    window.sessionStorage.setItem(KEY, JSON.stringify(VIEW_AS));
    const { impersonationStore } = await load();
    expect(impersonationStore.getState()?.targetUser.id).toBe('u-sales');
  });

  it('a view-as another tab left in localStorage is not adopted, and is removed', async () => {
    window.localStorage.setItem(KEY, JSON.stringify(VIEW_AS));
    const { impersonationStore } = await load();
    expect(impersonationStore.getState()).toBeNull();
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it('ending clears this tab only', async () => {
    const { impersonationStore } = await load();
    impersonationStore.setSession(VIEW_AS);
    impersonationStore.setSession(null);
    expect(window.sessionStorage.getItem(KEY)).toBeNull();
    expect(impersonationStore.getState()).toBeNull();
  });
});
