import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import ProductVariantsTab from './ProductVariantsTab';
import type { ProductVariantRef } from '../../types/product.types';

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
  } & Record<string, unknown>) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>
      {children}
    </a>
  ),
}));

const PARENT: ProductVariantRef = {
  id: 'p-parent-uuid',
  product_code: 'SRTKT71SS',
  product_name: 'Kitchen Tap 71 Stainless',
};

const CHILDREN: ProductVariantRef[] = [
  {
    id: 'c-1-uuid',
    product_code: 'SRTKT71SS-BL',
    product_name: 'Kitchen Tap 71 Stainless Black',
  },
  {
    id: 'c-2-uuid',
    product_code: 'SRTKT71SS-GM',
    product_name: 'Kitchen Tap 71 Stainless Gunmetal',
  },
];

describe('ProductVariantsTab', () => {
  it('renders the "Variant of" parent link when the product is a variant', () => {
    render(
      <ProductVariantsTab
        productCode="SRTKT71SS-BL"
        variantOf={PARENT}
        variants={[]}
      />,
    );

    // Section headings always render.
    expect(screen.getByText('Variant of')).toBeInTheDocument();

    const parentLink = screen.getByRole('link', { name: /SRTKT71SS/ });
    expect(parentLink).toHaveAttribute(
      'href',
      '/master-data-management/products/p-parent-uuid',
    );
    // Human-readable name shown, never the UUID.
    expect(screen.getByText('Kitchen Tap 71 Stainless')).toBeInTheDocument();
  });

  it('renders the "Variants (N)" list for a base with children, each linking to its detail', () => {
    render(
      <ProductVariantsTab
        productCode="SRTKT71SS"
        variantOf={null}
        variants={CHILDREN}
      />,
    );

    // Count in the heading.
    expect(screen.getByText('Variants (2)')).toBeInTheDocument();

    const child1 = screen.getByRole('link', { name: /SRTKT71SS-BL/ });
    expect(child1).toHaveAttribute(
      'href',
      '/master-data-management/products/c-1-uuid',
    );
    const child2 = screen.getByRole('link', { name: /SRTKT71SS-GM/ });
    expect(child2).toHaveAttribute(
      'href',
      '/master-data-management/products/c-2-uuid',
    );

    // Base products show the "not a variant" empty state for the parent slot.
    expect(
      screen.getByText(/it is not a variant of another product/i),
    ).toBeInTheDocument();
  });

  it('renders the empty state for a base with no variants', () => {
    render(
      <ProductVariantsTab productCode="ACC-4001" variantOf={null} variants={[]} />,
    );

    expect(screen.getByText('No variants of this product.')).toBeInTheDocument();
    // Section still renders (never hidden) — title + both sub-headings present.
    expect(screen.getAllByText('Variants').length).toBeGreaterThan(0);
    expect(screen.getByText('Variant of')).toBeInTheDocument();
  });

  it('never renders a raw UUID anywhere in the output', () => {
    const { container } = render(
      <ProductVariantsTab
        productCode="SRTKT71SS"
        variantOf={PARENT}
        variants={CHILDREN}
      />,
    );

    // hrefs carry the id, but no visible text node should contain a UUID.
    expect(container.textContent).not.toContain('p-parent-uuid');
    expect(container.textContent).not.toContain('c-1-uuid');
    expect(container.textContent).not.toContain('c-2-uuid');
  });
});
