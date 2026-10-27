/**
 * PORTAL-P1-SESSION-LINK AC-5: portal Log out also ends the CRM session the verify card
 * opened (revokes the FastAPI row, then NextAuth signOut) - and does nothing extra for a
 * contact the card never signed in.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const signOutMock = vi.fn();
vi.mock('next-auth/react', () => ({
  signIn: vi.fn(),
  signOut: (...args: unknown[]) => signOutMock(...args),
}));

const revokeMock = vi.fn();
const clearTokenMock = vi.fn();
vi.mock('@/lib/api', () => ({
  revokeCurrentSession: (...args: unknown[]) => revokeMock(...args),
  clearCachedAuthToken: (...args: unknown[]) => clearTokenMock(...args),
}));

import { CRM_SESSION_FLAG_KEY, portalLogout, writePortalToken } from './portal-client';

const fetchMock = vi.fn();
const order: string[] = [];

beforeEach(() => {
  vi.clearAllMocks();
  order.length = 0;
  window.localStorage.clear();
  window.sessionStorage.clear();
  fetchMock.mockImplementation(async () => {
    order.push('portal-logout');
    return new Response(null, { status: 204 });
  });
  vi.stubGlobal('fetch', fetchMock);
  revokeMock.mockImplementation(async () => order.push('revoke'));
  signOutMock.mockImplementation(async () => order.push('signOut'));
});

describe('portalLogout', () => {
  it('with the flag: revokes the CRM session, signs NextAuth out, clears the flag, revokes the portal token', async () => {
    writePortalToken('PT');
    window.localStorage.setItem(CRM_SESSION_FLAG_KEY, '1');
    await portalLogout();

    expect(revokeMock).toHaveBeenCalledTimes(1);
    expect(clearTokenMock).toHaveBeenCalledTimes(1);
    expect(signOutMock).toHaveBeenCalledWith({ redirect: false });
    expect(order.indexOf('revoke')).toBeLessThan(order.indexOf('signOut'));
    expect(order).toContain('portal-logout');
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
  });

  it('without the flag: only the portal token is revoked (trace unchanged)', async () => {
    writePortalToken('PT');
    await portalLogout();

    expect(revokeMock).not.toHaveBeenCalled();
    expect(signOutMock).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/public/portal/logout');
  });

  it('a failing CRM sign-out never blocks the portal logout', async () => {
    writePortalToken('PT');
    window.localStorage.setItem(CRM_SESSION_FLAG_KEY, '1');
    signOutMock.mockRejectedValue(new Error('boom'));
    await portalLogout();

    expect(order).toContain('portal-logout');
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
  });
});
