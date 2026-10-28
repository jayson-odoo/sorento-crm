/**
 * PORTAL-P3-ROLE-MENU round 2, C2 (P3-21): `/my-requests` with no portal token on this device
 * sends the salesperson to the WhatsApp code once; with a token it shows the embedded landing.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const replace = vi.fn();
const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/my-requests',
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: { portalKinds: ['stock_inquiry'], portalSlug: 'MYSLUG1234' },
    isLoading: false,
    isError: false,
    avatarSrc: undefined,
    displayName: '',
    displayEmail: '',
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalLanding', () => ({
  PortalLanding: () => <div data-testid="landing" />,
}));

const token: { value: string | null } = { value: null };
vi.mock('@/app/(auth)/portal/lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/app/(auth)/portal/lib/portal-client')>();
  return { ...original, readPortalToken: () => token.value };
});

import MyRequestsPage from './page';

const assign = vi.fn();
const realLocation = window.location;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: realLocation.href,
      origin: realLocation.origin,
      pathname: '/my-requests',
      search: '',
      hash: '',
      assign: (t: string) => assign(t),
      replace: (t: string) => assign(t),
      reload: vi.fn(),
    },
  });
});

function navigatedTo(): string[] {
  return [...replace.mock.calls, ...push.mock.calls, ...assign.mock.calls].map((c) => String(c[0]));
}

describe('/my-requests landing without and with a portal token', () => {
  it('no portal token: goes to /my-requests/verify and shows no landing', async () => {
    token.value = null;
    render(<MyRequestsPage />);
    await waitFor(() => expect(navigatedTo()).toContain('/my-requests/verify'));
    expect(screen.queryByTestId('landing')).toBeNull();
  });

  it('with a portal token: the embedded landing renders and nothing navigates', async () => {
    token.value = 'PORTAL-TOKEN';
    window.localStorage.setItem('sorento.portalSlug', 'MYSLUG1234');
    render(<MyRequestsPage />);
    expect(await screen.findByTestId('landing')).toBeInTheDocument();
    expect(navigatedTo()).toEqual([]);
  });
});
