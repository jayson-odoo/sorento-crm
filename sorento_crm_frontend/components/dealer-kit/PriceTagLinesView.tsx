'use client';

/**
 * A price tag request's lines, read-only: Item, Qty (tags), List price, and in Selling mode the
 * line's Promotion and Selling price, with each line's package parts and warning under it.
 *
 * Shared by the portal's price tag form (its read view) and the CRM request page a salesperson reads
 * their own request on (PORTAL-P4-REQUESTS S7b round 2). Moved out of
 * `app/(auth)/portal/components/PriceTagRequestForm.tsx` unchanged.
 */

import { Fragment } from 'react';
import { Badge } from '@/components/ui/badge';
import { promotionOptionName } from '@/lib/dealer-kit/line-pricing-types';
import { formatRM } from '@/lib/dealer-kit/price-tag-draft-lines';
import { sameDisplayText } from '@/lib/product-display';
import type { PriceMode } from '@/app/(auth)/portal/lib/price-tag-request-service';

/** What the table reads off a saved line. The portal's and the Dealer Kit's detail lines both carry it. */
export interface PriceTagViewLine {
  id: string;
  line_type: 'product' | 'product_set';
  product_id: string | null;
  name: string;
  code: string;
  quantity: number;
  remarks?: string | null;
  list_price?: number | null;
  sell_price?: number | null;
  promotion_name?: string | null;
  promotion_expired_on?: string | null;
  sell_price_basis?: 'manual' | 'promotion' | 'list' | null;
  parts?: Array<{
    id: string;
    product_id: string | null;
    code: string | null;
    name: string | null;
    role: string | null;
    candidates: Array<{ code: string }>;
  }>;
  package_warning?: string | null;
}

/** AC-S1-10: a submitted line's List price, read straight off what the
 *  server resolved - shared between the desktop `<td>` column (no label -
 *  the header already names it) and the mobile stack under the Item cell
 *  (label kept there, no header to read it off). Never both at once, see
 *  `isMobile`. */
function viewListPriceCell(line: PriceTagViewLine, withLabel: boolean) {
  return (
    <div>
      {withLabel && (
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          List price
        </div>
      )}
      <div className="text-sm font-medium whitespace-nowrap">
        {formatRM(line.list_price)}
      </div>
    </div>
  );
}

function viewPromotionCell(line: PriceTagViewLine, withLabel: boolean) {
  return (
    <div>
      {withLabel && (
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          Promotion
        </div>
      )}
      <div className="text-sm font-medium">
        {line.promotion_name != null
          ? promotionOptionName({
              description: line.promotion_name,
              expired_on: line.promotion_expired_on,
            })
          : line.sell_price_basis === 'manual'
            ? 'Manual price'
            : '-'}
      </div>
    </div>
  );
}

function viewSellingPriceCell(line: PriceTagViewLine, withLabel: boolean) {
  return (
    <div>
      {withLabel && (
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          Selling price
        </div>
      )}
      <div className="text-sm font-medium whitespace-nowrap">
        {formatRM(line.sell_price)}
      </div>
    </div>
  );
}

interface PriceTagLinesViewProps {
  lines: PriceTagViewLine[];
  priceMode: PriceMode;
  /** Below the mobile breakpoint the price fields stack under the Item cell (AC-S1-11). */
  isMobile: boolean;
}

