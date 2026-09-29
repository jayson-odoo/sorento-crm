/**
 * ProductForm (#1305 reviewer pass, Lane A FE rows, S1): a role holding
 * `master_data.products.view` but not `procurement.product_suppliers.view` must not see the
 * Suppliers tab on the create/edit form - today it always renders and the section's own
 * GET 403s, which reads as "the form's supplier section can no longer save".
 *
 * Same stubbing technique as `ProductForm.excludeFromPlanning.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

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
  useProduct: () => ({ data: undefined }),
}));

vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [] }),
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

import ProductForm from './ProductForm';

beforeEach(() => {
  vi.clearAllMocks();
  grantedPerms.granted.clear();
});

describe('S1: the Suppliers tab is gated on procurement.product_suppliers.view', () => {
  it('renders no Suppliers tab for a caller without the permission', () => {
    render(<ProductForm />);
    expect(screen.queryByRole('tab', { name: /Suppliers/i })).not.toBeInTheDocument();
  });

  it('renders the Suppliers tab for a caller with the permission', () => {
    grantedPerms.granted.add('procurement.product_suppliers.view');
    render(<ProductForm />);
    expect(screen.getByRole('tab', { name: /Suppliers/i })).toBeInTheDocument();
  });
});
