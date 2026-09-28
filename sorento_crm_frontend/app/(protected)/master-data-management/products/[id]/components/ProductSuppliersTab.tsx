'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColumnDef, ExpandedState, OnChangeFn } from '@tanstack/react-table';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { getProductSuppliersByProductId } from '../../../../procurement-management/product-suppliers/services/productSupplierService';
import type { ProductSupplier } from '../../../../procurement-management/product-suppliers/types/productSupplier.types';
import { formatPlainDate } from '../../../../procurement-management/cost-price-uploads/lib/formatPlainDate';
import type { ProductSupplierCostRow } from '../../../../procurement-management/cost-price-uploads/types/costPrice.types';
import { ProductSuppliedWithSection } from './ProductSuppliedWithSection';
import { ProductShipsWithSection } from './ProductShipsWithSection';

interface ProductSuppliersTabProps {
  productId: string;
}

/** A dash is "not on file", which is a different fact from zero and must not read as it. */
function fmtTerm(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
}

function fmtMoney(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-';
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : String(value);
}

/** Round 9 (AC-CL-13): the currency in front, "CNY 40.60". */
export function fmtCost(cost: Pick<ProductSupplierCostRow, 'unit_cost' | 'currency'>): string {
  return `${cost.currency} ${fmtMoney(cost.unit_cost)}`;
}

function TextCell({ value }: { value: string }) {
  return (
    <span className="block truncate" title={value}>
      {value}
    </span>
  );
}

const RIGHT = { cellClassName: 'text-right tabular-nums', headerClassName: 'text-right' };

/**
 * Round 9 (AC-CL-12 to AC-CL-15): one supplier's cost prices, opened under its row. A
 * start with no end reads as the start date and a dash; no status pill and no upload code,
 * the buyer reads the dates.
 */
const COST_COLUMNS: ColumnDef<ProductSupplierCostRow>[] = [
  {
    id: 'packaging_method',
    header: 'Packaging method',
    cell: ({ row }) => <TextCell value={row.original.packaging_method || 'standard'} />,
    size: 200,
  },
  {
    id: 'cost',
    header: 'Cost',
    cell: ({ row }) => fmtCost(row.original),
    size: 140,
    meta: RIGHT,
  },
  {
    id: 'start_date',
    header: 'Date start',
    cell: ({ row }) => formatPlainDate(row.original.start_date) ?? '-',
    size: 140,
  },
  {
    id: 'end_date',
    header: 'Date end',
    cell: ({ row }) => formatPlainDate(row.original.end_date) ?? '-',
    size: 140,
  },
];

function SupplierCostPrices({ link }: { link: ProductSupplier }) {
  return (
    <div data-testid="supplier-cost-prices-grid" className="p-3">
      <PanelDataGrid<ProductSupplierCostRow>
        columns={COST_COLUMNS}
        rows={link.costs ?? []}
        getRowId={(row) => row.id}
        listingKey="procurement.product_suppliers.view::product-supplier-costs"
        emptyTitle="No cost prices for this supplier."
        paginate={false}
      />
    </div>
  );
}

const SUPPLIER_COLUMNS: ColumnDef<ProductSupplier>[] = [
  {
    id: 'supplier_code',
    header: 'Supplier code',
    cell: ({ row }) => <TextCell value={row.original.supplier?.supplier_code || '-'} />,
    size: 130,
    // The shared grid draws this full width under an open row (PanelDataGrid `expanded`).
    meta: { expandedContent: (link: ProductSupplier) => <SupplierCostPrices link={link} /> },
  },
  {
    id: 'supplier_name',
    header: 'Supplier name',
    cell: ({ row }) => <TextCell value={row.original.supplier?.supplier_name || '-'} />,
    size: 220,
  },
  {
    id: 'primary',
    header: 'Primary',
    cell: ({ row }) => (row.original.is_primary_supplier ? 'Yes' : 'No'),
    size: 90,
  },
  {
    id: 'lead_time',
    header: 'Lead time (days)',
    cell: ({ row }) => fmtTerm(row.original.standard_lead_time_days ?? row.original.lead_time_days),
    size: 140,
    meta: RIGHT,
  },
  {
    id: 'unit_cost',
    header: 'Unit cost',
    cell: ({ row }) => fmtMoney(row.original.unit_cost),
    size: 110,
    meta: RIGHT,
  },
  {
    id: 'currency',
    header: 'Currency',
    cell: ({ row }) => fmtTerm(row.original.currency),
    size: 100,
  },
  {
    id: 'moq',
    header: 'Minimum order',
    cell: ({ row }) => fmtTerm(row.original.moq),
    size: 130,
    meta: RIGHT,
  },
  {
    id: 'order_multiple',
    header: 'Order multiple',
    cell: ({ row }) => fmtTerm(row.original.order_multiple),
    size: 130,
    meta: RIGHT,
  },
  {
    // The supplier's own spelling of this product's code, set on the loading plan's
    // Supplier codes tab (S4); read-only here.
    id: 'their_code',
    header: 'Their code',
    cell: ({ row }) => <TextCell value={fmtTerm(row.original.supplier_item_code)} />,
    size: 140,
  },
];

export default function ProductSuppliersTab({ productId }: ProductSuppliersTabProps) {
  const [openRow, setOpenRow] = useState<string | null>(null);
  const { data: productSuppliers, isLoading, error } = useQuery({
    queryKey: ['product-suppliers', productId],
    queryFn: () => getProductSuppliersByProductId(productId),
    enabled: !!productId,
  });

  const suppliers = useMemo(() => productSuppliers ?? [], [productSuppliers]);

  const expanded: ExpandedState = openRow ? { [openRow]: true } : {};
  const onExpandedChange: OnChangeFn<ExpandedState> = (updater) => {
    const next = typeof updater === 'function' ? updater(expanded) : updater;
    const openIds = Object.keys(next).filter((id) => (next as Record<string, boolean>)[id]);
    setOpenRow(openIds[0] ?? null);
  };

  return (
    <div className="space-y-6">
      <div data-testid="product-suppliers-grid">
        <PanelDataGrid<ProductSupplier>
          title="Suppliers"
          columns={SUPPLIER_COLUMNS}
          rows={suppliers}
          getRowId={(row) => row.id}
          listingKey="procurement.product_suppliers.view::product-suppliers"
          isLoading={isLoading}
          error={error}
          emptyTitle="No suppliers configured for this product."
          emptyBody="Edit the product to add suppliers."
          searchPlaceholder="Search supplier"
          searchOf={(row) =>
            [row.supplier?.supplier_code, row.supplier?.supplier_name, row.supplier_item_code]
              .filter(Boolean)
              .join(' ')
          }
          expanded={expanded}
          onExpandedChange={onExpandedChange}
          onRowClick={(row) => setOpenRow((cur) => (cur === row.id ? null : row.id))}
        />
      </div>

      {/* PLAN-scm-supplied-with-companions.md: this product's own bundling rules
          ("Supplied with", it is the companion) and the mirror of anyone else's
          ("Ships with", it is a host). A product can be both at once, so both
          sections render unconditionally, each with its own empty state. */}
      <ProductSuppliedWithSection companionProductId={productId} />
      <ProductShipsWithSection hostProductId={productId} />
    </div>
  );
}
