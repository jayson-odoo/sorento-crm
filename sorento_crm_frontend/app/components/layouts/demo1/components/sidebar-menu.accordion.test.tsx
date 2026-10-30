/**
 * SIDEBAR-ACCORDION-FIX: the sidebar renders in two halves (before and after the SALES
 * heading), each indexed from 0, so a path-less group in one half shared its accordion value
 * with the group at the same index in the other half. Ideas (index 2 before SALES) and
 * Project Sales (index 2 after) opened and closed together.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const pathnameRef = { current: '/' };

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'admin-1', roleName: 'Super Admin', status: 'ACTIVE' } },
    status: 'authenticated',
  }),
}));
vi.mock('next/navigation', () => ({ usePathname: () => pathnameRef.current }));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissionSet: new Set(['ideation.board.view', 'projects.projects.view']),
    isLoading: false,
  }),
  useHasAnyPermission: () => false,
}));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: null, isLoading: false }),
}));
vi.mock('@/hooks/usePrefetchOnce', () => ({ usePrefetchOnce: () => () => {} }));
vi.mock(
  '@/app/(protected)/workflow-forms-management/hooks/useWorkflowForms',
  () => ({
    usePublishedWorkflowDefinitionsForSubmissionQuery: () => ({ data: undefined }),
  }),
);
vi.mock('./quick-access-block', () => ({ QuickAccessBlock: () => null }));
vi.mock('./menu-item-pin-button', () => ({ MenuItemPinButton: () => null }));

import { SidebarMenu } from './sidebar-menu';

describe('SidebarMenu accordion values (SIDEBAR-ACCORDION-FIX)', () => {
  it('opening Project Sales does not open Ideas', () => {
    pathnameRef.current = '/';
    render(<SidebarMenu />);
    fireEvent.click(screen.getByText('Project Sales'));
    expect(screen.getByText('Leads')).toBeInTheDocument();
    expect(screen.queryByText('All ideas')).not.toBeInTheDocument();
  });

  it('opening Ideas does not open Project Sales, and switching groups closes the first', () => {
    pathnameRef.current = '/';
    render(<SidebarMenu />);
    fireEvent.click(screen.getByText('Ideas'));
    expect(screen.getByText('All ideas')).toBeInTheDocument();
    expect(screen.queryByText('Leads')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Project Sales'));
    expect(screen.getByText('Leads')).toBeInTheDocument();
    expect(screen.queryByText('All ideas')).not.toBeInTheDocument();
  });

  it('the active route still highlights its item inside its own group', () => {
    pathnameRef.current = '/project-sales/leads';
    render(<SidebarMenu />);
    fireEvent.click(screen.getByText('Project Sales'));
    const leads = screen.getByText('Leads').closest('[data-slot="accordion-menu-item"]');
    expect(leads).toHaveAttribute('data-selected', 'true');
    expect(screen.queryByText('All ideas')).not.toBeInTheDocument();
  });
});
