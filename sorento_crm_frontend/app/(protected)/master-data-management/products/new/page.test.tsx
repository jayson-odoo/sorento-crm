/**
 * The create and edit product pages are gated on the permission their save needs
 * (`master_data.products.add` / `.edit`), so a typed URL shows Access Denied
 * instead of a form whose save would 403 (PLAN-product-edit-perm-30oct.md).
 */
import React, { Suspense } from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';

import NewProductPage from './page';
import EditProductPage from '../[id]/edit/page';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/master-data-management/products/new',
}));

vi.mock('../components/ProductForm', () => ({
  default: () => <div data-testid="product-form" />,
}));

vi.mock('../hooks/useProducts', () => ({
  useProduct: () => ({ data: { id: 'p1' } }),
}));

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/app/components/common/AccessDenied', () => ({
  default: () => <div data-testid="access-denied" />,
}));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

function grant(slugs: string[]) {
  usePermissions.mockReturnValue({
    permissions: slugs,
    permissionSet: new Set(slugs),
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  });
}

const PARAMS = Promise.resolve({ id: 'p1' });

async function renderEdit() {
  await act(async () => {
    render(
      <Suspense fallback={null}>
        <EditProductPage params={PARAMS} />
      </Suspense>,
    );
  });
}

beforeEach(async () => {
  cleanup();
  await PARAMS;
});

describe('product create / edit pages are permission-gated', () => {
  it('create page: Access Denied without master_data.products.add', () => {
    grant(['master_data.products.view', 'master_data.products.edit']);
    render(<NewProductPage />);
    expect(screen.getByTestId('access-denied')).toBeInTheDocument();
    expect(screen.queryByTestId('product-form')).not.toBeInTheDocument();
  });

  it('create page: the form with master_data.products.add', () => {
    grant(['master_data.products.add']);
    render(<NewProductPage />);
    expect(screen.getByTestId('product-form')).toBeInTheDocument();
  });

  it('edit page: Access Denied without master_data.products.edit', async () => {
    grant(['master_data.products.view', 'master_data.products.add']);
    await renderEdit();
    expect(screen.getByTestId('access-denied')).toBeInTheDocument();
    expect(screen.queryByTestId('product-form')).not.toBeInTheDocument();
  });

  it('edit page: the form with master_data.products.edit', async () => {
    grant(['master_data.products.edit']);
    await renderEdit();
    expect(screen.getByTestId('product-form')).toBeInTheDocument();
  });
});
