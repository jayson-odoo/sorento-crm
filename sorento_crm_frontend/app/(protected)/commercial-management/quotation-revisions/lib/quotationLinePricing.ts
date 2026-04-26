import type { Product } from '@/app/(protected)/master-data-management/products/types/product.types';

export type QuotationPricingLineHint = {
  line_index: number;
  product_id: string | null;
  unit_cost: string | null;
  list_price: string | null;
  sales_tolerance_type: string | null;
  sales_tolerance_value: string | null;
  min_unit_price: string | null;
  max_unit_price: string | null;
  unit_price_out_of_tolerance: boolean;
};

/** Mirrors backend `tolerance_band` for product list price ± tolerance. */
export function toleranceUnitPriceBand(
  listPrice: number,
  tolType: string | null | undefined,
  tolVal: number | null | undefined,
): { min: number; max: number } {
  const lp = Math.max(0, Number(listPrice) || 0);
  if (!tolType || tolVal == null || tolVal < 0) {
    return { min: lp, max: lp };
  }
  if (tolType === 'percent') {
    const delta = lp * (tolVal / 100);
    return { min: Math.max(0, lp - delta), max: lp + delta };
  }
  if (tolType === 'amount') {
    return { min: Math.max(0, lp - tolVal), max: lp + tolVal };
  }
  return { min: lp, max: lp };
}

export function unitPriceOutOfToleranceFromProduct(
  unitPrice: number,
  product: Pick<Product, 'list_price' | 'sales_tolerance_type' | 'sales_tolerance_value'> | null | undefined,
): boolean {
  if (!product?.sales_tolerance_type || product.sales_tolerance_value == null) return false;
  const lp = Number(product.list_price) || 0;
  const { min, max } = toleranceUnitPriceBand(lp, product.sales_tolerance_type, product.sales_tolerance_value);
  const u = Number(unitPrice) || 0;
  return u < min || u > max;
}

export function quotationToleranceTooltipLines(
  minFormatted: string,
  maxFormatted: string,
): string {
  return [
    `Acceptable unit price range: ${minFormatted} – ${maxFormatted}.`,
    'This unit price is outside that range and is subject to approval.',
  ].join(' ');
}

/** Total cost of goods: sum of (qty × unit cost) for lines with a known unit cost (per product). */
export function orderLinesTotalCostBasis(
  lines: { qty: string }[],
  hints: QuotationPricingLineHint[] | undefined,
): number {
  if (!hints?.length) return 0;
  let t = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const h = hints[i];
    if (!h?.unit_cost) continue;
    const uc = Number(h.unit_cost);
    if (Number.isNaN(uc)) continue;
    t += (Number(lines[i].qty) || 0) * uc;
  }
  return t;
}
