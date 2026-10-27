/**
 * Products > Actions > Extract photos from catalogue (CATALOG-IMAGES, AC-1): shown only to users
 * with `dealer_kit.page.edit`. The toolbar is stubbed to capture the items ProductsList feeds it,
 * as ProductsList.uploadCostPrice.test does.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

const toolbar = vi.hoisted(() => ({ props: null as null | { secondaryActions?: ToolbarAction[] } }));
const perms = vi.hoisted(() => ({ granted: new Set<string>() }));

vi.mock('@/components/ui/data-grid', () => ({
  DataGrid: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/ui/data-grid-table', () => ({ DataGridTable: () => null }));
vi.mock('@/components/ui/data-grid-pagination', () => ({ DataGridPagination: () => null }));
vi.mock('@/components/ui/data-grid-list-toolbar', () => ({
  DataGridListToolbar: (props: { secondaryActions?: ToolbarAction[] }) => {
    toolbar.props = props;
    return null;
  },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));
vi.mock('../services/productService', () => ({
  getProducts: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } }),
  bulkImportProducts: vi.fn(),
  validateProductsImport: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: () => {}, push: vi.fn() }),
  usePathname: () => '/master-data-management/products',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [] }),
}));
vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));
vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull', () => ({
  useAutocountPullAction: () => ({ visible: false, label: '', onSelect: () => {} }),
}));

import ProductsList from './ProductsList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ProductsList />
    </QueryClientProvider>,
  );
}

const labels = () => (toolbar.props?.secondaryActions ?? []).map((a) => a.label);

beforeEach(() => {
  toolbar.props = null;
  perms.granted = new Set();
});
afterEach(() => cleanup());

describe('ProductsList Actions: Extract photos from catalogue', () => {
  it('is listed for a user with dealer_kit.page.edit', () => {
    perms.granted = new Set(['dealer_kit.page.edit']);
    renderList();
    expect(labels()).toContain('Extract photos from catalogue');
  });

  it('is absent without dealer_kit.page.edit, even with master_data.products.edit', () => {
    perms.granted = new Set(['master_data.products.edit']);
    renderList();
    expect(labels()).not.toContain('Extract photos from catalogue');
  });
});
