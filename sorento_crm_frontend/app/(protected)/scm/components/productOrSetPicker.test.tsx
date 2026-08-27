/**
 * F12 / R20 - one picker holding products AND our product sets.
 *
 * The supplier sells the whole WC. `CWC605-RL` is a SET no product carries, so a picker that
 * could only offer products left the operator with the wrong half of the answer or Dismiss.
 *
 * What is pinned here is the CONTRACT between the list and the endpoint: which of the two an
 * option value names, and that sets are asked for once rather than repeated under every
 * "Load more" - the product master is paged, the set master is not.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const getProducts = vi.fn();
const getProductSets = vi.fn();

vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({ getProducts: (...args: unknown[]) => getProducts(...args) }),
);
vi.mock(
  '@/app/(protected)/master-data-management/product-sets/services/productSetService',
  () => ({ getProductSets: (...args: unknown[]) => getProductSets(...args) }),
);

import {
  aliasTargetFor,
  fetchProductOrSetOptions,
  isSetOption,
  renderProductOrSetOption,
  SET_OPTION_PREFIX,
} from './productOrSetPicker';

beforeEach(() => {
  getProducts.mockReset().mockResolvedValue({
    data: [{ id: 'p-1', product_code: 'CWCX605-RL', product_name: 'Pedestal' }],
  });
  getProductSets.mockReset().mockResolvedValue({
    data: [{ id: 's-1', set_code: 'CWC605-RL', name: 'Close-coupled WC' }],
  });
});

describe('productOrSetPicker', () => {
  it('offers the sets first and the products after them', async () => {
    const options = await fetchProductOrSetOptions('CWC605', 0);

    expect(options.map((o) => o.value)).toEqual([`${SET_OPTION_PREFIX}s-1`, 'p-1']);
    expect(options[0].label).toBe('CWC605-RL - Close-coupled WC');
  });

  it('asks for the sets once, not under every load-more', async () => {
    await fetchProductOrSetOptions('CWC605', 1);

    expect(getProductSets).not.toHaveBeenCalled();
    expect(getProducts).toHaveBeenCalledWith(
      expect.objectContaining({ pageIndex: 1, searchQuery: 'CWC605' }),
    );
  });

  it('still answers with the products when the set master is out of reach', async () => {
    // A reader without the product-set permission gets half the list, never an empty one -
    // an empty picker is the state that makes a code unanswerable.
    getProductSets.mockRejectedValue(new Error('403'));

    const options = await fetchProductOrSetOptions('', 0);

    expect(options.map((o) => o.value)).toEqual(['p-1']);
  });

  it('says which of the two a chosen value names', () => {
    expect(aliasTargetFor('p-1')).toEqual({ product_id: 'p-1' });
    expect(aliasTargetFor(`${SET_OPTION_PREFIX}s-1`)).toEqual({ product_set_id: 's-1' });
    expect(isSetOption('p-1')).toBe(false);
    expect(isSetOption(`${SET_OPTION_PREFIX}s-1`)).toBe(true);
  });

  it('badges a set in the list, and leaves a product plain', () => {
    const { unmount } = render(
      <>{renderProductOrSetOption({ value: `${SET_OPTION_PREFIX}s-1`, label: 'CWC605-RL' })}</>,
    );
    expect(screen.getByText('Set')).toBeInTheDocument();
    unmount();

    render(<>{renderProductOrSetOption({ value: 'p-1', label: 'CWCX605-RL' })}</>);
    expect(screen.queryByText('Set')).not.toBeInTheDocument();
  });
});
