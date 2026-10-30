/**
 * PORTAL-P4-REQUESTS S8: `/my-requests` is a redirect to the starred form's staff list, else Stock Inquiry.
 * Waits for the profile before choosing (the star is keyed by the contact).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/my-requests',
}));
const profile = { isLoading: false, salesperson: { portalKinds: [], portalSlug: 'S1', contactId: 'c-1' } as unknown };
vi.mock('@/hooks/useAccountProfileForHeader', () => ({ useAccountProfileForHeader: () => profile }));

import MyRequestsPage from './page';

beforeEach(() => {
  replace.mockClear();
  window.localStorage.clear();
  profile.isLoading = false;
});

describe('/my-requests landing redirect', () => {
  it('waits while the profile loads', async () => {
    profile.isLoading = true;
    render(<MyRequestsPage />);
    await new Promise((r) => setTimeout(r, 20));
    expect(replace).not.toHaveBeenCalled();
  });
  it('a starred kind goes to its staff list', async () => {
    window.localStorage.setItem('sorento.portalDefaultTab.c-1', 'sample_request');
    render(<MyRequestsPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/project-sales/sample-requests'));
  });
  it('no star goes to Stock Inquiry', async () => {
    render(<MyRequestsPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/procurement-management/stock-inquiries'));
  });
});
