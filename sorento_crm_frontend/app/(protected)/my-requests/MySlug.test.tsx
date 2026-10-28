/**
 * PORTAL-P3-ROLE-MENU round 3, T4 + T5: the CRM wrapper of the portal pages.
 * T4 shared device: a portal token that belongs to someone else (stored slug missing or different
 * from the signed-in salesperson's) is dropped and the visitor goes to the code step.
 * T5 never stuck: no salesperson (or a failed profile read) leaves the page instead of an endless
 * skeleton.
 *
 * The profile hook is mocked with `salesperson`, `isLoading` and `isError`.
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

const profile: {
  salesperson: { portalKinds: string[]; portalSlug: string } | null;
  isLoading: boolean;
  isError: boolean;
} = { salesperson: null, isLoading: false, isError: false };
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    ...profile,
    avatarSrc: undefined,
    displayName: '',
    displayEmail: '',
  }),
}));

vi.mock('@/app/(auth)/portal/lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/app/(auth)/portal/lib/portal-client')>();
  return { ...original, fetchMeWithGrace: vi.fn(async () => ({ portal_slug: 'MYSLUG1234' })) };
});

import { MySlug } from './MySlug';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const MINE = { portalKinds: ['stock_inquiry'], portalSlug: 'MYSLUG1234' };

function mount() {
  return render(<MySlug>{(slug) => <div data-testid="child" data-slug={slug} />}</MySlug>);
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/my-requests');
  profile.salesperson = MINE;
  profile.isLoading = false;
  profile.isError = false;
});

describe('MySlug shared-device guard (T4)', () => {
  it('stored slug differs: token and slug are cleared and the visitor goes to /my-requests/verify', async () => {
    window.localStorage.setItem(TOKEN_KEY, 'OTHER-TOKEN');
    window.localStorage.setItem(SLUG_KEY, 'OTHERSLUG99');
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'));
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(SLUG_KEY)).toBeNull();
    expect(screen.queryByTestId('child')).toBeNull();
  });

  it('token but no stored slug: same', async () => {
    window.localStorage.setItem(TOKEN_KEY, 'OTHER-TOKEN');
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'));
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(screen.queryByTestId('child')).toBeNull();
  });

  it('matching slug: renders the child with the slug and leaves the token alone', async () => {
    window.localStorage.setItem(TOKEN_KEY, 'MY-TOKEN');
    window.localStorage.setItem(SLUG_KEY, 'MYSLUG1234');
    mount();
    expect((await screen.findByTestId('child')).getAttribute('data-slug')).toBe('MYSLUG1234');
    expect(replace).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('MY-TOKEN');
  });
});

describe('MySlug never stuck (T5)', () => {
  beforeEach(() => {
    // a token that matches, so only the profile state is under test
    window.localStorage.setItem(TOKEN_KEY, 'MY-TOKEN');
    window.localStorage.setItem(SLUG_KEY, 'MYSLUG1234');
  });

  it('profile loaded, no salesperson: goes to /', async () => {
    profile.salesperson = null;
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'));
    expect(screen.queryByTestId('child')).toBeNull();
  });

  it('profile read failed: goes to /', async () => {
    profile.salesperson = null;
    profile.isError = true;
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'));
  });

  it('profile still loading: waits, no navigation', async () => {
    profile.salesperson = null;
    profile.isLoading = true;
    mount();
    await new Promise((r) => setTimeout(r, 80));
    expect(replace).not.toHaveBeenCalled();
  });
});
