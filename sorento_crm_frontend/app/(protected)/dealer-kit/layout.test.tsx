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
  usePathname: vi.fn(() => '/dealer-kit'),
}));

import { usePermissions } from '@/hooks/usePermissions';
import DealerKitLayout from './layout';

describe('DealerKitLayout', () => {
  it('renders children when user has dealer_kit.page.view', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set(['dealer_kit.page.view']),
      isLoading: false,
    });
    render(
      <DealerKitLayout>
        <div data-testid="child">ok</div>
      </DealerKitLayout>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('renders AccessDenied when user lacks permission', () => {
    (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
      permissionSet: new Set([]),
      isLoading: false,
    });
    render(
      <DealerKitLayout>
        <div data-testid="child">ok</div>
      </DealerKitLayout>,
    );
    expect(screen.queryByTestId('child')).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeDefined();
  });
});
