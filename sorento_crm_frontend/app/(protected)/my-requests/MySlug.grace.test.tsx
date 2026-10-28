/**
 * PORTAL-P3-ROLE-MENU round 5, F1: MySlug reads the portal /me through the post-verify grace
 * retry. A fresh token whose first /me answers 401 and then 200 with the matching slug renders
 * the child and keeps the token. A persistent 401 still goes to verify.
 * Only global fetch is mocked, so the real fetchMeWithGrace runs.
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
    salesperson: { portalKinds: ['stock_inquiry'], portalSlug: 'MYSLUG1234' },
    isLoading: false, isError: false,
    avatarSrc: undefined, displayName: '', displayEmail: '',
  }),
}));

import { MySlug } from './MySlug';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const fetchMock = vi.fn();

function res(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body) };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem(TOKEN_KEY, 'FRESH-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'MYSLUG1234');
  window.sessionStorage.setItem('sorento.portalTokenWrittenAt', String(Date.now()));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  return render(<MySlug>{(slug) => <div data-testid="child" data-slug={slug} />}</MySlug>);
}

describe('MySlug grace fetch (F1)', () => {
  it('fresh token: 401 then 200 with the matching slug renders the child and keeps the token', async () => {
    fetchMock
      .mockResolvedValueOnce(res(401, { detail: 'expired' }))
      .mockResolvedValue(res(200, { portal_slug: 'MYSLUG1234' }));
    mount();
    expect(await screen.findByTestId('child', {}, { timeout: 4000 })).toBeTruthy();
    expect(replace).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('FRESH-TOKEN');
  });

  it('persistent 401: goes to verify', async () => {
    fetchMock.mockResolvedValue(res(401, { detail: 'expired' }));
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'), { timeout: 4000 });
    expect(screen.queryByTestId('child')).toBeNull();
  });
});
