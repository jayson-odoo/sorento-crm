/**
 * PORTAL-P3-ROLE-MENU P3-14, P3-17: a salesperson holding only `projects.projects.view_own`
 * passes the Project Sales gate (layout and pipeline page); `.view` holders are unchanged.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/hooks/usePermissions', () => ({ usePermissions: vi.fn() }));
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => false }));
vi.mock('next-auth/react', () => ({
  useSession: vi.fn(() => ({ data: { user: { roleName: 'salesperson' } }, status: 'authenticated' })),
}));
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => '/project-sales/pipeline'),
}));
vi.mock('./pipeline/components/PipelineClient', () => ({
  PipelineClient: () => <div data-testid="pipeline-client">pipeline</div>,
}));

import { usePermissions } from '@/hooks/usePermissions';
import ProjectSalesLayout from './layout';
import ProjectPipelinePage from './pipeline/page';

function perms(...slugs: string[]) {
  (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
    permissionSet: new Set(slugs),
    isLoading: false,
    isError: false,
  });
}

describe('Project Sales gate with view_own', () => {
  it('layout: view_own only renders children', () => {
    perms('projects.projects.view_own');
    render(
      <ProjectSalesLayout>
        <div data-testid="child">ok</div>
      </ProjectSalesLayout>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('layout: view only still renders children (unchanged)', () => {
    perms('projects.projects.view');
    render(
      <ProjectSalesLayout>
        <div data-testid="child">ok</div>
      </ProjectSalesLayout>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('layout: neither slug is denied (unchanged)', () => {
    perms('sales.customer_asks.view');
    render(
      <ProjectSalesLayout>
        <div data-testid="child">ok</div>
      </ProjectSalesLayout>,
    );
    expect(screen.queryByTestId('child')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });

  it('pipeline page: view_own only renders the pipeline', () => {
    perms('projects.projects.view_own');
    render(<ProjectPipelinePage />);
    expect(screen.getByTestId('pipeline-client')).toBeDefined();
  });

  it('pipeline page: view only still renders the pipeline (unchanged)', () => {
    perms('projects.projects.view');
    render(<ProjectPipelinePage />);
    expect(screen.getByTestId('pipeline-client')).toBeDefined();
  });

  it('pipeline page: neither slug is denied (unchanged)', () => {
    perms();
    render(<ProjectPipelinePage />);
    expect(screen.queryByTestId('pipeline-client')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });
});
