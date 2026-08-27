'use client';

import * as React from 'react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import {
  useDismissSupplierCode,
  useForgetSupplierCodeMatch,
  useMatchSupplierCode,
  useSupplierCodeAliases,
  useUnmatchedSupplierCodes,
} from '../../hooks/useSupplierCodeAliases';
import type { UnmatchedSupplierCode } from '../../services/supplierCodeAliasService';
import { EM_DASH, fmtInt } from '../../lib/format';

/**
 * The codes this supplier sent that bind to nothing we hold (R16, R17).
 *
 * Rendered on the loading plan because that is where the consequence lands: a stock row with
 * no product is stock the plan cannot offer, so a supplier can be holding 400 pieces of
 * something and the plan shows nothing. The upload dialog counts them and goes away; this is
 * where somebody comes back and answers them.
 *
 * ONE code-matching format, the same one the delivery-schedule review uses: a grid, and each
 * row carries the answer to its own problem. The product is picked in the row itself rather
 * than through a dialog - a dialog per code turns twenty codes into forty clicks and hides
 * the list the operator is working down. Dismiss is the other answer: some of these codes
 * are not ours at all, and a queue holding lines that can never be crossed off is one people
 * stop reading. No confirmation on it, deliberately - it deletes nothing and detaches
 * nothing, and Forget puts the code straight back.
 *
 * Hidden when there is nothing to answer and nothing dismissed - it is not a section of the
 * record, it is a queue, and an empty queue on screen every day is noise the eye learns to
 * skip.
 */
export function UnmatchedSupplierCodesPanel({ supplierId }: { supplierId: string }) {
  const { data: rows = [] } = useUnmatchedSupplierCodes(supplierId || null);
  const { data: aliases = [] } = useSupplierCodeAliases(supplierId || null);
  const match = useMatchSupplierCode();
  const dismiss = useDismissSupplierCode();
  const forget = useForgetSupplierCodeMatch();
  const [showDismissed, setShowDismissed] = React.useState(false);
  /** The code a write is in flight for, so only ITS row goes quiet. */
  const [busy, setBusy] = React.useState<string | null>(null);

  const dismissed = React.useMemo(
    () => aliases.filter((alias) => alias.source === 'dismissed'),
    [aliases],
  );

  /**
   * The product master is tens of thousands of rows, so the picker is SERVER-searched and
   * paginated. A dropdown holding one cached page silently hides the item the operator is
   * looking for, which is the same mistake this codebase has made twice.
   */
  const fetchProducts = React.useCallback(
    async (query: string, pageIndex: number) => {
      const res = await getProducts({
        pageIndex,
        pageSize: 50,
        sorting: [],
        searchQuery: query,
        status: 'active',
      });
      return (res.data ?? []).map((p) => ({
        value: p.id,
        label: `${p.product_code} - ${p.product_name}`,
        searchText: `${p.product_code} ${p.product_name}`,
      }));
    },
    [],
  );

  const onPick = React.useCallback(
    async (code: string, productId: string) => {
      if (!productId) return;
      setBusy(code);
      try {
        await match.mutateAsync({
          supplier_id: supplierId,
          supplier_code: code,
          product_id: productId,
        });
      } catch {
        // The hook toasts the refusal; the row stays in the queue to be answered again.
      } finally {
        setBusy(null);
      }
    },
    [match, supplierId],
  );

  const onDismiss = React.useCallback(
    async (code: string) => {
      setBusy(code);
      try {
        await dismiss.mutateAsync({ supplier_id: supplierId, supplier_code: code });
      } catch {
        // Toasted by the hook.
      } finally {
        setBusy(null);
      }
    },
    [dismiss, supplierId],
  );

  const columns = React.useMemo<ColumnDef<UnmatchedSupplierCode>[]>(
    () => [
      {
        id: 'code',
        accessorKey: 'item_code',
        header: 'Code',
        size: 170,
        cell: ({ row }) => (
          <span
            className="block truncate text-sm font-medium"
            title={row.original.item_code}
          >
            {row.original.item_code}
          </span>
        ),
      },
      {
        id: 'says',
        accessorKey: 'product_name',
        header: 'Supplier says',
        size: 220,
        cell: ({ row }) => {
          // What the person matching it actually recognises: the code means nothing on its
          // own, and "连体马桶, SORENTO" means everything.
          const said =
            [row.original.product_name, row.original.brand, row.original.spec]
              .filter(Boolean)
              .join(' · ') || EM_DASH;
          return (
            <span className="block truncate text-sm text-muted-foreground" title={said}>
              {said}
            </span>
          );
        },
      },
      {
        id: 'packed',
        accessorKey: 'qty_packed',
        header: 'Packed',
        size: 100,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => (
          <span className="tabular-nums">{fmtInt(row.original.qty_packed || 0)}</span>
        ),
      },
      {
        id: 'product',
        accessorKey: 'item_code',
        header: 'Product',
        size: 280,
        cell: ({ row }) => {
          const code = row.original.item_code;
          return (
            <SearchableSelect
              id={`unmatched-product-${code}`}
              value=""
              onChange={(v: string) => void onPick(code, v)}
              fetchOptions={fetchProducts}
              paginated
              pageSize={50}
              size="sm"
              disabled={busy === code}
              placeholder="Search a product"
              triggerClassName="w-full"
              clearable
            />
          );
        },
      },
      {
        id: 'dismiss',
        accessorKey: 'as_of',
        header: 'Dismiss',
        size: 100,
        cell: ({ row }) => (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            disabled={busy === row.original.item_code}
            onClick={() => void onDismiss(row.original.item_code)}
          >
            Dismiss
          </Button>
        ),
      },
    ],
    [busy, fetchProducts, onDismiss, onPick],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.item_code,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (rows.length === 0 && dismissed.length === 0) return null;

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      // Column personalisation OFF, the same call the delivery-schedule review makes: unset,
      // the grid keys saved widths on the URL, which here carries a supplier id, and it
      // leaves the grid in its skeleton state until something else re-renders it.
      listingKey=""
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="Every code binds."
    >
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 py-3">
          <CardHeading>
            <CardTitle className="text-sm">
              {rows.length === 1
                ? '1 code matches nothing we hold'
                : `${rows.length} codes match nothing we hold`}
            </CardTitle>
          </CardHeading>
          <Badge variant="secondary" appearance="light">
            {fmtInt(rows.reduce((sum, r) => sum + (r.qty_packed || 0), 0))} packed
          </Badge>
        </CardHeader>
        <CardTable>
          {/* Five columns are wider than a phone, so the table scrolls inside its own
              container rather than dragging the page sideways. */}
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>

        {dismissed.length > 0 && (
          <div className="border-t border-border p-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>
                {dismissed.length === 1 ? '1 dismissed' : `${dismissed.length} dismissed`}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => setShowDismissed((open) => !open)}
              >
                {showDismissed ? 'Hide' : 'Show'}
              </Button>
            </div>
            {showDismissed && (
              <ul className="mt-2 space-y-1">
                {dismissed.map((alias) => (
                  <li
                    key={alias.id}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="min-w-0 truncate" title={alias.supplier_code}>
                      {alias.supplier_code}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 shrink-0 px-2 text-xs"
                      onClick={() => forget.mutate(alias.id)}
                    >
                      Undo
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>
    </DataGrid>
  );
}

export default UnmatchedSupplierCodesPanel;
