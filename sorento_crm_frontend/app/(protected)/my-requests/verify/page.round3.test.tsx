/**
 * PORTAL-P3-ROLE-MENU round 3: T5 (never stuck) and T6 (no automatic WhatsApp code while an
 * admin is viewing as the salesperson) on `/my-requests/verify`.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/my-requests/verify',
}));

const profile: {
  salesperson: { portalKinds: string[]; portalSlug: string } | null;
  isLoading: boolean;
  isError: boolean;
} = { salesperson: null, isLoading: false, isError: false };
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    ...profile,
    avatarSrc: undefined,
    displayName: '',
    displayEmail: '',
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalVerifyCard', () => ({
  PortalVerifyCard: ({ slug, autoSend }: { slug?: string; autoSend?: boolean }) => (
    <div data-testid="verify-card" data-slug={slug} data-autosend={String(autoSend)} />
  ),
}));

import { impersonationStore } from '@/lib/impersonation-store';
import VerifyPage from './page';

beforeEach(() => {
  vi.clearAllMocks();
  profile.salesperson = { portalKinds: ['stock_inquiry'], portalSlug: 'MYSLUG1234' };
  profile.isLoading = false;
  profile.isError = false;
  impersonationStore.setSession(null);
});
afterEach(() => impersonationStore.setSession(null));

describe('/my-requests/verify never stuck (T5)', () => {
  it('profile loaded, no salesperson: goes to /', async () => {
    profile.salesperson = null;
    render(<VerifyPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'));
    expect(screen.queryByTestId('verify-card')).toBeNull();
  });

  it('profile read failed: goes to /', async () => {
    profile.salesperson = null;
    profile.isError = true;
    render(<VerifyPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'));
  });
});

describe('/my-requests/verify autoSend (T6)', () => {
  it('not impersonating: the card keeps its default (auto request)', () => {
    render(<VerifyPage />);
    expect(screen.getByTestId('verify-card').getAttribute('data-autosend')).not.toBe('false');
  });

  it('an admin viewing as the salesperson: autoSend={false}', () => {
    impersonationStore.setSession({
      sessionId: 'imp-1',
      startedAt: '2026-10-06T00:00:00Z',
      targetUser: { id: 'u-9', name: 'Retail One', email: 'r@x.test', avatar: null, role_name: 'salesperson' },
    });
    render(<VerifyPage />);
    expect(screen.getByTestId('verify-card').getAttribute('data-autosend')).toBe('false');
  });
});
