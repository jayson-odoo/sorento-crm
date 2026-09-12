/**
 * PLAN-portal-price-tag-journey-r8, D-V1 (AC-V1..V4).
 *
 * `PortalVerifyCard.test.tsx` already covers the bootstrap / confirm-identity
 * / link-request states end to end; this file is narrowly about the r8
 * demarcation on the plain OTP card - what stayed, what the owner deleted,
 * and the order the survivors render in.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

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
  fetchSlugInfo,
  fetchTokenInfo,
  requestOtp,
  verifyOtp,
} from '../lib/portal-client';

const mockSlugInfo = vi.mocked(fetchSlugInfo);
const mockTokenInfo = vi.mocked(fetchTokenInfo);
const mockRequestOtp = vi.mocked(requestOtp);
const mockVerifyOtp = vi.mocked(verifyOtp);

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/portal/c/SLUG123456/verify');
  mockRequestOtp.mockResolvedValue({ sent_to: '+60••••1234', expires_at: 'x' });
});

async function renderOtpCard() {
  // returns the RTL render() result
  mockSlugInfo.mockResolvedValue({
    contact_id: 'c1',
    space_id: 's1',
    name: 'Ahmad Tester',
    masked_phone: '+60••••1234',
    whatsapp_number: '60123456789',
  });
  const result = render(<PortalVerifyCard slug="SLUG123456" />);
  await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
  return result;
}

describe('PortalVerifyCard - r8 demarcation (AC-V1)', () => {
  it('renders title, masked line, Not-your-number, code input and Resend, and nothing r8 removed', async () => {
    await renderOtpCard();

    // Survivors.
    expect(screen.getByText('Verify your identity')).toBeInTheDocument();
    expect(
      screen.getByText((_, node) =>
        node?.textContent === "We'll send a code to your WhatsApp +60••••1234",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('not-your-number')).toBeInTheDocument();
    expect(screen.getByLabelText('Verification code')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Resend/ })).toBeInTheDocument();

    // Removed (D-V1): the intro alert, the "Code sent..." line, the "Verify
    // and continue" button, and the WhatsApp escape hatch.
    expect(screen.queryByText(/Verify with a one-time code/i)).toBeNull();
    expect(screen.queryByText(/Code sent\. It expires in 10 minutes/i)).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Verify and continue' }),
    ).toBeNull();
    expect(screen.queryByTestId('wa-escape-hatch')).toBeNull();
    expect(screen.queryByText(/No code after a minute/i)).toBeNull();
  });

  it('renders survivors in order: title, masked line, Not your number, code input, Resend', async () => {
    await renderOtpCard();

    const title = screen.getByText('Verify your identity');
    const maskedLine = screen.getByText((_, node) =>
      node?.textContent === "We'll send a code to your WhatsApp +60••••1234",
    );
    const notYourNumber = screen.getByTestId('not-your-number');
    const codeLabel = screen.getByText('Verification code');
    const resend = screen.getByRole('button', { name: /^Resend/ });

    // DOCUMENT_POSITION_FOLLOWING (4): `a` comes before `b`.
    const FOLLOWING = 4;
    const before = (a: Element, b: Element) =>
      (a.compareDocumentPosition(b) & FOLLOWING) === FOLLOWING;

    expect(before(title, maskedLine)).toBe(true);
    expect(before(maskedLine, notYourNumber)).toBe(true);
    expect(before(notYourNumber, codeLabel)).toBe(true);
    expect(before(codeLabel, resend)).toBe(true);
  });
});

describe('PortalVerifyCard - auto-verify and inline error (AC-V2)', () => {
  it('verifies without a button once the sixth digit lands', async () => {
    await renderOtpCard();
    mockVerifyOtp.mockResolvedValue({ token: 'tok-123' });

    fireEvent.change(screen.getByLabelText('Verification code'), {
      target: { value: '123456' },
    });

    await waitFor(() => expect(mockVerifyOtp).toHaveBeenCalledWith('c1', 's1', '123456'));
  });

  it('a wrong code shows the inline error under the input, not a toast-only failure', async () => {
    await renderOtpCard();
    mockVerifyOtp.mockRejectedValue(new Error('Invalid or expired code.'));

    fireEvent.change(screen.getByLabelText('Verification code'), {
      target: { value: '000000' },
    });

    expect(await screen.findByText('Invalid or expired code.')).toBeInTheDocument();
  });
});

describe('PortalVerifyCard - logout notice survives (AC-V3)', () => {
  it('shows the logged-out alert, the one alert that survives', async () => {
    window.history.pushState({}, '', '/portal/c/SLUG123456/verify?reason=logout');
    mockSlugInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      name: 'Ahmad Tester',
      masked_phone: '+60••••1234',
      whatsapp_number: '60123456789',
    });

    render(<PortalVerifyCard slug="SLUG123456" />);

    expect(
      await screen.findByText('You have been logged out. Verify with an OTP to continue.'),
    ).toBeInTheDocument();
    // Still no intro alert or "Code sent" line alongside it.
    expect(screen.queryByText(/Verify with a one-time code/i)).toBeNull();
    expect(screen.queryByText(/Code sent\. It expires in 10 minutes/i)).toBeNull();
  });
});

describe('PortalVerifyCard - legacy token route (AC-V4)', () => {
  it('has no "Not your number?" link, otherwise matches the AC-V1 layout', async () => {
    window.history.pushState({}, '', '/portal/verify?token=legacy-tok');
    mockTokenInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      name: 'Ahmad Tester',
      masked_phone: '+60••••9999',
      whatsapp_number: '60123456789',
    });

    render(<PortalVerifyCard />);

    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
    expect(screen.getByText('Verify your identity')).toBeInTheDocument();
    expect(screen.getByLabelText('Verification code')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Resend/ })).toBeInTheDocument();
    expect(screen.queryByTestId('not-your-number')).toBeNull();
  });
});
