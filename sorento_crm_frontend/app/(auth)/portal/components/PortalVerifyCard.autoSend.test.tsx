/**
 * PORTAL-P3-ROLE-MENU round 3 T6: after the code, a salesperson (NextAuth session homePath under
 * /my-requests) is sent to that path; everyone else, and a failed CRM sign-in, keep today's
 * destination exactly.
 *
 * (header of the P1 suite this was copied from) PORTAL-P1-SESSION-LINK: after the code verifies, the card also opens a CRM session through
 * NextAuth, but ONLY when verify-otp returned a `portal_link_secret` (the contact has a user).
 * A contact without a user sees no NextAuth call at all (AC-2), and a failed sign-in never
 * blocks the portal. The portal token itself is never handed to NextAuth (security review H1).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

describe('PortalVerifyCard autoSend (PORTAL-P3-ROLE-MENU round 3, T6)', () => {
  it('default: requests a code on mount, as today', async () => {
    render(<PortalVerifyCard slug="SLUG123456" />);
    await screen.findByLabelText(/verification code/i);
    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
  });

  it('autoSend={false}: no code is requested on mount', async () => {
    render(<PortalVerifyCard slug="SLUG123456" {...({ autoSend: false } as object)} />);
    await screen.findByLabelText(/verification code/i);
    await new Promise((r) => setTimeout(r, 100));
    expect(mockRequestOtp).not.toHaveBeenCalled();
  });

  it('autoSend={false}: the Send button still sends one', async () => {
    render(<PortalVerifyCard slug="SLUG123456" {...({ autoSend: false } as object)} />);
    await screen.findByLabelText(/verification code/i);
    fireEvent.click(await screen.findByRole('button', { name: /send|resend/i }));
    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
  });
});
