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
  usePathname: vi.fn(() => '/scm'),
}));

import { usePermissions } from '@/hooks/usePermissions';
import ScmLayout from './layout';

describe('ScmLayout', () => {
  it('renders children when user has scm.dashboard.view', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set(['scm.dashboard.view']),
      isLoading: false,
    });
    render(
      <ScmLayout>
        <div data-testid="child">ok</div>
      </ScmLayout>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('renders AccessDenied when user lacks permission', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set([]),
      isLoading: false,
    });
    render(
      <ScmLayout>
        <div data-testid="child">ok</div>
      </ScmLayout>,
    );
    expect(screen.queryByTestId('child')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });
});
