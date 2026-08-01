'use client';

import * as React from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
// The shared products `/select` mapper. Its name says "variant" because that screen needed
// it first; the endpoint and the shape are the generic ones.
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';

/**
 * Identifies a column the extractor could not match to our catalogue.
 *
 * Sits in the column header rather than in a dialog: the reviewer is reading the customer's
 * code off the header when they decide, and a modal would take that code off the screen.
 */
export function DeliveryScheduleProductPicker({
  idPrefix,
  columnIndex,
  customerCode,
  disabled,
  onPick,
}: {
  /**
   * The matrix and the phone view are both mounted (they differ by breakpoint, not by state),
   * so the element id has to say which one this is or the two collide in one document.
   */
  idPrefix: string;
  columnIndex: number;
  customerCode: string | null;
  disabled?: boolean;
  onPick: (productId: string) => void;
}) {
  const fetchProducts = React.useCallback(async (query: string) => {
    const rows = await getProductsForVariantSelect(query || undefined);
    return rows.map((row) => ({
      value: row.id,
      label: row.product_code,
      description: row.product_name,
    }));
  }, []);

  const id = `${idPrefix}-column-product-${columnIndex}`;
  const name = customerCode
    ? `Pick the product for ${customerCode}`
    : `Pick the product for column ${columnIndex + 1}`;

  return (
    <>
      <label htmlFor={id} className="sr-only">
        {name}
      </label>
      <SearchableSelect
        id={id}
        value=""
        onChange={onPick}
        size="sm"
        disabled={disabled}
        fetchOptions={fetchProducts}
        placeholder="Pick the product"
        emptyMessage="No products match"
        triggerClassName="w-full"
        className="min-w-[280px]"
      />
    </>
  );
}
