'use client';

import * as React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { CellStockTable } from '../../../project-sales/fulfilment-planning/components/CellStockTable';
import type { BoardCellLocation } from '../../../project-sales/_shared/types/fulfilmentPlanning.types';
import { searchStockStatusProducts } from '@/components/stock-status/stockStatusService';
import { useStockStatus } from '@/components/stock-status/useStockStatus';

/**
 * Inventory > Stock status: pick any item and read AutoCount's Available Stock Status for it,
 * in the same stock table Fulfilment Planning and Order Inquiry show (owner, 18 Oct: "1. Keep").
 * The item lives in the URL (`?product_id=`), so a link can be shared.
 */
export default function StockStatusPageClient() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const productId = params.get('product_id') ?? '';
  // The table's own read: also names the picked item when the page was opened by link, so the
  // picker never shows a bare id.
  const picked = useStockStatus(productId || null);
  const selectedOption = picked.data
    ? { value: picked.data.product_id, label: picked.data.item_code, description: picked.data.description ?? undefined }
    : undefined;

  const pick = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set('product_id', value);
    else next.delete('product_id');
    router.replace(`${pathname}${next.toString() ? `?${next.toString()}` : ''}`);
  };

  return (
    <div className="flex flex-col gap-4 pb-8">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Item</span>
        <SearchableSelect
          value={productId}
          onChange={pick}
          fetchOptions={searchStockStatusProducts}
          selectedOption={selectedOption}
          paginated
          clearable
          placeholder="Search an item code"
          triggerClassName="w-full sm:w-96"
        />
      </div>
      {productId ? (
        picked.data ? (
          <CellStockTable locations={rowsOf(picked.data)} />
        ) : null
      ) : (
        <div className="rounded-md border px-4 py-8 text-center">
          <p className="font-medium">Pick an item</p>
          <p className="text-sm text-muted-foreground">Every location, its orders and what is coming in.</p>
        </div>
      )}
    </div>
  );
}

/** AutoCount's locations as stock-table rows: every location holding the item. */
function rowsOf(data: NonNullable<ReturnType<typeof useStockStatus>['data']>): BoardCellLocation[] {
  return data.locations.map((loc) => ({
    location: loc.warehouse_code,
    where: 'other_group',
    product_id: data.product_id,
    warehouse_id: loc.warehouse_id,
    qty: '0',
    qty_on_hand: String(loc.on_hand),
    so_qty: String(loc.so_qty),
    spo_qty: String(loc.spo_qty),
    po_open_qty: String(loc.po_qty),
    available_qty: String(loc.on_hand - loc.so_qty + loc.spo_qty),
  }));
}
