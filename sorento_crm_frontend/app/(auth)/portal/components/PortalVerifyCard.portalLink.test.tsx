/**
 * PORTAL-P1-SESSION-LINK: after the code verifies, the card also opens a CRM session through
 * NextAuth, but ONLY when verify-otp returned a `portal_link_secret` (the contact has a user).
 * A contact without a user sees no NextAuth call at all (AC-2), and a failed sign-in never
 * blocks the portal. The portal token itself is never handed to NextAuth (security review H1).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const signInMock = vi.fn();
vi.mock('next-auth/react', () => ({
  signIn: (...args: unknown[]) => signInMock(...args),
  signOut: vi.fn(),
  getSession: async () => ({ user: { id: 'u1' } }),
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
  signInMock.mockImplementation(async () => {
    calls.push('signIn');
    return { ok: true, error: null, status: 200, url: null };
  });
});

describe('PortalVerifyCard - CRM session from the portal link', () => {
  it('a secret: signs in through phone-otp with the secret (never the portal token), then navigates', async () => {
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).toHaveBeenCalledTimes(1);
    expect(signInMock).toHaveBeenCalledWith('phone-otp', {
      portal_link_secret: 'LINK-SECRET',
      redirect: false,
    });
    // The cookie is set before the page is left.
    expect(calls).toEqual(['signIn', 'assign']);
    // The flag names the signed-in user, so logout only ends that user's session.
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBe('u1');
    // Landing is unchanged in P1: still the portal.
    expect(assignMock.mock.calls[0][0]).toContain('/portal/c/SLUG123456');
  });

  it('no secret (contact without a user): no NextAuth call at all', async () => {
    verifiedWith(undefined);
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
  });

  it('a refused sign-in still opens the portal and sets no flag', async () => {
    signInMock.mockResolvedValue({ ok: false, error: 'refused', status: 401, url: null });
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(window.localStorage.getItem('sorento.portalToken')).toBe('PORTAL-TOKEN');
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
    expect(screen.queryByText(/refused/i)).toBeNull();
  });

  it('a thrown sign-in still opens the portal', async () => {
    signInMock.mockRejectedValue(new Error('network'));
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
  });

  it('token mode: the same secret branch', async () => {
    setUrl('/portal/verify?token=OLDTOKEN');
    mockTokenInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      expires_at: 'x',
      expired: false,
      revoked: false,
      masked_phone: '+60••••1234',
    });
    render(<PortalVerifyCard />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).toHaveBeenCalledWith('phone-otp', {
      portal_link_secret: 'LINK-SECRET',
      redirect: false,
    });
  });
});
