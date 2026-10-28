/**
 * PORTAL-P3-ROLE-MENU round 6, F3 (P3-24, P3-26): MySlug with an impersonation token (sessionStorage)
 * skips the stored-slug compare and never writes the stored slug; the token's /me portal_slug must
 * equal the salesperson's: match renders, mismatch clears ONLY the sessionStorage token and goes to
 * /my-requests/verify. The admin's own localStorage token and slug are never touched.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/my-requests',
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: { portalKinds: ['stock_inquiry'], portalSlug: 'TARGETSLUG' },
    isLoading: false, isError: false,
    avatarSrc: undefined, displayName: '', displayEmail: '',
  }),
}));

import { MySlug } from './MySlug';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  // the admin's own device state, and the impersonation token of this tab
  window.localStorage.setItem(TOKEN_KEY, 'ADMIN-OWN-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'ADMINSLUG01');
  window.sessionStorage.setItem(TOKEN_KEY, 'IMP-TOKEN');
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function me(slug: string) {
  fetchMock.mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ portal_slug: slug }),
    text: async () => '',
  });
}

function mount() {
  return render(<MySlug>{(slug) => <div data-testid="child" data-slug={slug} />}</MySlug>);
}

describe('MySlug under an impersonation token (F3)', () => {
  it('matching identity: renders, stored slug and tokens untouched', async () => {
    me('TARGETSLUG');
    mount();
    expect((await screen.findByTestId('child')).getAttribute('data-slug')).toBe('TARGETSLUG');
    expect(replace).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe('IMP-TOKEN');
  });

  it('mismatching identity: only the sessionStorage token is cleared, then verify', async () => {
    me('SOMEONEELSE');
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'));
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
    expect(screen.queryByTestId('child')).toBeNull();
  });
});
