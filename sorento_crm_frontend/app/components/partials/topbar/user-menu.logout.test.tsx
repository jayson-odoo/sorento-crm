/**
 * PORTAL-P3-ROLE-MENU round 4, R2: CRM Logout from the user menu also ends the portal session on
 * this device: best-effort portalLogout(), then the portal token and slug are cleared even when
 * portalLogout rejects, and the CRM sign-out is never blocked by it. Both menu variants.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const signOut = vi.fn();
vi.mock('next-auth/react', () => ({
  signOut: (...a: unknown[]) => signOut(...a),
  useSession: () => ({ data: { user: { name: 'S', email: 's@x.test' } }, status: 'authenticated' }),
}));
vi.mock('next-themes', () => ({ useTheme: () => ({ theme: 'light', setTheme: vi.fn() }) }));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
vi.mock('@/lib/api', () => ({
  clearCachedAuthToken: vi.fn(),
  revokeCurrentSession: vi.fn(async () => {}),
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: null, isLoading: false, isError: false,
    avatarSrc: undefined, displayName: 'S', displayEmail: 's@x.test',
  }),
}));
vi.mock('@/providers/i18n-provider', () => ({
  useLanguage: () => ({ changeLanguage: vi.fn(), language: { code: 'en' } }),
}));
vi.mock('@/components/upload-activity/UploadManagerContext', () => ({
  useUploadManager: () => ({ setDrawerOpen: vi.fn() }),
}));
vi.mock('@/components/upload-activity/useUploadActivity', () => ({
  useUploadActivity: () => ({ badgeCount: 0 }),
}));
vi.mock('@/components/my-downloads/MyDownloadsContext', () => ({
  useMyDownloads: () => ({ setOpen: vi.fn(), badgeCount: 0 }),
}));
vi.mock('@/components/ui/dropdown-menu', () => {
  const P = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    DropdownMenu: P, DropdownMenuContent: P, DropdownMenuItem: P, DropdownMenuRadioGroup: P,
    DropdownMenuRadioItem: P, DropdownMenuSeparator: P, DropdownMenuSub: P,
    DropdownMenuSubContent: P, DropdownMenuSubTrigger: P, DropdownMenuTrigger: P,
  };
});

const portalLogout = vi.fn();
vi.mock('@/app/(auth)/portal/lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/app/(auth)/portal/lib/portal-client')>();
  return { ...original, portalLogout: (...a: unknown[]) => portalLogout(...a) };
});

import { UserDropdownMenu } from './user-dropdown-menu';
import { DropdownMenuUser } from './dropdown-menu-user';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem(TOKEN_KEY, 'PORTAL-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'NT8D6BFC45');
});

describe.each([
  ['UserDropdownMenu', UserDropdownMenu],
  ['DropdownMenuUser', DropdownMenuUser],
])('%s Logout ends the portal session too', (_name, Menu) => {
  it('calls portalLogout, clears token and slug, and signs out of the CRM', async () => {
    portalLogout.mockResolvedValue(undefined);
    render(<Menu trigger={<button>t</button>} />);
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    await waitFor(() => expect(signOut).toHaveBeenCalled());
    expect(portalLogout).toHaveBeenCalled();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(SLUG_KEY)).toBeNull();
  });

  it('portalLogout rejects: token and slug still cleared and CRM sign-out still happens', async () => {
    portalLogout.mockRejectedValue(new Error('network'));
    render(<Menu trigger={<button>t</button>} />);
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    await waitFor(() => expect(signOut).toHaveBeenCalled());
    expect(portalLogout).toHaveBeenCalled();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(SLUG_KEY)).toBeNull();
  });
});
