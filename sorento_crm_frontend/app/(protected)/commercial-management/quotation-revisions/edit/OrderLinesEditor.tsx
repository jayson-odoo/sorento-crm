'use client';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ProductComboboxSearchable } from '@/app/(protected)/procurement-management/packing-lists/components/ProductComboboxSearchable';
import type { ProductDetail } from '@/app/(protected)/master-data-management/products/types/product.types';
import {
  quotationToleranceTooltipLines,
  toleranceUnitPriceBand,
  unitPriceOutOfToleranceFromProduct,
} from '@/app/(protected)/commercial-management/quotation-revisions/lib/quotationLinePricing';
import { AlertTriangle, GripVertical, Plus, SlidersHorizontal, Trash2 } from 'lucide-react';
import { QuotationLineProductImages } from '@/app/(protected)/commercial-management/quotation-revisions/components/QuotationLineProductImages';
import { cn } from '@/lib/utils';

export type DiscountMode = 'percent' | 'amount';

export type OrderLineRowData = {
  _key: string;
  product_id: string;
  product_code?: string;
  brand?: string;
  description?: string;
  /** Attachment ids (Product Image type) included on this quotation line. */
  product_image_attachment_ids?: string[];
  /** Attachment ids (Technical Spec type) included on this quotation line. */
  technical_spec_attachment_ids?: string[];
  is_optional?: boolean;
  qty: string;
  uom_code: string;
  unit_price: string;
  discount_mode: DiscountMode;
  discount_value: string;
  tax_rate_code: string;
};

type SelectOpt = { code: string; label: string };

const ORDER_LINE_TYPE = 'quotation_order_line';

type DragItem = { index: number; id: string; type: string };

/** Gross line amount before discount (qty × unit price). */
export function orderLineGross(l: OrderLineRowData): number {
  const q = Number(l.qty) || 0;
  const up = Number(l.unit_price) || 0;
  return Math.max(0, q * up);
}

/** Net line amount after discount — matches quotation show view / API snapshot math. */
export function orderLineNetAmount(l: OrderLineRowData): number {
  const q = Number(l.qty) || 0;
  const up = Number(l.unit_price) || 0;
  let line = q * up;
  const v = Number(l.discount_value) || 0;
  if (l.discount_mode === 'percent' && v > 0) line *= 1 - v / 100;
  else if (l.discount_mode === 'amount' && v > 0) line -= v;
  return Math.max(0, line);
}

/** Subtotal (net), discount (gross − net), and gross — same as `lineTotals` on quotation-revisions show page. */
export function orderLinesTotals(lines: OrderLineRowData[]) {
  let sub = 0;
  let gross = 0;
  for (const l of lines) {
    if (l.is_optional) continue;
    gross += orderLineGross(l);
    sub += orderLineNetAmount(l);
  }
  return { subtotal: sub, discountTotal: Math.max(0, gross - sub), gross };
}

export function formatOrderLineMoney(amount: number, currencyCode: string | null | undefined) {
  const code = (currencyCode || 'MYR').toUpperCase();
  try {
    return new Intl.NumberFormat('en-MY', { style: 'currency', currency: code }).format(amount);
  } catch {
    return `${code} ${amount.toFixed(2)}`;
  }
}

const control = 'h-9 rounded-[14px] border-[#d1d5dc] bg-white text-sm shadow-none';

