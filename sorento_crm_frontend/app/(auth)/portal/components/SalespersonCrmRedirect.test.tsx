/**
 * PORTAL-P3-ROLE-MENU round 2, B3 (P3-19, P3-20): a signed-in salesperson who opens a portal
 * link on a device that already holds a portal token is sent to the CRM twin of that page.
 * Nobody else is moved.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const getSessionMock = vi.fn();
vi.mock('next-auth/react', () => ({
  getSession: (...a: unknown[]) => getSessionMock(...a),
  useSession: () => ({ data: null, status: 'unauthenticated' }),
  signIn: vi.fn(),
  signOut: vi.fn(),
}));

const loc = { pathname: '/', search: '' };
vi.mock('next/navigation', () => ({
  usePathname: () => loc.pathname,
  useSearchParams: () => new URLSearchParams(loc.search),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const replaceMock = vi.fn();
const realLocation = window.location;

function at(path: string) {
  const u = new URL(path, realLocation.origin);
  loc.pathname = u.pathname;
  loc.search = u.search;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: u.href,
      origin: u.origin,
      pathname: u.pathname,
      search: u.search,
      hash: '',
      assign: vi.fn(),
      replace: (t: string) => replaceMock(t),
      reload: vi.fn(),
    },
  });
}

import SalespersonCrmRedirect from './SalespersonCrmRedirect';

async function settle() {
  await new Promise((r) => setTimeout(r, 60));
}

beforeEach(() => {
  vi.clearAllMocks();
  getSessionMock.mockResolvedValue({ user: { id: 'u1', homePath: '/my-requests' } });
});

describe('SalespersonCrmRedirect', () => {
  it.each([
    ['/portal/c/SLUG123456', '/my-requests'],
    ['/portal/c/SLUG123456?type=complaint', '/my-requests?type=complaint'],
    ['/portal/c/SLUG123456/complaint/abc-123', '/my-requests/complaint/abc-123'],
  ])('salesperson on %s is sent to %s', async (here, to) => {
    at(here);
    render(<SalespersonCrmRedirect />);
    await waitFor(() => expect(replaceMock).toHaveBeenCalledTimes(1));
    expect(replaceMock).toHaveBeenCalledWith(to);
  });

  it.each([
    ['no session', null, '/portal/c/SLUG123456'],
    ['homePath /', { user: { id: 'u', homePath: '/' } }, '/portal/c/SLUG123456'],
    ['a portal homePath', { user: { id: 'u', homePath: '/portal/c/SLUG123456' } }, '/portal/c/SLUG123456'],
    ['a verify path', { user: { id: 'u', homePath: '/my-requests' } }, '/portal/c/SLUG123456/verify'],
    ['a legacy /portal path', { user: { id: 'u', homePath: '/my-requests' } }, '/portal'],
    ['a legacy /portal/verify path', { user: { id: 'u', homePath: '/my-requests' } }, '/portal/verify?token=T'],
  ])('no redirect for %s', async (_n, session, here) => {
    getSessionMock.mockResolvedValue(session);
    at(here);
    render(<SalespersonCrmRedirect />);
    await settle();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
