/**
 * PORTAL-P1-SESSION-LINK: after the code verifies, the card also opens a CRM session through
 * NextAuth, but ONLY when slug-info / token-info says the contact has a user. A contact without
 * a user sees no NextAuth call at all (AC-2), and a failed sign-in never blocks the portal.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const signInMock = vi.fn();
vi.mock('next-auth/react', () => ({
  signIn: (...args: unknown[]) => signInMock(...args),
  signOut: vi.fn(),
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

function slugInfo(hasUser: boolean | undefined) {
  return {
    contact_id: 'c1',
    space_id: 's1',
    name: 'Contact Name',
    masked_phone: '+60••••1234',
    whatsapp_number: null,
    ...(hasUser === undefined ? {} : { has_user: hasUser }),
  };
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
  mockVerifyOtp.mockResolvedValue({ token: 'PORTAL-TOKEN', expires_at: 'x' });
  signInMock.mockImplementation(async () => {
    calls.push('signIn');
    return { ok: true, error: null, status: 200, url: null };
  });
});

describe('PortalVerifyCard - CRM session from the portal link', () => {
  it('has_user: signs in through phone-otp with the portal token, then navigates', async () => {
    mockSlugInfo.mockResolvedValue(slugInfo(true));
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).toHaveBeenCalledTimes(1);
    expect(signInMock).toHaveBeenCalledWith('phone-otp', {
      portal_token: 'PORTAL-TOKEN',
      redirect: false,
    });
    // The cookie is set before the page is left.
    expect(calls).toEqual(['signIn', 'assign']);
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBe('1');
    // Landing is unchanged in P1: still the portal.
    expect(assignMock.mock.calls[0][0]).toContain('/portal/c/SLUG123456');
  });

  it.each([false, undefined])('has_user=%s: no NextAuth call at all', async (hasUser) => {
    mockSlugInfo.mockResolvedValue(slugInfo(hasUser));
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
  });

  it('a refused sign-in still opens the portal and sets no flag', async () => {
    mockSlugInfo.mockResolvedValue(slugInfo(true));
    signInMock.mockResolvedValue({ ok: false, error: 'refused', status: 401, url: null });
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(window.localStorage.getItem('sorento.portalToken') ?? 'set').toBeTruthy();
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
    expect(screen.queryByText(/refused/i)).toBeNull();
  });

  it('a thrown sign-in still opens the portal', async () => {
    mockSlugInfo.mockResolvedValue(slugInfo(true));
    signInMock.mockRejectedValue(new Error('network'));
    render(<PortalVerifyCard slug="SLUG123456" />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(window.localStorage.getItem(CRM_SESSION_FLAG_KEY)).toBeNull();
  });

  it('token mode reads has_user from token-info', async () => {
    setUrl('/portal/verify?token=OLDTOKEN');
    mockTokenInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      expires_at: 'x',
      expired: false,
      revoked: false,
      masked_phone: '+60••••1234',
      has_user: true,
    });
    render(<PortalVerifyCard />);
    await enterCode();

    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    expect(signInMock).toHaveBeenCalledWith('phone-otp', {
      portal_token: 'PORTAL-TOKEN',
      redirect: false,
    });
  });
});
