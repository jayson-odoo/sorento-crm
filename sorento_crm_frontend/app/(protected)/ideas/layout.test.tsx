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
  usePathname: vi.fn(() => '/ideas'),
}));

import { usePermissions } from '@/hooks/usePermissions';
import IdeasLayout from './layout';

describe('IdeasLayout', () => {
  it('renders children when user has ideation.board.view', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set(['ideation.board.view']),
      isLoading: false,
    });
    render(
      <IdeasLayout>
        <div data-testid="child">ok</div>
      </IdeasLayout>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('renders AccessDenied when user lacks permission', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set([]),
      isLoading: false,
    });
    render(
      <IdeasLayout>
        <div data-testid="child">ok</div>
      </IdeasLayout>,
    );
    expect(screen.queryByTestId('child')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });
});
