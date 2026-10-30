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
import { usePathname } from 'next/navigation';
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
  describe('price tag pages open for a salesperson\'s own requests', () => {
    const ID = '5b0c1c0e-0000-4000-8000-000000000001';
    const setPerms = (slugs: string[]) =>
      (usePermissions as ReturnType<typeof vi.fn>).mockReturnValue({
        permissionSet: new Set(slugs),
        isLoading: false,
      });
    const renderAt = (path: string) => {
      (usePathname as ReturnType<typeof vi.fn>).mockReturnValue(path);
      return render(
        <DealerKitLayout>
          <div data-testid="child">ok</div>
        </DealerKitLayout>,
      );
    };
    const ownPages = [
      '/dealer-kit/price-tag-requests',
      '/dealer-kit/price-tag-requests/new',
      `/dealer-kit/price-tag-requests/${ID}`,
    ];

    it.each(ownPages)('view_own alone opens %s', (path) => {
      setPerms(['dealer_kit.price_tag_requests.view_own']);
      renderAt(path);
      expect(screen.queryByTestId('child')).not.toBeNull();
    });

    it.each(ownPages)('page.view alone opens %s', (path) => {
      setPerms(['dealer_kit.page.view']);
      renderAt(path);
      expect(screen.queryByTestId('child')).not.toBeNull();
    });

    it.each(['/dealer-kit', `/dealer-kit/price-tag-requests/${ID}/design`])(
      'view_own alone is denied on %s',
      (path) => {
        setPerms(['dealer_kit.price_tag_requests.view_own']);
        renderAt(path);
        expect(screen.queryByTestId('child')).toBeNull();
        expect(screen.getByText("You don't have access to this page")).toBeDefined();
      },
    );

    it('neither permission is denied on the price tag list', () => {
      setPerms([]);
      renderAt('/dealer-kit/price-tag-requests');
      expect(screen.queryByTestId('child')).toBeNull();
      expect(screen.getByText("You don't have access to this page")).toBeDefined();
    });
  });
});
