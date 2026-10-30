/**
 * PORTAL-P3-ROLE-MENU P3-14, P3-17: a salesperson holding only
 * `sla_management.conversations.view_own` passes the Conversations page gate; `.view` holders
 * are unchanged. Only the inbox body is stubbed, so the page's own gate constant is the real one.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: () => <h1>header</h1> }));
vi.mock('@/hooks/usePermissions', () => ({ usePermissions: vi.fn() }));
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => false }));
vi.mock('next-auth/react', () => ({
  useSession: vi.fn(() => ({ data: { user: { roleName: 'salesperson' } }, status: 'authenticated' })),
}));
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  usePathname: vi.fn(() => '/sla-management/conversations'),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('./components/ConversationsInbox', async (importOriginal) => {
  const original = await importOriginal<typeof import('./components/ConversationsInbox')>();
  return { ...original, default: () => <div data-testid="inbox">inbox</div> };
});

import { usePermissions } from '@/hooks/usePermissions';
import ConversationsPage from './page';

async function renderPage(...slugs: string[]) {
  (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
    permissionSet: new Set(slugs),
    isLoading: false,
    isError: false,
  });
  render(await ConversationsPage());
}

describe('Conversations page gate with view_own', () => {
  it('view_own only renders the inbox', async () => {
    await renderPage('sla_management.conversations.view_own');
    expect(screen.getByTestId('inbox')).toBeDefined();
  });

  it('view only still renders the inbox (unchanged)', async () => {
    await renderPage('sla_management.conversations.view');
    expect(screen.getByTestId('inbox')).toBeDefined();
  });

  it('neither slug is denied (unchanged)', async () => {
    await renderPage('sales.customer_asks.view');
    expect(screen.queryByTestId('inbox')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });
});
