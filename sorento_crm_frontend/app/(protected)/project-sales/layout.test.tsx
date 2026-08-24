import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock usePermissions
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: vi.fn(),
}));

// Mock next-auth
vi.mock('next-auth/react', () => ({
  useSession: vi.fn(() => ({
    data: { user: { roleName: 'viewer' } },
    status: 'authenticated',
  })),
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => '/project-sales'),
}));

import { usePermissions } from '@/hooks/usePermissions';
import ProjectSalesLayout from './layout';

describe('ProjectSalesLayout', () => {
  it('renders children when user has projects.projects.view', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set(['projects.projects.view']),
      isLoading: false,
    });
    render(
      <ProjectSalesLayout>
        <div data-testid="child">ok</div>
      </ProjectSalesLayout>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('renders AccessDenied when user lacks permission', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set([]),
      isLoading: false,
    });
    render(
      <ProjectSalesLayout>
        <div data-testid="child">ok</div>
      </ProjectSalesLayout>,
    );
    expect(screen.queryByTestId('child')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });
});