export function PriceTagLinesView({ lines, priceMode, isMobile }: PriceTagLinesViewProps) {
  const viewSelling = priceMode === 'selling';
  const viewSpan = isMobile ? 4 : viewSelling ? 7 : 5;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] table-fixed text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="w-10 px-2 py-2 text-left">#</th>
            <th
              className={
                // Owner ruling on review: matches the edit
                // table's Item width per mode exactly, so
                // View and Edit share the layout - Item stays
                // the widest column in every mode.
                isMobile
                  ? 'w-[46%] px-2 py-2 text-left'
                  : viewSelling
                    ? 'w-[31%] px-2 py-2 text-left'
                    : 'w-[43%] px-2 py-2 text-left'
              }
            >
              Item
            </th>
            <th
              className={
                isMobile
                  ? 'w-[12%] px-2 py-2 text-left'
                  : viewSelling
                    ? 'w-[9%] px-2 py-2 text-left'
                    : 'w-[12%] px-2 py-2 text-left'
              }
            >
              Qty (tags)
            </th>
            {!isMobile && (
              <th
                className={
                  viewSelling
                    ? 'w-[13%] px-2 py-2 text-left'
                    : 'w-[14%] px-2 py-2 text-left'
                }
              >
                List price
              </th>
            )}
            {!isMobile && viewSelling && (
              <>
                <th className="w-[14%] px-2 py-2 text-left">
                  Promotion
                </th>
                <th className="w-[12%] px-2 py-2 text-left">
                  Selling price
                </th>
              </>
            )}
            <th
              className={
                // No trailing action column here (nothing to
                // delete on a read-only line), so Remarks
                // absorbs the edit table's action-column share
                // too.
                isMobile
                  ? 'w-[42%] px-2 py-2 text-left'
                  : viewSelling
                    ? 'w-[21%] px-2 py-2 text-left'
                    : 'w-[31%] px-2 py-2 text-left'
              }
            >
              Remarks
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => {
            const hasPricing =
              line.line_type === 'product' && !!line.product_id;
            return (
              <Fragment key={line.id}>
                <tr className="border-t border-border align-top">
                  <td className="px-2 py-2 text-muted-foreground">
                    {index + 1}
                  </td>
                  <td className="px-2 py-2">
                    <div
                      className="font-medium truncate"
                      title={line.name}
                    >
                      {line.name}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {line.line_type === 'product' ? 'Product' : 'Set'}
                      {line.code && !sameDisplayText(line.code, line.name) ? ` - ${line.code}` : ''}
                    </div>
                    {/* AC-S1-10/AC-S1-11: below the app's 992px
                        mobile breakpoint (useIsMobile), the same
                        fields stack here instead of living in
                        their own columns. */}
                    {isMobile && hasPricing && (
                      <div
                        data-testid="line-pricing-stack"
                        className="mt-2 flex flex-wrap items-center gap-4 border-l-2 border-border pl-3"
                      >
                        {viewListPriceCell(line, true)}
                        {viewSelling && viewPromotionCell(line, true)}
                        {viewSelling && viewSellingPriceCell(line, true)}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-2">{line.quantity}</td>
                  {!isMobile && (
                    <td className="px-2 py-2">
                      {hasPricing ? viewListPriceCell(line, false) : null}
                    </td>
                  )}
                  {!isMobile && viewSelling && (
                    <>
                      <td className="px-2 py-2">
                        {hasPricing ? viewPromotionCell(line, false) : null}
                      </td>
                      <td className="px-2 py-2">
                        {hasPricing ? viewSellingPriceCell(line, false) : null}
                      </td>
                    </>
                  )}
                  <td
                    className="px-2 py-2 text-muted-foreground truncate"
                    title={line.remarks ?? undefined}
                  >
                    {line.remarks || '-'}
                  </td>
                </tr>
                {/* The package under the line, exactly as it was asked
                    for (AC-S2-8): the parts that go on the tag, and each
                    group still left open. */}
                {(line.parts ?? []).map((part) => (
                  <tr key={part.id} className="align-top">
                    <td colSpan={viewSpan} className="px-2 pb-2 pl-9">
                      <div className="border-l-2 border-border pl-3 text-sm">
                        {part.product_id ? (
                          <>
                            <span
                              className="truncate"
                              title={part.name ?? undefined}
                            >
                              {part.name || part.code}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {part.code && !sameDisplayText(part.code, part.name) ? ` - ${part.code}` : ''}
                              {part.role ? ` (${part.role})` : ''}
                            </span>
                          </>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {part.role ? `${part.role}: ` : ''}
                            {part.candidates
                              .map((candidate) => candidate.code)
                              .join(' / ')}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {line.package_warning ? (
                  <tr>
                    <td colSpan={viewSpan} className="px-2 pb-2 pl-9">
                      <div className="flex flex-wrap items-center gap-1.5 border-l-2 border-border pl-3">
                        <Badge variant="warning" appearance="light" size="sm">
                          Package warning
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {line.package_warning}
                        </span>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
