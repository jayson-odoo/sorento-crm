/**
 * PORTAL-P3-ROLE-MENU round 3, T2: the Quick Access "Add shortcut" list applies the sidebar's
 * audience and portalKind filter.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const sessionRef = { data: { user: { id: 'u1', roleName: 'x', status: 'ACTIVE' } }, status: 'authenticated' };
const permsRef: { set: Set<string> } = { set: new Set() };
const profile: { salesperson: { portalKinds: string[]; portalSlug: string } | null } = { salesperson: null };

vi.mock('next-auth/react', () => ({ useSession: () => sessionRef }));
vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: permsRef.set, isLoading: false }),
  useHasAnyPermission: () => true,
}));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: null, isLoading: false }),
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: profile.salesperson,
    avatarSrc: undefined,
    displayName: '',
    displayEmail: '',
  }),
}));
vi.mock('@/hooks/usePrefetchOnce', () => ({ usePrefetchOnce: () => () => {} }));
vi.mock('@/hooks/useQuickAccess', () => ({
  useQuickAccess: () => ({ data: [], isLoading: false }),
  useAddQuickAccess: () => ({ mutate: vi.fn() }),
  useRemoveQuickAccess: () => ({ mutate: vi.fn() }),
  useReorderQuickAccess: () => ({ mutate: vi.fn() }),
}));
vi.mock(
  '@/app/(protected)/workflow-forms-management/hooks/useWorkflowForms',
  () => ({ usePublishedWorkflowDefinitionsForSubmissionQuery: () => ({ data: undefined }) }),
);
vi.mock('./menu-item-pin-button', () => ({ MenuItemPinButton: () => null }));

import { SidebarMenu } from './sidebar-menu';

function openAddShortcut() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /add shortcut/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  permsRef.set = new Set([
    'projects.projects.view_own',
    'sla_management.conversations.view_own',
    'sales.customer_asks.view',
  ]);
});

describe('Quick Access add-shortcut list', () => {
  it('staff: no request kind and Customer asks only once', async () => {
    profile.salesperson = null;
    render(<SidebarMenu />);
    openAddShortcut();
    const items = (await screen.findAllByRole('menuitem')).map((i) => i.textContent);
    expect(items).not.toContain('Complaint');
    expect(items).not.toContain('Stock Inquiry');
    expect(items.filter((t) => t === 'Customer asks')).toHaveLength(1);
  });

  it('salesperson: request kinds only for the contact kinds', async () => {
    profile.salesperson = { portalKinds: ['complaint'], portalSlug: 'S1' };
    render(<SidebarMenu />);
    openAddShortcut();
    const items = (await screen.findAllByRole('menuitem')).map((i) => i.textContent);
    expect(items).toContain('Complaint');
    expect(items).not.toContain('Stock Inquiry');
    expect(items.filter((t) => t === 'Customer asks')).toHaveLength(1);
  });
});
