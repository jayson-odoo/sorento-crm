'use client';

import Link from 'next/link';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertTriangle, SlidersHorizontal } from 'lucide-react';
import {
  orderLinesTotalCostBasis,
  quotationToleranceTooltipLines,
  type QuotationPricingLineHint,
} from '@/app/(protected)/commercial-management/quotation-revisions/lib/quotationLinePricing';
import { QuotationLineProductImages } from '@/app/(protected)/commercial-management/quotation-revisions/components/QuotationLineProductImages';

type SelectOpt = { code: string; label: string };

export type ShowOrderLine = {
  _key: string;
  product_id?: string;
  product_image_attachment_ids?: string[];
  technical_spec_attachment_ids?: string[];
  product_code?: string;
  brand?: string;
  description?: string;
  is_optional?: boolean;
  qty: string;
  uom_code: string;
  unit_price: string;
  discount_pct: string;
  discount_amt: string;
  tax_rate_code: string;
};

function formatMoneyAmount(amount: number, currencyCode: string | null | undefined) {
  const code = (currencyCode || 'MYR').toUpperCase();
  try {
    return new Intl.NumberFormat('en-MY', { style: 'currency', currency: code }).format(amount);
  } catch {
    return `${code} ${amount.toFixed(2)}`;
  }
}

function lineDiscountDisplay(line: ShowOrderLine, currencyCode: string | null | undefined) {
  const da = Number(line.discount_amt) || 0;
  if (da > 0) return formatMoneyAmount(da, currencyCode);
  const dp = Number(line.discount_pct) || 0;
  if (dp > 0) return `${dp}%`;
  return formatMoneyAmount(0, currencyCode);
}

function lineNetAmount(l: ShowOrderLine): number {
  const q = Number(l.qty) || 0;
  const up = Number(l.unit_price) || 0;
  let line = q * up;
  const dp = Number(l.discount_pct) || 0;
  if (dp > 0) line *= 1 - dp / 100;
  const da = Number(l.discount_amt) || 0;
  if (da > 0) line -= da;
  return Math.max(0, line);
}

type Props = {
  lines: ShowOrderLine[];
  uoms: SelectOpt[];
  taxRates: SelectOpt[];
  quotedCurrency: string | null | undefined;
  pricingLineHints?: QuotationPricingLineHint[] | null;
  totals: { subtotal: number; discountTotal: number };
  showUnitCost: boolean;
  onToggleUnitCost: () => void;
  emptyMessage?: string;
};

