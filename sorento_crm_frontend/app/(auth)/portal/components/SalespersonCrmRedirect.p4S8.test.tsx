/**
 * PORTAL-P4-REQUESTS S8: a signed-in salesperson (home /my-requests) who opens a
 * portal link, incl. the WhatsApp submission_link, lands on the STAFF page of that request.
 * Anyone else (staff home "/", a portal home) is not moved.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

const getSessionMock = vi.fn();
vi.mock('next-auth/react', () => ({
  getSession: (...a: unknown[]) => getSessionMock(...a),
  useSession: () => ({ data: null, status: 'unauthenticated' }),
  signIn: vi.fn(),
  signOut: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(''),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const replaceMock = vi.fn();
const realLocation = window.location;
function at(path: string) {
  const u = new URL(path, realLocation.origin);
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: u.href, origin: u.origin, pathname: u.pathname, search: u.search, hash: '',
      assign: vi.fn(), replace: (t: string) => replaceMock(t), reload: vi.fn(),
    },
  });
}

import SalespersonCrmRedirect from './SalespersonCrmRedirect';
const settle = () => new Promise((r) => setTimeout(r, 80));

beforeEach(() => {
  vi.clearAllMocks();
  getSessionMock.mockResolvedValue({
    user: { id: 'u1', homePath: '/my-requests' },
  });
});

describe('SalespersonCrmRedirect S8', () => {
  it('WhatsApp rejection link: lands on the staff detail of the request', async () => {
    at('/portal/c/SLUG123456/complaint/abc-123?token=T1');
    render(<SalespersonCrmRedirect />);
    await settle();
    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith('/complaint-management/complaints/abc-123');
  });
  it('plain portal landing with ?type= goes to that staff list', async () => {
    at('/portal/c/SLUG123456?type=sample_request');
    render(<SalespersonCrmRedirect />);
    await settle();
    expect(replaceMock).toHaveBeenCalledWith('/project-sales/sample-requests');
  });
  it.each([['/'], ['/portal/c/SLUG123456'], ['/procurement-management/stock-inquiries']])(
    'a user whose home is %s is not moved (staff / contact stays put)',
    async (home) => {
      getSessionMock.mockResolvedValue({ user: { id: 'u2', homePath: home } });
      at('/portal/c/SLUG123456/complaint/abc-123');
      render(<SalespersonCrmRedirect />);
      await settle();
      expect(replaceMock).not.toHaveBeenCalled();
    },
  );
  it('the verify page has no twin: nobody is moved', async () => {
    at('/portal/c/SLUG123456/verify');
    render(<SalespersonCrmRedirect />);
    await settle();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
