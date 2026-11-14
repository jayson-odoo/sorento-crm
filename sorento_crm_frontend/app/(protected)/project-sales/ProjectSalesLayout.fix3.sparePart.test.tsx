/**
 * SPARE-PART-ORDER-REQUEST fix round 3, B1 (browser pass): a requester holding ONLY
 * `procurement.spare_part_requests.create` (no projects.projects.view / view_own) reaches the
 * Order Inquiries list, the New / Edit spare part request form and their request's OI page
 * through the project-sales route gate (`app/(protected)/project-sales/layout.tsx`). The rest of
 * project sales stays closed to them, and a projects viewer is unaffected.
 *
 * Red today: the layout wraps every project-sales route in RequireAccess(PROJECT_VIEW_PERMISSIONS),
 * so the create-only requester lands on "You don't have access to this page".
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

let pathname = '/project-sales/order-inquiries';
vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  useParams: () => ({}),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissionSet: held,
    permissions: [...held],
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
}));
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => false }));
vi.mock('@/components/common/screen-loader', () => ({ ScreenLoader: () => <div>loading</div> }));
vi.mock('@/app/components/common/AccessDenied', () => ({ default: () => <div>ACCESS DENIED</div> }));

import ProjectSalesLayout from './layout';

const CREATE = 'procurement.spare_part_requests.create';

function mount(path: string, slugs: string[]) {
  pathname = path;
  held = new Set(slugs);
  return render(
    <ProjectSalesLayout>
      <div>PAGE BODY</div>
    </ProjectSalesLayout>,
  );
}

beforeEach(() => cleanup());

describe('B1: the project-sales gate lets a create-only requester reach their request screens', () => {
  for (const path of [
    '/project-sales/order-inquiries',
    '/project-sales/order-inquiries/spare-part-requests/new',
    '/project-sales/order-inquiries/spare-part-requests/oi-1/edit',
    '/project-sales/order-inquiries/oi-1',
  ]) {
    it(`opens ${path}`, () => {
      mount(path, [CREATE]);
      expect(screen.getByText('PAGE BODY')).toBeInTheDocument();
      expect(screen.queryByText('ACCESS DENIED')).toBeNull();
    });
  }

  it('the rest of project sales stays closed to a create-only requester', () => {
    mount('/project-sales/pipeline', [CREATE]);
    expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
    expect(screen.queryByText('PAGE BODY')).toBeNull();
  });

  it('nobody without any grant reaches the order inquiries', () => {
    mount('/project-sales/order-inquiries', []);
    expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
  });

  it('a projects viewer is unchanged', () => {
    mount('/project-sales/pipeline', ['projects.projects.view']);
    expect(screen.getByText('PAGE BODY')).toBeInTheDocument();
  });
});