export function QuotationOrderLinesReadOnly({
  lines,
  uoms,
  taxRates,
  quotedCurrency,
  pricingLineHints,
  totals,
  showUnitCost,
  onToggleUnitCost,
  emptyMessage = 'No order lines.',
}: Props) {
  const normalEntries = lines
    .map((line, lineIndex) => ({ line, lineIndex }))
    .filter((entry) => !entry.line.is_optional);
  const optionalEntries = lines
    .map((line, lineIndex) => ({ line, lineIndex }))
    .filter((entry) => Boolean(entry.line.is_optional));
  const normalLines = normalEntries.map((e) => e.line);
  const normalHints = normalEntries
    .map((e) => pricingLineHints?.[e.lineIndex] ?? null)
    .filter((h): h is QuotationPricingLineHint => Boolean(h));
  const costBasis = orderLinesTotalCostBasis(normalLines, normalHints);
  const hasCostData = normalHints.some(
    (h) => h?.unit_cost != null && String(h.unit_cost).trim() !== '' && !Number.isNaN(Number(h.unit_cost)),
  );
  const marginAmt = totals.subtotal - costBasis;
  const marginPct = totals.subtotal > 0 ? (marginAmt / totals.subtotal) * 100 : 0;

  const colSpanBase = showUnitCost ? 8 : 7;

  const renderTable = (
    entries: Array<{ line: ShowOrderLine; lineIndex: number }>,
    showAmountColumn: boolean,
    emptyLabel: string,
  ) => (
    <div className="overflow-hidden rounded-xl border border-[#e5e7eb]">
      <Table>
        <TableHeader>
          <TableRow className="border-b border-[#e5e7eb] bg-[#f9fafb] hover:bg-[#f9fafb]">
            <TableHead className="h-10 text-xs font-medium text-[#4a5565]">Product</TableHead>
            <TableHead className="h-10 text-xs font-medium text-[#4a5565]">Quantity</TableHead>
            <TableHead className="h-10 text-xs font-medium text-[#4a5565]">UOM</TableHead>
            {showUnitCost ? <TableHead className="h-10 text-xs font-medium text-[#4a5565]">Cost</TableHead> : null}
            <TableHead className="h-10 text-xs font-medium text-[#4a5565]">Unit price</TableHead>
            <TableHead className="h-10 text-xs font-medium text-[#4a5565]">Discount</TableHead>
            <TableHead className="h-10 text-xs font-medium text-[#4a5565]">Tax</TableHead>
            {showAmountColumn ? <TableHead className="h-10 text-end text-xs font-medium text-[#4a5565]">Amount</TableHead> : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={showAmountColumn ? colSpanBase : colSpanBase - 1}
                className="text-muted-foreground py-8 text-center text-sm"
              >
                {emptyLabel}
              </TableCell>
            </TableRow>
          ) : (
            entries.map(({ line, lineIndex }) => {
              const hint = pricingLineHints?.[lineIndex];
              const uomLabel =
                uoms.find((u) => u.code === line.uom_code)?.label ?? (line.uom_code.trim() ? line.uom_code : '—');
              const taxLabel =
                !line.tax_rate_code.trim()
                  ? '—'
                  : taxRates.find((t) => t.code === line.tax_rate_code)?.label ?? line.tax_rate_code;
              const productCode = (line.product_code || '').trim();
              const productLabel = productCode || (line.description || '').trim() || '—';
              const productIdForImages = line.product_id?.trim() ?? '';
              const unitPriceNum = Number(line.unit_price) || 0;
              const warn = Boolean(hint?.unit_price_out_of_tolerance);
              const minS = hint?.min_unit_price;
              const maxS = hint?.max_unit_price;
              const tooltipText =
                warn && minS != null && maxS != null
                  ? quotationToleranceTooltipLines(
                      formatMoneyAmount(Number(minS), quotedCurrency),
                      formatMoneyAmount(Number(maxS), quotedCurrency),
                    )
                  : '';

              const unitCostDisplay =
                hint?.unit_cost != null && hint.unit_cost !== '' ? formatMoneyAmount(Number(hint.unit_cost), quotedCurrency) : '—';

              return (
                <TableRow key={line._key} className="border-b border-[#e5e7eb]">
                  <TableCell className="py-3 text-sm text-[#101828]">
                    <div className="flex items-start gap-2">
                      {productIdForImages ? (
                        <Link
                          href={`/master-data-management/products/${encodeURIComponent(productIdForImages)}`}
                          className="min-w-0 flex-1 font-medium text-[#e7000b] hover:underline"
                          title="Open product"
                        >
                          <span>{productLabel}</span>
                        </Link>
                      ) : (
                        <span className="min-w-0 flex-1">
                          <span>{productLabel}</span>
                        </span>
                      )}
                      {productIdForImages ? (
                        <QuotationLineProductImages
                          productId={productIdForImages}
                          selectedAttachmentIds={line.product_image_attachment_ids ?? []}
                          mode="view"
                        />
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="py-3 text-sm text-[#101828]">{line.qty}</TableCell>
                  <TableCell className="py-3 text-sm text-[#101828]">{uomLabel}</TableCell>
                  {showUnitCost ? <TableCell className="py-3 text-sm tabular-nums text-[#101828]">{unitCostDisplay}</TableCell> : null}
                  <TableCell className="py-3 text-sm tabular-nums text-[#101828]">
                    <div className="flex items-center gap-1.5">
                      <span>{formatMoneyAmount(unitPriceNum, quotedCurrency)}</span>
                      {warn ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              className="inline-flex shrink-0 text-amber-600 hover:text-amber-700"
                              aria-label="Unit price outside tolerance"
                            >
                              <AlertTriangle className="size-4" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs text-sm leading-snug">
                            {tooltipText}
                          </TooltipContent>
                        </Tooltip>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="py-3 text-sm tabular-nums text-[#101828]">{lineDiscountDisplay(line, quotedCurrency)}</TableCell>
                  <TableCell className="py-3 text-sm text-[#101828]">{taxLabel}</TableCell>
                  {showAmountColumn ? (
                    <TableCell className="py-3 text-end text-sm tabular-nums text-[#101828]">
                      {formatMoneyAmount(lineNetAmount(line), quotedCurrency)}
                    </TableCell>
                  ) : null}
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
  );

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-3">
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2 rounded-[14px]"
            onClick={onToggleUnitCost}
          >
            <SlidersHorizontal className="size-4 text-[#6a7282]" aria-hidden />
            {showUnitCost ? 'Hide cost' : 'Show cost'}
          </Button>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-[#101828]">Normal items</p>
            {renderTable(normalEntries, true, emptyMessage)}
          </div>
          <div className="space-y-2">
            <p className="text-sm font-semibold text-[#101828]">Optional items</p>
            {renderTable(optionalEntries, false, 'No optional items.')}
          </div>
        </div>

        <div className="ms-auto flex w-full max-w-sm flex-col gap-2">
          <div className="flex justify-between text-sm">
            <span className="text-[#4a5565]">Subtotal</span>
            <span className="tabular-nums text-[#101828]">{formatMoneyAmount(totals.subtotal, quotedCurrency)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-[#4a5565]">Discount</span>
            <span className="tabular-nums text-[#101828]">
              {formatMoneyAmount(totals.discountTotal, quotedCurrency)}
            </span>
          </div>
          <div className="flex justify-between border-t border-[#e5e7eb] pt-2 text-base">
            <span className="text-[#101828]">Total</span>
            <span className="tabular-nums font-normal text-[#101828]">
              {formatMoneyAmount(totals.subtotal, quotedCurrency)}
            </span>
          </div>
          <div className="flex justify-between pt-1 text-sm">
            <span className="text-[#4a5565]">Margin</span>
            <span className="tabular-nums font-medium text-[#008236]">
              {hasCostData ? formatMoneyAmount(marginAmt, quotedCurrency) : '—'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-[#4a5565]">Margin %</span>
            <span className="tabular-nums font-medium text-[#008236]">
              {hasCostData ? `${marginPct.toFixed(2)}%` : '—'}
            </span>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
