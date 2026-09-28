/**
 * ProductsList header, round 5 of #1288 (owner ruling 28 Sep 2026): Create product
 * moves into the toolbar's Actions menu, and the primary spot it held becomes
 * "Upload cost price", which opens the SAME `UploadPriceListDialog` Purchasing >
 * Cost price lists uses, behind the same `procurement.cost_price_changes.upload` gate.
 *
 * The real DataGrid and toolbar do not mount in jsdom (see ProductsList.variant.test),
 * so the toolbar is stubbed to capture the props ProductsList feeds it; the captured
 * `primaryAction` is then rendered for real. The toolbar's own suite covers how
 * `secondaryActions` render as the Actions menu.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

const toolbar = vi.hoisted(() => ({
  props: null as null | { primaryAction?: ReactNode; secondaryActions?: ToolbarAction[] },
}));
const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
const dialog = vi.hoisted(() => ({ lastProps: null as null | { open: boolean; onUploaded?: () => void } }));
const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  router: { replace: () => {}, push: vi.fn() },
}));

vi.mock('@/components/ui/data-grid', () => ({
  DataGrid: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/ui/data-grid-table', () => ({ DataGridTable: () => null }));
vi.mock('@/components/ui/data-grid-pagination', () => ({ DataGridPagination: () => null }));
vi.mock('@/components/ui/data-grid-list-toolbar', () => ({
  DataGridListToolbar: (props: { primaryAction?: ReactNode; secondaryActions?: ToolbarAction[] }) => {
    toolbar.props = props;
    return <div data-testid="toolbar-primary">{props.primaryAction}</div>;
  },
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));

// The Purchasing dialog itself, stubbed only so this suite can see it opened and
// with what; `UploadPriceListDialog.test.tsx` covers its body.
vi.mock('@/app/(protected)/procurement-management/cost-price-uploads/components/UploadPriceListDialog', () => ({
  UploadPriceListDialog: (props: { open: boolean; onUploaded?: () => void }) => {
    dialog.lastProps = props;
    return props.open ? <div role="dialog">Upload price list</div> : null;
  },
}));

vi.mock('../services/productService', () => ({
  getProducts: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } }),
  bulkImportProducts: vi.fn(),
  validateProductsImport: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => nav.router,
  usePathname: () => '/master-data-management/products',
  useSearchParams: () => nav.params,
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

const UPLOAD_SLUG = 'procurement.cost_price_changes.upload';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(
    <QueryClientProvider client={client}>
      <ProductsList />
    </QueryClientProvider>,
  );
  return { invalidate };
}

beforeEach(() => {
  toolbar.props = null;
  dialog.lastProps = null;
  perms.granted = new Set();
  nav.router.push.mockReset();
});
afterEach(() => cleanup());

describe('ProductsList header: Upload cost price, Create product under Actions', () => {
  it('lists Create product in the Actions menu items, opening the create page as before', () => {
    renderList();
    const items = toolbar.props?.secondaryActions ?? [];
    const create = items.find((a) => a.label === 'Create product');
    expect(create).toBeDefined();
    // First in the menu, and still the only way to reach the create page.
    expect(items[0]?.key).toBe('create-product');
    create?.onClick?.();
    expect(nav.router.push).toHaveBeenCalledWith('/master-data-management/products/new');
  });

  it('keeps Create product ungated, as it was (it had no client gate before)', () => {
    perms.granted = new Set();
    renderList();
    expect(toolbar.props?.secondaryActions?.some((a) => a.label === 'Create product')).toBe(true);
  });

  it('puts Upload cost price in the primary spot for a user with the upload permission', () => {
    perms.granted = new Set([UPLOAD_SLUG]);
    renderList();
    const primary = screen.getByTestId('toolbar-primary');
    expect(primary.textContent).toContain('Upload cost price');
    expect(primary.textContent).not.toMatch(/Create product/i);
  });

  it('hides Upload cost price without the upload permission, and Create product never returns to the primary spot', () => {
    renderList();
    expect(screen.queryByRole('button', { name: 'Upload cost price' })).toBeNull();
    expect(screen.getByTestId('toolbar-primary').textContent).not.toMatch(/Create product/i);
  });

  it('opens the Purchasing UploadPriceListDialog from Upload cost price', () => {
    perms.granted = new Set([UPLOAD_SLUG]);
    renderList();
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Upload cost price' }));
    expect(screen.getByRole('dialog').textContent).toContain('Upload price list');
    expect(dialog.lastProps?.open).toBe(true);
  });

  it('reloads the products list when the upload succeeds', () => {
    perms.granted = new Set([UPLOAD_SLUG]);
    const { invalidate } = renderList();
    fireEvent.click(screen.getByRole('button', { name: 'Upload cost price' }));
    expect(dialog.lastProps?.onUploaded).toBeTypeOf('function');
    dialog.lastProps?.onUploaded?.();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['products'] });
  });
});
