/**
 * SIGNIN-2FA-NOT-ROLE AC-10 / AC-11: the verify card never sends a code on its own.
 *
 * Slug mode and token mode both: after the identity lookup resolves, no request-otp call is
 * made; the masked number and a "Send code" button are shown. Pressing it makes exactly one
 * request-otp call and the code field is there to type into, with Resend on its 60 s cooldown.
 * A reload (re-mount) sends nothing either. There is no `autoSend` prop any more.
 *
 * Contract: documentation/plans/identity/signin-2fa-not-role-14nov-acceptance-criteria.md
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const getSessionMock = vi.fn();
vi.mock('next-auth/react', () => ({
  signIn: vi.fn(),
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
import { fetchSlugInfo, fetchTokenInfo, requestOtp } from '../lib/portal-client';

const mockSlugInfo = vi.mocked(fetchSlugInfo);
const mockTokenInfo = vi.mocked(fetchTokenInfo);
const mockRequestOtp = vi.mocked(requestOtp);

const MASKED = '+60••••1234';

const SLUG_INFO = {
  contact_id: 'c1',
  space_id: 's1',
  name: 'Ahmad Tester',
  masked_phone: MASKED,
  whatsapp_number: '60123456789',
};

const TOKEN_INFO = {
  contact_id: 'c2',
  space_id: 's2',
  expires_at: '2026-01-02T00:00:00Z',
  expired: true,
  revoked: false,
  name: 'Legacy Tester',
  masked_phone: MASKED,
  whatsapp_number: '60123456789',
};

/** Lookup resolved and the card has settled: the masked number is on screen. */
async function settled() {
  await screen.findByText(new RegExp(MASKED.replace('+', '\\+')));
  // Give any mount-time effect a chance to fire a send before we assert it did not.
  await new Promise((r) => setTimeout(r, 100));
}

function sendButton() {
  return screen.getByRole('button', { name: /^send code$/i });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/portal/c/SLUG123456/verify');
  mockSlugInfo.mockResolvedValue(SLUG_INFO);
  mockTokenInfo.mockResolvedValue(TOKEN_INFO);
  mockRequestOtp.mockResolvedValue({ sent_to: MASKED, expires_at: 'x' });
  getSessionMock.mockResolvedValue(null);
});

describe('PortalVerifyCard - no auto-send (AC-10, slug mode)', () => {
  it('makes no request-otp call on mount; shows the masked number and a Send code button', async () => {
    render(<PortalVerifyCard slug="SLUG123456" />);
    await settled();

    expect(mockRequestOtp).not.toHaveBeenCalled();
    expect(sendButton()).toBeInTheDocument();
    expect(sendButton()).toBeEnabled();
  });

  it('pressing Send code makes exactly one request-otp call and shows the code field on cooldown', async () => {
    render(<PortalVerifyCard slug="SLUG123456" />);
    await settled();
    expect(mockRequestOtp).not.toHaveBeenCalled();

    fireEvent.click(sendButton());

    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
    expect(mockRequestOtp).toHaveBeenCalledWith('c1', 's1');
    expect(await screen.findByLabelText(/verification code/i)).toBeInTheDocument();
    // Resend keeps the 60 s cooldown.
    const resend = await screen.findByRole('button', { name: /resend in \d+s/i });
    expect(resend).toBeDisabled();

    await new Promise((r) => setTimeout(r, 100));
    expect(mockRequestOtp).toHaveBeenCalledTimes(1);
  });

  it('a reload (re-mount) does not send either', async () => {
    const first = render(<PortalVerifyCard slug="SLUG123456" />);
    await settled();
    expect(mockRequestOtp).not.toHaveBeenCalled();
    first.unmount();

    render(<PortalVerifyCard slug="SLUG123456" />);
    await settled();
    expect(mockRequestOtp).not.toHaveBeenCalled();
    expect(sendButton()).toBeInTheDocument();
  });

  it('a reload after a pressed send does not send again', async () => {
    const first = render(<PortalVerifyCard slug="SLUG123456" />);
    await settled();
    expect(mockRequestOtp).not.toHaveBeenCalled();
    fireEvent.click(sendButton());
    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
    first.unmount();

    render(<PortalVerifyCard slug="SLUG123456" />);
    await settled();
    expect(mockRequestOtp).toHaveBeenCalledTimes(1);
  });
});

describe('PortalVerifyCard - no auto-send (AC-10, token mode)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/portal/verify?token=LEGACY-TOK');
  });

  it('makes no request-otp call on mount; shows the masked number and a Send code button', async () => {
    render(<PortalVerifyCard />);
    await settled();

    expect(mockTokenInfo).toHaveBeenCalled();
    expect(mockRequestOtp).not.toHaveBeenCalled();
    expect(sendButton()).toBeInTheDocument();
  });

  it('pressing Send code makes exactly one request-otp call and shows the code field', async () => {
    render(<PortalVerifyCard />);
    await settled();
    expect(mockRequestOtp).not.toHaveBeenCalled();

    fireEvent.click(sendButton());

    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
    expect(mockRequestOtp).toHaveBeenCalledWith('c2', 's2');
    expect(await screen.findByLabelText(/verification code/i)).toBeInTheDocument();
  });

  it('a reload (re-mount) does not send', async () => {
    const first = render(<PortalVerifyCard />);
    await settled();
    first.unmount();

    render(<PortalVerifyCard />);
    await settled();
    expect(mockRequestOtp).not.toHaveBeenCalled();
  });
});
