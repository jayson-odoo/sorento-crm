/**
 * PORTAL-P3-ROLE-MENU round 4, R4: after the stored-slug check passes, MySlug compares the TOKEN's
 * own identity: portal /me `portal_slug` must equal the salesperson's slug from the profile.
 * Differs -> token and slug cleared, /my-requests/verify. Match -> renders. 401 -> verify.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

const fetchMe = vi.fn();
vi.mock('@/app/(auth)/portal/lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/app/(auth)/portal/lib/portal-client')>();
  return { ...original, fetchMeWithGrace: (...a: unknown[]) => fetchMe(...a) };
});

import { PortalUnauthorizedError } from '@/app/(auth)/portal/lib/portal-client';
import { MySlug } from './MySlug';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';

function mount() {
  return render(<MySlug>{(slug) => <div data-testid="child" data-slug={slug} />}</MySlug>);
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  // the stored slug matches, so only the token's own identity is under test
  window.localStorage.setItem(TOKEN_KEY, 'SOME-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'MYSLUG1234');
});

describe('MySlug token identity (R4)', () => {
  it('token belongs to another contact: cleared and sent to verify', async () => {
    fetchMe.mockResolvedValue({ portal_slug: 'OTHERSLUG99' });
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'));
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(SLUG_KEY)).toBeNull();
    expect(screen.queryByTestId('child')).toBeNull();
  });

  it('token belongs to the salesperson: renders and keeps the token', async () => {
    fetchMe.mockResolvedValue({ portal_slug: 'MYSLUG1234' });
    mount();
    expect((await screen.findByTestId('child')).getAttribute('data-slug')).toBe('MYSLUG1234');
    expect(fetchMe).toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('SOME-TOKEN');
  });

  it('fetchMe 401: goes to verify', async () => {
    fetchMe.mockRejectedValue(new PortalUnauthorizedError());
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'));
    expect(screen.queryByTestId('child')).toBeNull();
  });
});
