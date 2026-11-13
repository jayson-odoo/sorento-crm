/**
 * NON-CANCELLABLE-ITEMS: the company default dialog reads "Create" (title and submit) when it
 * creates, never "Add item" (owner standing rule: one verb, Create). Values invented.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../_shared/hooks/useProjects', () => ({
  useNonCancellableRuleMutations: () => ({
    create: { isPending: false, mutateAsync: vi.fn() },
    update: { isPending: false, mutateAsync: vi.fn() },
  }),
}));
vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query',
  () => ({ useProductCategorySelectQuery: () => ({ data: [] }) }),
);
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForLineSelect: vi.fn(async () => []),
}));

import { NonCancellableRuleDialog } from './NonCancellableRuleDialog';

describe('NonCancellableRuleDialog', () => {
  it('reads Create in the title and on the submit button, never Add item', () => {
    render(<NonCancellableRuleDialog rule={null} onDone={() => {}} />);
    expect(screen.getByRole('heading', { name: 'Create' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
    expect(screen.queryByText(/Add item/i)).toBeNull();
  });

  it('reads Edit item and Save when editing', () => {
    render(
      <NonCancellableRuleDialog
        rule={{
          id: 'r1',
          product_id: 'p1',
          product_code: 'ZZT-TUB-1',
          product_name: 'Freestanding bathtub',
          category_id: null,
          category_name: null,
          non_cancellable: true,
          notes: null,
          updated_at: null,
        }}
        onDone={() => {}}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Edit item' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });
});
