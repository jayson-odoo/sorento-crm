/**
 * PORTAL-P3-ROLE-MENU P3-07, P3-08: after the code, a salesperson (NextAuth session homePath under
 * /my-requests) is sent to that path; everyone else, and a failed CRM sign-in, keep today's
 * destination exactly.
 *
 * (header of the P1 suite this was copied from) PORTAL-P1-SESSION-LINK: after the code verifies, the card also opens a CRM session through
 * NextAuth, but ONLY when verify-otp returned a `portal_link_secret` (the contact has a user).
 * A contact without a user sees no NextAuth call at all (AC-2), and a failed sign-in never
 * blocks the portal. The portal token itself is never handed to NextAuth (security review H1).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const signInMock = vi.fn();
const getSessionMock = vi.fn();
vi.mock('next-auth/react', () => ({
  signIn: (...args: unknown[]) => signInMock(...args),
  signOut: vi.fn(),
  getSession: (...args: unknown[]) => getSessionMock(...args),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchSlugInfo: vi.fn(),
    fetchTokenInfo: vi.fn(),
    requestOtp: vi.fn(),
    verifyOtp: vi.fn(),
  };
});

import { impersonationStore } from '@/lib/impersonation-store';
import { PortalVerifyCard } from './PortalVerifyCard';
import {
  CRM_SESSION_FLAG_KEY,
  fetchSlugInfo,
  fetchTokenInfo,
  requestOtp,
  verifyOtp,
} from '../lib/portal-client';

const mockSlugInfo = vi.mocked(fetchSlugInfo);
const mockTokenInfo = vi.mocked(fetchTokenInfo);
const mockRequestOtp = vi.mocked(requestOtp);
const mockVerifyOtp = vi.mocked(verifyOtp);

const assignMock = vi.fn();
const calls: string[] = [];

const SLUG_INFO = {
  contact_id: 'c1',
  space_id: 's1',
  name: 'Contact Name',
  masked_phone: '+60••••1234',
  whatsapp_number: null,
};

function verifiedWith(secret?: string) {
  mockVerifyOtp.mockResolvedValue({
    token: 'PORTAL-TOKEN',
    expires_at: 'x',
    ...(secret ? { portal_link_secret: secret } : {}),
  });
}

async function enterCode() {
  const input = await screen.findByLabelText(/verification code/i);
  fireEvent.change(input, { target: { value: '123456' } });
}

const realLocation = window.location;

/** A plain location stub: jsdom's own `assign` cannot be spied on. */
function setUrl(path: string) {
  const u = new URL(path, realLocation.origin);
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: u.href,
      origin: u.origin,
      pathname: u.pathname,
      search: u.search,
      hash: '',
      assign: (target: string) => {
        calls.push('assign');
        assignMock(target);
      },
      reload: vi.fn(),
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  window.localStorage.clear();
  window.sessionStorage.clear();
  setUrl('/portal/c/SLUG123456/verify');
  mockRequestOtp.mockResolvedValue({ sent_to: '+60••••1234', expires_at: 'x' });
  mockSlugInfo.mockResolvedValue(SLUG_INFO);
  verifiedWith('LINK-SECRET');
  getSessionMock.mockResolvedValue({ user: { id: 'u1' } });
  signInMock.mockImplementation(async () => {
    calls.push('signIn');
    return { ok: true, error: null, status: 200, url: null };
  });
});

function sessionWith(homePath?: string) {
  getSessionMock.mockResolvedValue({ user: { id: 'u1', ...(homePath ? { homePath } : {}) } });
}

describe('PortalVerifyCard - salesperson lands in the CRM shell', () => {
  it('homePath /my-requests: the browser opens the Stock Inquiry staff list', async () => {
    sessionWith('/my-requests');
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(assignMock.mock.calls[0][0]).toBe('/procurement-management/stock-inquiries');
  });

  it.each([
    ['a portal homePath', '/portal/c/SLUG123456'],
    ['the CRM root', '/'],
    ['no homePath', undefined],
  ])('%s: destination is today\'s portal home', async (_n, homePath) => {
    sessionWith(homePath);
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(assignMock.mock.calls[0][0]).toBe('/portal/c/SLUG123456');
  });

  it('contact without a CRM user (no secret): today\'s portal home, no session read decides it', async () => {
    verifiedWith(undefined);
    sessionWith('/my-requests');
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).not.toHaveBeenCalled();
    expect(assignMock.mock.calls[0][0]).toBe('/portal/c/SLUG123456');
  });

  it('CRM sign-in refused: today\'s portal home even if a stale session says /my-requests', async () => {
    signInMock.mockResolvedValue({ ok: false, error: 'refused', status: 401, url: null });
    sessionWith('/my-requests');
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(assignMock.mock.calls[0][0]).toBe('/portal/c/SLUG123456');
  });

  it('CRM sign-in throws: today\'s portal home', async () => {
    signInMock.mockRejectedValue(new Error('network'));
    sessionWith('/my-requests');
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(assignMock.mock.calls[0][0]).toBe('/portal/c/SLUG123456');
  });
});

describe('PortalVerifyCard under a CRM impersonation (round 7, T4)', () => {
  beforeEach(() => {
    impersonationStore.setSession({
      sessionId: 's1',
      startedAt: '2026-10-28T00:00:00Z',
      targetUser: { id: 'u-eric', name: 'Eric', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
    });
  });
  afterEach(() => impersonationStore.setSession(null));

  it('stores the token for this tab only and never replaces the admin CRM session', async () => {
    sessionWith('/my-requests');
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();
    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem('sorento.portalToken')).toBe('PORTAL-TOKEN');
    expect(window.localStorage.getItem('sorento.portalToken')).toBeNull();
    expect(window.localStorage.getItem('sorento.portalSlug')).toBeNull();
  });
});

describe('PortalVerifyCard "Not your number?" (round 8, S2)', () => {
  afterEach(() => impersonationStore.setSession(null));

  it('under a CRM impersonation: the control is not rendered', async () => {
    impersonationStore.setSession({
      sessionId: 's1',
      startedAt: '2026-10-28T00:00:00Z',
      targetUser: { id: 'u-eric', name: 'Eric', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
    });
    render(<PortalVerifyCard slug="SLUG123456" />);
    await screen.findByLabelText(/verification code/i);
    expect(screen.queryByTestId('not-your-number')).toBeNull();
  });

  it('outside impersonation: the control is there', async () => {
    render(<PortalVerifyCard slug="SLUG123456" />);
    await screen.findByLabelText(/verification code/i);
    expect(screen.getByTestId('not-your-number')).toBeInTheDocument();
  });
});