function OrderLineTableRow({
  line,
  index,
  moveLine,
  updateLine,
  removeLine,
  onPickProduct,
  fetchProductOptions,
  uoms,
  taxRates,
  quotedCurrency,
  showUnitCost,
  showAmountColumn,
  productById,
}: {
  line: OrderLineRowData;
  index: number;
  moveLine: (from: number, to: number) => void;
  updateLine: (key: string, patch: Partial<OrderLineRowData>) => void;
  removeLine: (key: string) => void;
  onPickProduct: (lineKey: string, productId: string) => void | Promise<void>;
  fetchProductOptions: (query: string, pageIndex: number) => Promise<{
    data: { id: string; product_code: string; product_name?: string }[];
  }>;
  uoms: SelectOpt[];
  taxRates: SelectOpt[];
  quotedCurrency: string | null | undefined;
  showUnitCost: boolean;
  showAmountColumn: boolean;
  productById: Map<string, ProductDetail>;
}) {
  const [{ isDragging }, drag] = useDrag({
    type: ORDER_LINE_TYPE,
    item: { index, id: line._key, type: ORDER_LINE_TYPE },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  const [, drop] = useDrop<DragItem>({
    accept: ORDER_LINE_TYPE,
    hover(item) {
      const dragIndex = item.index;
      const hoverIndex = index;
      if (dragIndex === hoverIndex) return;
      moveLine(dragIndex, hoverIndex);
      item.index = hoverIndex;
    },
  });

  const productFallback =
    line.product_id && line.product_code
      ? { id: line.product_id, product_code: line.product_code, product_name: line.description }
      : null;

  const net = orderLineNetAmount(line);

  const product = line.product_id ? productById.get(line.product_id) : undefined;
  const warnTol = product ? unitPriceOutOfToleranceFromProduct(Number(line.unit_price) || 0, product) : false;
  const band = product
    ? toleranceUnitPriceBand(
        Number(product.list_price) || 0,
        product.sales_tolerance_type,
        product.sales_tolerance_value,
      )
    : { min: 0, max: 0 };
  const tolTip =
    product?.sales_tolerance_type != null && product.sales_tolerance_value != null
      ? quotationToleranceTooltipLines(
          formatOrderLineMoney(band.min, quotedCurrency),
          formatOrderLineMoney(band.max, quotedCurrency),
        )
      : '';

  const reqProduct = !String(line.product_id ?? '').trim();
  const reqQty = !String(line.qty ?? '').trim();
  const reqUom = !String(line.uom_code ?? '').trim();
  const reqUnitPx = !String(line.unit_price ?? '').trim();

  const unitCostNum = product?.cost_price != null ? Number(product.cost_price) : NaN;
  const costLabel =
    showUnitCost && product && !Number.isNaN(unitCostNum)
      ? formatOrderLineMoney(unitCostNum, quotedCurrency)
      : showUnitCost
        ? '—'
        : null;

  return (
    <tr
      ref={(el) => {
        if (el) drop(el);
      }}
      style={{ opacity: isDragging ? 0.45 : 1 }}
      className="border-b border-[#e5e7eb] bg-white"
    >
      <td className="align-top px-2 py-2">
        <div
          ref={(el) => {
            if (el) drag(el);
          }}
          className={cn(control, 'flex size-9 cursor-grab items-center justify-center active:cursor-grabbing')}
        >
          <GripVertical className="size-4 text-[#6a7282]" />
        </div>
      </td>
      <td className="min-w-[220px] max-w-[340px] align-top px-2 py-2">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <ProductComboboxSearchable
              value={line.product_id}
              onChange={(id) => void onPickProduct(line._key, id)}
              fetchProducts={fetchProductOptions}
              productFallback={productFallback}
              className={cn('w-full', reqProduct && 'border-l-4 border-l-[#e7000b]')}
            />
          </div>
          <QuotationLineProductImages
            productId={line.product_id}
            selectedAttachmentIds={line.product_image_attachment_ids ?? []}
            selectedTechnicalSpecIds={line.technical_spec_attachment_ids ?? []}
            mode="edit"
            onSelectionChange={(ids) => updateLine(line._key, { product_image_attachment_ids: ids })}
            onTechnicalSpecSelectionChange={(ids) => updateLine(line._key, { technical_spec_attachment_ids: ids })}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Input
            className={cn(control, 'w-full')}
            placeholder="Description"
            value={line.description ?? ''}
            onChange={(e) => updateLine(line._key, { description: e.target.value })}
          />
        </div>
      </td>
      <td className="w-[88px] min-w-[72px] align-top px-2 py-2">
        <Input
          inputMode="decimal"
          className={cn(control, 'w-full', reqQty && 'border-l-4 border-l-[#e7000b]')}
          value={line.qty}
          onChange={(e) => updateLine(line._key, { qty: e.target.value })}
        />
      </td>
      <td className="min-w-[120px] align-top px-2 py-2">
        <Select
          value={line.uom_code || '__none__'}
          onValueChange={(v) => updateLine(line._key, { uom_code: v === '__none__' ? '' : v })}
        >
          <SelectTrigger className={cn(control, 'w-full', reqUom && 'border-l-4 border-l-[#e7000b]')}>
            <SelectValue placeholder="UOM" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">—</SelectItem>
            {uoms.map((u) => (
              <SelectItem key={u.code} value={u.code}>
                {u.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
      {showUnitCost ? (
        <td className="min-w-[110px] whitespace-nowrap px-2 py-2 align-top text-sm tabular-nums text-[#101828]">
          {costLabel}
        </td>
      ) : null}
      <td className="min-w-[130px] align-top px-2 py-2">
        <div className="flex items-center gap-1">
          <Input
            inputMode="decimal"
            className={cn(control, 'min-w-0 flex-1', reqUnitPx && 'border-l-4 border-l-[#e7000b]')}
            value={line.unit_price}
            onChange={(e) => updateLine(line._key, { unit_price: e.target.value })}
          />
          {warnTol && tolTip ? (
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
                {tolTip}
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </td>
      <td className="min-w-[200px] max-w-[280px] align-top px-2 py-2">
        <div className="flex items-center gap-2">
          <Select
            value={line.discount_mode}
            onValueChange={(v) =>
              updateLine(line._key, {
                discount_mode: v as DiscountMode,
                discount_value: '',
              })
            }
          >
            <SelectTrigger className={cn(control, 'h-9 w-[88px] shrink-0 px-2')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="percent">%</SelectItem>
              <SelectItem value="amount">Amt</SelectItem>
            </SelectContent>
          </Select>
          <Input
            inputMode="decimal"
            placeholder={line.discount_mode === 'percent' ? '%' : 'Amount'}
            className={cn(control, 'min-w-0 flex-1')}
            value={line.discount_value}
            onChange={(e) => updateLine(line._key, { discount_value: e.target.value })}
          />
        </div>
      </td>
      <td className="min-w-[120px] align-top px-2 py-2">
        <Select
          value={line.tax_rate_code || '__none__'}
          onValueChange={(v) => updateLine(line._key, { tax_rate_code: v === '__none__' ? '' : v })}
        >
          <SelectTrigger className={cn(control, 'w-full')}>
            <SelectValue placeholder="Tax" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">—</SelectItem>
            {taxRates.map((t) => (
              <SelectItem key={t.code} value={t.code}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
      {showAmountColumn ? (
        <td className="min-w-[100px] whitespace-nowrap px-2 py-2 align-top text-end text-sm tabular-nums text-[#101828]">
          {formatOrderLineMoney(net, quotedCurrency)}
        </td>
      ) : null}
      <td className="w-[52px] align-top px-1 py-2">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-[#e7000b] hover:bg-red-50"
          aria-label="Remove line"
          onClick={() => removeLine(line._key)}
        >
          <Trash2 className="size-4" />
        </Button>
      </td>
    </tr>
  );
}

export function OrderLinesEditor({
  lines,
  moveLine,
  updateLine,
  removeLine,
  addLine,
  onPickProduct,
  fetchProductOptions,
  uoms,
  taxRates,
  quotedCurrency,
  showUnitCost,
  onToggleUnitCost,
  productById,
}: {
  lines: OrderLineRowData[];
  moveLine: (from: number, to: number) => void;
  updateLine: (key: string, patch: Partial<OrderLineRowData>) => void;
  removeLine: (key: string) => void;
  addLine: (isOptional?: boolean) => void;
  onPickProduct: (lineKey: string, productId: string) => void | Promise<void>;
  fetchProductOptions: (query: string, pageIndex: number) => Promise<{
    data: { id: string; product_code: string; product_name?: string }[];
  }>;
  uoms: SelectOpt[];
  taxRates: SelectOpt[];
  quotedCurrency: string | null | undefined;
  showUnitCost: boolean;
  onToggleUnitCost: () => void;
  productById: Map<string, ProductDetail>;
}) {
  const tableMin = showUnitCost ? 'min-w-[1180px]' : 'min-w-[1040px]';
  const normalEntries = lines
    .map((line, index) => ({ line, index }))
    .filter((entry) => !entry.line.is_optional);
  const optionalEntries = lines
    .map((line, index) => ({ line, index }))
    .filter((entry) => Boolean(entry.line.is_optional));

  const renderTable = (
    entries: Array<{ line: OrderLineRowData; index: number }>,
    showAmountColumn: boolean,
    emptyLabel: string,
  ) => (
    <div className="overflow-x-auto rounded-xl border border-[#e5e7eb]">
      <table className={cn('w-full border-collapse', tableMin)}>
        <thead>
          <tr className="border-b border-[#e5e7eb] bg-[#f9fafb]">
            <th className="w-12 px-2 py-3 text-start text-xs font-medium text-[#4a5565]" aria-hidden />
            <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">Product</th>
            <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">Qty</th>
            <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">UOM</th>
            {showUnitCost ? <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">Cost</th> : null}
            <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">Unit price</th>
            <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">Discount</th>
            <th className="px-2 py-3 text-start text-xs font-medium text-[#4a5565]">Tax</th>
            {showAmountColumn ? (
              <th className="px-2 py-3 text-end text-xs font-medium text-[#4a5565]">Amount</th>
            ) : null}
            <th className="w-12 px-1 py-3 text-end text-xs font-medium text-[#4a5565]" />
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr>
              <td
                colSpan={showAmountColumn ? (showUnitCost ? 10 : 9) : showUnitCost ? 9 : 8}
                className="py-6 text-center text-sm text-[#6a7282]"
              >
                {emptyLabel}
              </td>
            </tr>
          ) : (
            entries.map(({ line, index }) => (
              <OrderLineTableRow
                key={line._key}
                line={line}
                index={index}
                moveLine={moveLine}
                updateLine={updateLine}
                removeLine={removeLine}
                onPickProduct={onPickProduct}
                fetchProductOptions={fetchProductOptions}
                uoms={uoms}
                taxRates={taxRates}
                quotedCurrency={quotedCurrency}
                showUnitCost={showUnitCost}
                showAmountColumn={showAmountColumn}
                productById={productById}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <TooltipProvider delayDuration={200}>
      <DndProvider backend={HTML5Backend}>
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
            <div className="space-y-3">
              <p className="text-sm font-semibold text-[#101828]">Normal items</p>
              {renderTable(normalEntries, true, 'No normal items.')}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="inline-flex gap-1 self-start rounded-[14px] border-[#e7000b] font-medium text-[#e7000b] hover:bg-red-50"
                onClick={() => addLine(false)}
              >
                <Plus className="size-4" />
                Add line
              </Button>
            </div>
            <div className="space-y-3">
              <p className="text-sm font-semibold text-[#101828]">Optional items</p>
              {renderTable(optionalEntries, false, 'No optional items.')}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="inline-flex gap-1 self-start rounded-[14px] border-[#f59e0b] font-medium text-[#d97706] hover:bg-amber-50"
                onClick={() => addLine(true)}
              >
                <Plus className="size-4" />
                Add optional line
              </Button>
            </div>
          </div>
        </div>
      </DndProvider>
    </TooltipProvider>
  );
}
