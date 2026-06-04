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
import { fetchSlugInfo, requestOtp } from '../lib/portal-client';

const mockSlugInfo = vi.mocked(fetchSlugInfo);
const mockRequestOtp = vi.mocked(requestOtp);

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/portal/c/SLUG123456/verify');
});

describe('PortalVerifyCard — slug mode', () => {
  it('renders OTP state with masked phone + wa.me hatch, auto-fires OTP', async () => {
    mockSlugInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      masked_phone: '+60••••1234',
      whatsapp_number: '60123456789',
    });
    mockRequestOtp.mockResolvedValue({ sent_to: '+60••••1234', expires_at: 'x' });

    render(<PortalVerifyCard slug="SLUG123456" />);

    await waitFor(() => expect(screen.getByText(/\+60••••1234/)).toBeTruthy());
    // Auto-fire happened once
    await waitFor(() => expect(mockRequestOtp).toHaveBeenCalledTimes(1));
    // Escape hatch present with the wa.me link
    const hatch = screen.getByTestId('wa-escape-hatch');
    const link = hatch.querySelector('a');
    expect(link?.getAttribute('href')).toContain('wa.me/60123456789');
    // "Not your number?" available on the slug tree
    expect(screen.getByTestId('not-your-number')).toBeTruthy();
  });

  it('hides the wa.me hatch when no business number is configured', async () => {
    mockSlugInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      masked_phone: '+60••••1234',
      whatsapp_number: null,
    });
    mockRequestOtp.mockResolvedValue({ sent_to: '+60••••1234', expires_at: 'x' });

    render(<PortalVerifyCard slug="SLUG123456" />);
    await waitFor(() => expect(screen.getByText(/\+60••••1234/)).toBeTruthy());
    expect(screen.queryByTestId('wa-escape-hatch')).toBeNull();
  });

  it('renders the link-request CTA for an unknown slug (404)', async () => {
    mockSlugInfo.mockResolvedValue(null);

    render(<PortalVerifyCard slug="UNKNOWN999" />);
    await waitFor(() =>
      expect(screen.getByText('This portal link is not recognized.')).toBeTruthy(),
    );
    expect(mockRequestOtp).not.toHaveBeenCalled();
  });

  it('does not auto-fire after logout', async () => {
    window.history.pushState({}, '', '/portal/c/SLUG123456/verify?reason=logout');
    mockSlugInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      masked_phone: '+60••••1234',
      whatsapp_number: '60123456789',
    });

    render(<PortalVerifyCard slug="SLUG123456" />);
    await waitFor(() =>
      expect(screen.getByText(/logged out/i)).toBeTruthy(),
    );
    expect(mockRequestOtp).not.toHaveBeenCalled();
    // Manual send still available
    expect(screen.getByRole('button', { name: 'Send code' })).toBeTruthy();
  });

  it('"Not your number?" clears stored identity and shows link-request CTA', async () => {
    window.history.pushState({}, '', '/portal/c/SLUG123456/verify?reason=logout');
    window.localStorage.setItem('sorento.portalSlug', 'SLUG123456');
    window.localStorage.setItem('sorento.portalToken', 'tok');
    mockSlugInfo.mockResolvedValue({
      contact_id: 'c1',
      space_id: 's1',
      masked_phone: '+60••••1234',
      whatsapp_number: '60123456789',
    });

    render(<PortalVerifyCard slug="SLUG123456" />);
    await waitFor(() => expect(screen.getByTestId('not-your-number')).toBeTruthy());
    fireEvent.click(screen.getByTestId('not-your-number'));

    await waitFor(() =>
      expect(screen.getByText('No portal session on this device.')).toBeTruthy(),
    );
    expect(window.localStorage.getItem('sorento.portalSlug')).toBeNull();
    expect(window.localStorage.getItem('sorento.portalToken')).toBeNull();
    expect(screen.getByTestId('wa-request-link')).toBeTruthy();
  });
});

describe('PortalVerifyCard — legacy mode', () => {
  it('shows the link-request CTA when no token exists anywhere', async () => {
    window.history.pushState({}, '', '/portal/verify');
    render(<PortalVerifyCard />);
    await waitFor(() =>
      expect(screen.getByText('No portal session on this device.')).toBeTruthy(),
    );
  });
});
