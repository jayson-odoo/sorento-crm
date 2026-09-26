'use client';

import * as React from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { getProductSuppliers } from '@/app/(protected)/procurement-management/product-suppliers/services/productSupplierService';
import type { ProductSupplier } from '@/app/(protected)/procurement-management/product-suppliers/types/productSupplier.types';
import { getCostRowsForLink } from '@/app/(protected)/procurement-management/cost-price-uploads/services/costPriceService';
import { formatPlainDate } from '@/app/(protected)/procurement-management/cost-price-uploads/lib/formatPlainDate';
import type { CostRowStatus, ProductSupplierCostRow } from '@/app/(protected)/procurement-management/cost-price-uploads/types/costPrice.types';
import { CostRowDialog } from '@/app/(protected)/procurement-management/cost-price-uploads/components/CostRowDialog';

const STATUS_LABELS: Record<CostRowStatus, string> = {
  in_force: 'In force',
  scheduled: 'Scheduled',
  ended: 'Ended',
  always: 'Always',
  overridden: 'Overridden',
};
const STATUS_BADGE_VARIANT: Record<CostRowStatus, 'success' | 'info' | 'secondary'> = {
  in_force: 'success',
  scheduled: 'info',
  ended: 'secondary',
  always: 'secondary',
  overridden: 'secondary',
};
const STATUS_OPTIONS = (Object.keys(STATUS_LABELS) as CostRowStatus[]).map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

interface Entry {
  link: ProductSupplier;
  costs: ProductSupplierCostRow[];
}

type Row = { id: string; entry: Entry; cost: ProductSupplierCostRow | null };

export function SupplierPricesTab({ supplierId }: { supplierId: string }) {
  const canEdit = useHasPermission('procurement.product_suppliers.edit');
  const queryClient = useQueryClient();
  const [search, setSearch] = React.useState('');
  const [statuses, setStatuses] = React.useState<CostRowStatus[]>([]);
  const [dialog, setDialog] = React.useState<{ link: ProductSupplier; cost: ProductSupplierCostRow | null } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['supplier-cost-lists', supplierId],
    queryFn: async () => {
      const page = await getProductSuppliers({ pageIndex: 0, pageSize: 500, supplier_id: supplierId });
      return page.data;
    },
    enabled: !!supplierId,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['supplier-cost-lists', supplierId] });

  const entries: Entry[] = React.useMemo(
    () => (data ?? []).map((link) => ({ link, costs: getCostRowsForLink(link.id, link.unit_cost, link.currency) })),
    [data],
  );

  const tokens = React.useMemo(() => search.toLowerCase().split(/\s+/).filter(Boolean), [search]);
  const filteredEntries = React.useMemo(() => {
    return entries
      .filter((entry) => {
        if (!tokens.length) return true;
        const haystack = [entry.link.product?.product_code, entry.link.product?.product_name, entry.link.supplier_item_code]
          .filter(Boolean)
          .map((s) => (s as string).toLowerCase());
        return tokens.every((t) => haystack.some((h) => h.includes(t)));
      })
      .filter((entry) => {
        if (!statuses.length) return true;
        if (entry.costs.length === 0) return false;
        return entry.costs.some((c) => statuses.includes(c.status));
      });
  }, [entries, tokens, statuses]);

  const rows: Row[] = React.useMemo(() => {
    const out: Row[] = [];
    for (const entry of filteredEntries) {
      const visibleCosts = statuses.length ? entry.costs.filter((c) => statuses.includes(c.status)) : entry.costs;
      if (visibleCosts.length === 0) {
        out.push({ id: `${entry.link.id}-empty`, entry, cost: null });
      } else {
        for (const cost of visibleCosts) out.push({ id: cost.id, entry, cost });
      }
    }
    return out;
  }, [filteredEntries, statuses]);

  const columns = React.useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: 'price',
        header: 'Price',
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) =>
          row.original.cost ? (
            <span className="tabular-nums">
              {row.original.cost.unit_cost.toFixed(2)} {row.original.cost.currency}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
      },
      {
        id: 'start',
        header: 'Valid from',
        size: 110,
        cell: ({ row }) => (row.original.cost ? (formatPlainDate(row.original.cost.start_date) ?? 'Always') : ''),
      },
      {
        id: 'end',
        header: 'Valid to',
        size: 110,
        cell: ({ row }) => (row.original.cost ? (formatPlainDate(row.original.cost.end_date) ?? 'No end') : ''),
      },
      {
        id: 'status',
        header: 'Status',
        size: 110,
        cell: ({ row }) =>
          row.original.cost ? (
            <Badge variant={STATUS_BADGE_VARIANT[row.original.cost.status]}>{STATUS_LABELS[row.original.cost.status]}</Badge>
          ) : null,
      },
      {
        id: 'source',
        header: 'Source',
        size: 130,
        cell: ({ row }) =>
          row.original.cost ? (
            row.original.cost.source ? (
              <Link
                className="text-primary hover:underline"
                href={`/procurement-management/cost-price-uploads/${row.original.cost.source.change_set_id}`}
              >
                {row.original.cost.source.code}
              </Link>
            ) : (
              <span className="text-muted-foreground">Edited by hand</span>
            )
          ) : null,
      },
      {
        id: 'actions',
        header: '',
        size: 90,
        cell: ({ row }) =>
          canEdit ? (
            row.original.cost ? (
              <Button size="sm" variant="ghost" onClick={() => setDialog({ link: row.original.entry.link, cost: row.original.cost })}>
                Edit
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={() => setDialog({ link: row.original.entry.link, cost: null })}>
                <Plus className="size-3.5" /> Price
              </Button>
            )
          ) : null,
      },
    ],
    [canEdit],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <ListSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search product code, description or supplier code"
          className="w-full sm:w-80"
        />
        <SearchableMultiSelect value={statuses} onChange={(v) => setStatuses(v as CostRowStatus[])} options={STATUS_OPTIONS} placeholder="Status" triggerClassName="w-56" />
      </div>

      {!isLoading && entries.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center gap-3 p-10 text-center">
            <p className="text-sm font-medium">No prices recorded for this supplier yet</p>
            <Button asChild>
              <Link href="/procurement-management/cost-price-uploads">Upload price list</Link>
            </Button>
          </div>
        </Card>
      ) : (
        <DataGrid
          table={table}
          recordCount={rows.length}
          isLoading={isLoading}
          listingKey=""
          tableLayout={{ width: 'fixed', columnsResizable: true }}
          renderGroupHeader={(row: Row, previous: Row | null) => {
            if (previous && previous.entry.link.id === row.entry.link.id) return null;
            const { link } = row.entry;
            return (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium">{link.product?.product_code ?? '-'}</span>
                  <span className="ms-2 text-muted-foreground">{link.product?.product_name ?? ''}</span>
                  {link.supplier_item_code ? (
                    <span className="ms-2 text-muted-foreground">&middot; {link.supplier_item_code}</span>
                  ) : null}
                </div>
                <span className="tabular-nums text-muted-foreground">
                  {link.unit_cost != null ? `${Number(link.unit_cost).toFixed(2)} ${link.currency ?? ''}` : 'no price'}
                </span>
              </div>
            );
          }}
        >
          <Card>
            <CardTable>
              <DataGridTable />
            </CardTable>
          </Card>
        </DataGrid>
      )}

      {dialog ? (
        <CostRowDialog
          open
          onOpenChange={(next) => {
            if (!next) setDialog(null);
          }}
          link={dialog.link}
          cost={dialog.cost}
          onSaved={invalidate}
        />
      ) : null}
    </div>
  );
}

export default SupplierPricesTab;
