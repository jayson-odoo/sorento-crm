/**
 * PORTAL-P3-ROLE-MENU round 7, T2: a 401 to a request that carried an impersonation token (this
 * tab's sessionStorage) clears ONLY that token; the admin's own localStorage token and slug
 * survive. A 401 to a normal token clears it as today.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchMe, fetchMeWithGrace, fetchPortalAttachmentBytes, PortalUnauthorizedError } from './portal-client';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  fetchMock.mockResolvedValue({ ok: false, status: 401, json: async () => ({}), text: async () => '' });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function impersonationTab() {
  window.localStorage.setItem(TOKEN_KEY, 'ADMIN-OWN-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'ADMINSLUG01');
  window.sessionStorage.setItem(TOKEN_KEY, 'IMP-TOKEN');
}

describe('portal 401 with an impersonation token (T2)', () => {
  it('portalFetch (fetchMe): only the sessionStorage token is cleared', async () => {
    impersonationTab();
    await expect(fetchMe()).rejects.toBeInstanceOf(PortalUnauthorizedError);
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
  });

  it('attachment bytes fetch: same', async () => {
    impersonationTab();
    await expect(fetchPortalAttachmentBytes('/api/v1/x/download')).rejects.toBeInstanceOf(PortalUnauthorizedError);
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
  });

  it('fetchMeWithGrace after a revoked impersonation token: admin localStorage token still present', async () => {
    impersonationTab();
    await expect(fetchMeWithGrace()).rejects.toBeInstanceOf(PortalUnauthorizedError);
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
  });

  it('normal token 401: the token is cleared as today', async () => {
    window.localStorage.setItem(TOKEN_KEY, 'MY-TOKEN');
    await expect(fetchMe()).rejects.toBeInstanceOf(PortalUnauthorizedError);
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});
