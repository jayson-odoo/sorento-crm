/**
 * PORTAL-P3-ROLE-MENU round 4, R3b: in a salesperson's sidebar, a MY REQUESTS item (path with
 * ?type=X) is active only when the current search param type equals X; exactly one is active on
 * /my-requests?type=complaint, none on /my-requests/verify without a type; MY WORK items are
 * unaffected (Projects stays active on its own page).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

const nav = { pathname: '/my-requests', search: 'type=complaint' };
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u1', name: 'E', email: 'e@x.test', roleName: 'Sales', status: 'ACTIVE' } }, status: 'authenticated' }),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissionSet: new Set([
      'projects.projects.view_own',
      'sla_management.conversations.view_own',
      'sales.customer_asks.view',
      'sales.customer_asks.edit',
    ]),
    isLoading: false,
  }),
  useHasAnyPermission: () => false,
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: {
      portalKinds: ['stock_inquiry', 'complaint', 'purchase_request'],
      portalSlug: 'NT8D6BFC45',
    },
    isLoading: false, isError: false,
    avatarSrc: undefined, displayName: '', displayEmail: '',
  }),
}));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: null, isLoading: false }),
}));
vi.mock('@/hooks/usePrefetchOnce', () => ({ usePrefetchOnce: () => () => {} }));
vi.mock('@/app/(protected)/workflow-forms-management/hooks/useWorkflowForms', () => ({
  usePublishedWorkflowDefinitionsForSubmissionQuery: () => ({ data: undefined }),
}));
vi.mock('./quick-access-block', () => ({ QuickAccessBlock: () => null }));
vi.mock('./menu-item-pin-button', () => ({ MenuItemPinButton: () => null }));

import { SidebarMenu } from './sidebar-menu';

function activeTitles(container: HTMLElement): string[] {
  return [...container.querySelectorAll('[data-selected="true"]')].map((el) =>
    (el.textContent ?? '').trim(),
  );
}

beforeEach(() => {
  nav.pathname = '/my-requests';
  nav.search = 'type=complaint';
});

describe('SidebarMenu MY REQUESTS active item', () => {
  it('type=complaint: only Complaint is active', () => {
    const { container } = render(<SidebarMenu />);
    expect(activeTitles(container)).toEqual(['Complaint']);
  });

  it('type=stock_inquiry: only Stock Inquiry is active', () => {
    nav.search = 'type=stock_inquiry';
    const { container } = render(<SidebarMenu />);
    expect(activeTitles(container)).toEqual(['Stock Inquiry']);
  });

  it('no type param: no MY REQUESTS item is active', () => {
    nav.search = '';
    const { container } = render(<SidebarMenu />);
    expect(activeTitles(container)).toEqual([]);
  });

  it('MY WORK unaffected: Projects stays the single active item on its own page', () => {
    nav.pathname = '/project-sales/pipeline';
    nav.search = '';
    const { container } = render(<SidebarMenu />);
    expect(activeTitles(container)).toEqual(['Projects']);
  });

  it('/my-requests/complaint/new: only Complaint is active', () => {
    nav.pathname = '/my-requests/complaint/new';
    nav.search = '';
    const { container } = render(<SidebarMenu />);
    expect(activeTitles(container)).toEqual(['Complaint']);
  });

  it('/my-requests/stock_inquiry/<id>: only Stock Inquiry is active', () => {
    nav.pathname = '/my-requests/stock_inquiry/3f2a9c1e-0000-4000-8000-000000000001';
    nav.search = '';
    const { container } = render(<SidebarMenu />);
    expect(activeTitles(container)).toEqual(['Stock Inquiry']);
  });
});
