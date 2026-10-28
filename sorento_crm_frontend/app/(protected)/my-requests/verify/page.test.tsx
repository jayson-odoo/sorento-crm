/**
 * PORTAL-P3-ROLE-MENU round 2, C1 (P3-21): inside the CRM, the verify page renders the existing
 * PortalVerifyCard with the signed-in salesperson's portal slug from /users/me.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const profile: { salesperson: { portalKinds: string[]; portalSlug: string } | null } = {
  salesperson: { portalKinds: ['stock_inquiry'], portalSlug: 'MYSLUG1234' },
};
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: profile.salesperson,
    avatarSrc: undefined,
    displayName: '',
    displayEmail: '',
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalVerifyCard', () => ({
  PortalVerifyCard: ({ slug }: { slug?: string }) => <div data-testid="verify-card" data-slug={slug} />,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/my-requests/verify',
}));

import VerifyPage from './page';

describe('/my-requests/verify', () => {
  it('renders the verify card with the salesperson slug', () => {
    profile.salesperson = { portalKinds: ['stock_inquiry'], portalSlug: 'MYSLUG1234' };
    render(<VerifyPage />);
    expect(screen.getByTestId('verify-card').getAttribute('data-slug')).toBe('MYSLUG1234');
  });

  it('renders no card until the slug is known', () => {
    profile.salesperson = null;
    render(<VerifyPage />);
    expect(screen.queryByTestId('verify-card')).toBeNull();
  });
});
