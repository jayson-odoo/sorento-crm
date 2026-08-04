'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
// The one decimal-exact money formatter in the repo. Imported rather than re-implemented: a
// second formatter is how the public page and the PDF end up disagreeing by a cent, and the
// customer reading this screen is the person who would notice.
import {
  formatMyrExact,
  formatQty,
} from '@/app/(protected)/project-sales/[projectId]/components/POIntakeMoney';
import type {
  QuotationSignLine,
  QuotationSignScope,
} from '../../services/quotationSignService';

/** The sample workbook's column set, minus the product image. */
const COLUMNS = 9;

function text(value: string | null | undefined): string {
  return value?.trim() ? value : '-';
}

/**
 * The money column for ONE line.
 *
 * A rate-only line prints the WORDS. `RM 0.00` would tell the customer the item is free and a
 * blank cell reads as a rendering fault, while what is true is that they are being quoted a rate
 * nobody adds into the total (AC-C2 / AC-D3, and the same rule the PDF renderer follows).
 */
function LineAmount({ line }: { line: QuotationSignLine }) {
  if (line.is_rate_only) {
    return <span className="italic text-muted-foreground">rate only</span>;
  }
  return <span className="tabular-nums">{formatMyrExact(line.amount ?? '0')}</span>;
}

function ScopeTable({ lines }: { lines: QuotationSignLine[] }) {
  // A band label heads its section ONCE, above the line that opens it. Repeating it on every row
  // is how the printed quotation stops being readable.
  let currentBand: string | null = null;

  return (
    // Hand-rolled and read-only on purpose: this is a printed quotation being read by a stranger
    // on a phone, with nothing to sort, page or select, so DataGrid's toolbar and pagination
    // would be furniture in the way. `overflow-x-auto` + `min-w-0` keep the wide table scrolling
    // inside its own gutter instead of dragging the whole PAGE sideways at 375px.
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="min-w-[140px] px-2 py-2 text-left font-semibold">Item</th>
            <th className="min-w-[160px] px-2 py-2 text-left font-semibold">Technical spec</th>
            <th className="min-w-[200px] px-2 py-2 text-left font-semibold">Description</th>
            <th className="min-w-[100px] px-2 py-2 text-left font-semibold">Brand</th>
            <th className="min-w-[120px] px-2 py-2 text-left font-semibold">Product code</th>
            <th className="min-w-[70px] px-2 py-2 text-right font-semibold">Qty</th>
            <th className="min-w-[120px] px-2 py-2 text-right font-semibold">Unit rate</th>
            <th className="min-w-[140px] px-2 py-2 text-left font-semibold">Complete set</th>
            <th className="min-w-[120px] px-2 py-2 text-right font-semibold">Amount</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => {
            const band = line.band_label?.trim() ? line.band_label.trim() : null;
            const opensBand = band !== null && band !== currentBand;
            if (opensBand) currentBand = band;
            return (
              <React.Fragment key={index}>
                {opensBand && (
                  <tr className="bg-muted/60">
                    <td
                      colSpan={COLUMNS}
                      className="px-2 py-2 text-xs font-semibold uppercase tracking-wide"
                    >
                      {band}
                    </td>
                  </tr>
                )}
                <tr className="border-t border-border align-top">
                  <td className="px-2 py-2">{text(line.item_label)}</td>
                  <td className="px-2 py-2 text-muted-foreground">{text(line.technical_spec)}</td>
                  <td className="px-2 py-2">{text(line.description)}</td>
                  <td className="px-2 py-2">{text(line.brand)}</td>
                  <td className="px-2 py-2">{text(line.product_code)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatQty(line.quantity)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {formatMyrExact(line.unit_price)}
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">{text(line.complete_set)}</td>
                  <td className="px-2 py-2 text-right">
                    <LineAmount line={line} />
                  </td>
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Every scope the issue carried, each with its own total, then the grand total.
 *
 * Rendered even when the issue carries none: a quotation with no scopes is a state somebody can
 * produce, and a section that vanishes reads as a broken page to the person being asked to sign.
 */
export function QuotationSignScopes({
  scopes,
  grandTotal,
}: {
  scopes: QuotationSignScope[];
  grandTotal: string;
}) {
  return (
    <div className="space-y-4">
      {scopes.length === 0 ? (
        <Card>
          <CardContent className="px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              This quotation has no priced items on it.
            </p>
          </CardContent>
        </Card>
      ) : (
        scopes.map((scope, index) => (
          <Card key={`${scope.scope_label}-${index}`}>
            <CardHeader>
              <CardTitle className="min-w-0 break-words text-sm">
                {text(scope.scope_label)}
              </CardTitle>
            </CardHeader>
            {/* min-w-0 on the content, or the wide table refuses to shrink and the page itself
                scrolls sideways on a phone. */}
            <CardContent className="min-w-0 space-y-3 px-3 py-4 sm:px-6">
              {scope.lines.length === 0 ? (
                <p className="text-sm text-muted-foreground">No items under this section.</p>
              ) : (
                <ScopeTable lines={scope.lines} />
              )}
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
                <span className="text-muted-foreground">Section total</span>
                <span className="font-semibold tabular-nums">
                  {formatMyrExact(scope.scope_total)}
                </span>
              </div>
            </CardContent>
          </Card>
        ))
      )}

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-2 py-4">
          <span className="text-sm font-semibold uppercase tracking-wide">Total amount</span>
          <span className="text-base font-semibold tabular-nums">
            {formatMyrExact(grandTotal)}
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
