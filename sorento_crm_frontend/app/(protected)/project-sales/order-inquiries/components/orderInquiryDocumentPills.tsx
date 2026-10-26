'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import type {
  OrderInquiryDeadReason,
  OrderInquiryLinkReceipt,
} from '../../_shared/types/orderInquiry.types';

/**
 * REV design (17 Sep review round): the row's own one-word marks - `via PO`/`via SPO`,
 * `received`, `reallocate`/`unlink`, `used`, `note` - shared ONE pill from here on,
 * rather than four hand-rolled spellings of `text-2xs text-muted-foreground` (one of
 * them a literal `text-[var(--color-warning-accent,...)]` colour). The same `Badge`
 * idiom the `+N` pill beside them already used (`size="sm" appearance="light" asChild`);
 * `warning` is the design system's own token for the amber marks, never a literal one.
 *
 * Lives here, beside `DocumentStatePills`, so the worklist columns, the Lines tab and the
 * backing-documents dialog all draw it from one module.
 */
export function WorklistPill({
  as = 'span',
  warning = false,
  destructive = false,
  testId,
  onClick,
  ariaLabel,
  children,
}: {
  as?: 'span' | 'button';
  warning?: boolean;
  /** LINKAGE-UNIFY U3 (Q5): the red "PO cancelled" / "SPO withdrawn" marks. */
  destructive?: boolean;
  testId: string;
  onClick?: (event: React.MouseEvent) => void;
  ariaLabel?: string;
  children: React.ReactNode;
}) {
  const variant = destructive ? 'destructive' : warning ? 'warning' : 'secondary';
  return (
    <Badge asChild size="sm" variant={variant} appearance="light">
      {as === 'button' ? (
        <button
          type="button"
          data-testid={testId}
          aria-label={ariaLabel}
          className="shrink-0"
          onClick={onClick}
        >
          {children}
        </button>
      ) : (
        <span data-testid={testId} className="shrink-0">
          {children}
        </span>
      )}
    </Badge>
  );
}

const DEAD_LABEL: Record<OrderInquiryDeadReason, string> = {
  po_cancelled: 'PO cancelled',
  spo_withdrawn: 'SPO withdrawn',
};

function receiptText(receipt: OrderInquiryLinkReceipt): string {
  const qty = formatInquiryQty(receipt.qty);
  return receipt.bin ? `Received ${qty} at ${receipt.bin}` : `Received ${qty}`;
}

/**
 * LINKAGE-UNIFY U3: receipts added up per bin, in first-seen order - several placements
 * on one document line landing at one bin read as one figure.
 */
export function receiptsByBin(receipts: OrderInquiryLinkReceipt[]): OrderInquiryLinkReceipt[] {
  const totals = new Map<string, number>();
  for (const receipt of receipts) {
    const bin = receipt.bin ?? '';
    totals.set(bin, (totals.get(bin) ?? 0) + Number(receipt.qty));
  }
  return [...totals.entries()].map(([bin, qty]) => ({
    qty: String(Number(qty.toFixed(4))),
    bin: bin || null,
  }));
}

/**
 * Below this cell width the receipt pills give way to one compact chip (owner, #1870 hand
 * test: "the focus is on the SPO number; if I resize narrow I still need to see the
 * number"). The cell root carries `@container`; at 220px the number, a draft mark and a
 * "via PO" still fit, a readable receipt no longer does.
 */
const RECEIPTS_HIDE = '@max-[220px]:hidden';
const FALLBACK_SHOW = '@max-[220px]:inline-flex';

/**
 * LINKAGE-UNIFY U3 (AC-D1, AC-D3, AC-D4): the state pills beside ONE document line chip,
 * the same piece on the worklist (`DocumentsCell`), the Lines tab (`DocumentCell`) and
 * the backing-documents dialog, so the screens agree by construction. Red "PO cancelled"
 * / "SPO withdrawn" for a dead document (Q5); one "Received <qty> at <bin>" pill per bin
 * the goods landed at (Q1, Q6). A PO chip only ever carries the PO line's own receipts
 * (Q4); goods that went on through an SPO are on the SPO's chip.
 *
 * Round 5 (owner): the receipt pills are quieter than the number and give way FIRST - they
 * ellipsize (full wording in `title`), and in a narrow cell they hide behind one compact
 * "Received" chip whose label names every receipt and which opens the same view as the
 * cell's "+N" (`onShowAll`). The number itself never truncates.
 */
export function DocumentStatePills({
  receipts,
  deadReason,
  testIdPrefix,
  testIdSuffix,
  onOpen,
  onShowAll,
}: {
  receipts: OrderInquiryLinkReceipt[];
  deadReason: OrderInquiryDeadReason | null;
  /** Test ids read `<prefix>-received-<suffix>` (then `-1`, `-2` for further bins) and
   * `<prefix>-dead-<suffix>`. */
  testIdPrefix: string;
  testIdSuffix: string;
  /** Makes each receipt pill a button that opens the document, as the chip does. */
  onOpen?: (event: React.MouseEvent) => void;
  /** The narrow-cell chip opens what the cell's "+N" opens. No chip without it. */
  onShowAll?: (event: React.MouseEvent) => void;
}) {
  const texts = receipts.map(receiptText);
  return (
    <>
      {deadReason ? (
        <WorklistPill destructive testId={`${testIdPrefix}-dead-${testIdSuffix}`}>
          {DEAD_LABEL[deadReason]}
        </WorklistPill>
      ) : null}
      {receipts.length ? (
        <span className={`flex min-w-0 items-center gap-1 overflow-hidden ${RECEIPTS_HIDE}`}>
          {receipts.map((receipt, index) => {
            const testId = `${testIdPrefix}-received-${testIdSuffix}${index ? `-${index}` : ''}`;
            const className =
              'min-w-0 truncate rounded-sm px-1 text-2xs leading-4 text-muted-foreground ring-1 ring-inset ring-border';
            return onOpen ? (
              <button
                key={`${receipt.bin ?? ''}-${index}`}
                type="button"
                data-testid={testId}
                title={texts[index]}
                className={`${className} hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}
                onClick={onOpen}
              >
                {texts[index]}
              </button>
            ) : (
              <span
                key={`${receipt.bin ?? ''}-${index}`}
                data-testid={testId}
                title={texts[index]}
                className={className}
              >
                {texts[index]}
              </span>
            );
          })}
        </span>
      ) : null}
      {receipts.length && onShowAll ? (
        <button
          type="button"
          data-testid={`${testIdPrefix}-received-compact-${testIdSuffix}`}
          aria-label={texts.join(', ')}
          className={`hidden ${FALLBACK_SHOW} h-5 min-w-5 shrink-0 items-center justify-center rounded-full border border-transparent bg-secondary px-2 text-[0.6875rem] leading-[0.75rem] font-medium text-secondary-foreground dark:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}
          onClick={onShowAll}
        >
          Received
        </button>
      ) : null}
    </>
  );
}
