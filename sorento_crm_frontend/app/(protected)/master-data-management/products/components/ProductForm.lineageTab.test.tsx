/**
 * NPA-FROM-SI: the product page's read-only Lineage tab. It exists for a saved product only, lists
 * what the code was created from and the codes made from it, and reads as "No lineage" when there
 * is nothing (or the read is refused). Same stubbing technique as `ProductForm.suppliersTabGate`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'select'} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="" />
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('../hooks/useProducts', () => ({
  useCreateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProduct: (id: string | null) => ({
    data: id
      ? {
          id, product_code: 'PROD-9', product_name: 'Product Nine',
          list_price: 10, is_active: true, is_searchable: true,
          exclude_from_planning: false, has_serial_tracking: false,
          has_batch_tracking: false,
        }
      : undefined,
  }),
}));

const lineage = vi.hoisted(() => ({
  state: { data: undefined, isLoading: false, isError: false } as {
    data: unknown;
    isLoading: boolean;
    isError: boolean;
    error?: unknown;
  },
}));
vi.mock(
  '@/app/(protected)/procurement-management/new-product-applications/hooks/useNewProductApplications',
  () => ({ useProductLineageQuery: () => lineage.state }),
);

vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [] }),
}));
vi.mock('../../shared/hooks/use-item-class-select-query', () => ({
  useItemClassSelectQuery: () => ({ data: [] }),
}));
vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));
vi.mock('../../shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({ data: [] }),
}));

const grantedPerms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => grantedPerms.granted.has(slug),
}));
vi.mock('../../product-categories/hooks/useProductCategories', () => ({
  useCategory: () => ({ data: undefined }),
}));

vi.mock('@/app/(protected)/project-sales/_shared/components/PriceFloorPanel', () => ({
  PriceFloorPanel: () => <div data-testid="price-floor-stub" />,
}));
vi.mock('./ProductSuppliersSection', () => ({
  default: () => <div data-testid="suppliers-stub" />,
}));
vi.mock('./ProductAttachmentsTab', () => ({
  default: () => <div data-testid="attachments-stub" />,
}));
vi.mock('@/components/common/ListPager', () => ({
  default: () => <div data-testid="list-pager-stub" />,
}));

import { NewProductApplicationError } from '@/types/newProductApplication';
import ProductForm from './ProductForm';

const row = (over: Record<string, unknown> = {}) => ({
  application_no: 'NPA-000123',
  product_id: 'p-69',
  product_code: 'SRTWB893',
  product_name: 'Wall hung basin',
  is_active: true,
  current_products: [{ id: 'p-1', product_code: 'SRTWB888' }],
  description: 'no tap hole & overflow',
  expected_qty: '270',
  created_at: '2026-11-03T02:00:00',
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  grantedPerms.granted.clear();
  lineage.state = { data: { created_from: [], made_from_this: [] }, isLoading: false, isError: false };
});

const openLineage = () =>
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Lineage/i }));

describe('Lineage tab', () => {
  it('is absent while creating a product', () => {
    render(<ProductForm />);
    expect(screen.queryByRole('tab', { name: /Lineage/i })).not.toBeInTheDocument();
  });

  it('shows the empty state when there is no lineage', () => {
    render(<ProductForm productId="p-69" />);
    openLineage();
    expect(screen.getByText('No lineage')).toBeInTheDocument();
    expect(
      screen.getByText('Codes created through a New Product Application show here.'),
    ).toBeInTheDocument();
  });

  it('shows the empty state when the read is refused', () => {
    lineage.state = {
      data: undefined,
      isLoading: false,
      isError: true,
      error: new NewProductApplicationError('Forbidden', null, null, 403),
    };
    render(<ProductForm productId="p-69" />);
    openLineage();
    expect(screen.getByText('No lineage')).toBeInTheDocument();
  });

  it('lists created-from with a link to the application, and the codes made from this product', () => {
    lineage.state = {
      data: {
        created_from: [row({ application_id: 'a-1', customer_name: 'EXAMPLE DEVELOPER', project_name: 'TOWER B' })],
        made_from_this: [
          row({
            application_no: 'NPA-000200',
            product_id: 'p-70',
            product_code: 'SRTWB894',
            application_id: 'a-2',
          }),
        ],
      },
      isLoading: false,
      isError: false,
    };
    render(<ProductForm productId="p-69" />);
    openLineage();

    expect(screen.getByText('Created from')).toBeInTheDocument();
    expect(screen.getByText('New codes made from this product')).toBeInTheDocument();
    const app = screen.getByRole('link', { name: 'NPA-000123' });
    expect(app).toHaveAttribute('href', '/procurement-management/new-product-applications/a-1');
    expect(screen.getAllByText('SRTWB888').length).toBeGreaterThan(0);
    expect(screen.getAllByText('no tap hole & overflow').length).toBeGreaterThan(0);
    expect(screen.getByText('EXAMPLE DEVELOPER / TOWER B')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'SRTWB894' })).toHaveAttribute(
      'href',
      '/master-data-management/products/p-70',
    );
  });

  it('shows the application number as plain text without a link when it carries no id, and no customer column', () => {
    lineage.state = {
      data: { created_from: [row()], made_from_this: [] },
      isLoading: false,
      isError: false,
    };
    render(<ProductForm productId="p-69" />);
    openLineage();
    expect(screen.getByText('NPA-000123')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'NPA-000123' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /customer/i })).toBeNull();
  });
});
