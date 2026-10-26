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
  title,
  truncate = false,
  children,
}: {
  as?: 'span' | 'button';
  warning?: boolean;
  /** LINKAGE-UNIFY U3 (Q5): the red "PO cancelled" / "SPO withdrawn" marks. */
  destructive?: boolean;
  testId: string;
  onClick?: (event: React.MouseEvent) => void;
  ariaLabel?: string;
  title?: string;
  /** The pill's text ellipsizes when its cell narrows (`title` should carry the full text). */
  truncate?: boolean;
  children: React.ReactNode;
}) {
  const className = truncate
    ? 'min-w-0 max-w-full shrink-0 whitespace-nowrap'
    : 'shrink-0 whitespace-nowrap';
  const body = truncate ? <span className="truncate">{children}</span> : children;
  const variant = destructive ? 'destructive' : warning ? 'warning' : 'secondary';
  return (
    <Badge asChild size="sm" variant={variant} appearance="light">
      {as === 'button' ? (
        <button
          type="button"
          data-testid={testId}
          aria-label={ariaLabel}
          title={title}
          className={className}
          onClick={onClick}
        >
          {body}
        </button>
      ) : (
        <span data-testid={testId} title={title} className={className}>
          {body}
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
 * LINKAGE-UNIFY U3 (AC-D1, AC-D3, AC-D4): the state pills beside ONE document line chip,
 * the same piece on the worklist (`DocumentsCell`), the Lines tab (`DocumentCell`) and
 * the backing-documents dialog, so the screens agree by construction. Red "PO cancelled"
 * / "SPO withdrawn" for a dead document (Q5); one "Received <qty> at <bin>" pill per bin
 * the goods landed at (Q1, Q6). A PO chip only ever carries the PO line's own receipts
 * (Q4); goods that went on through an SPO are on the SPO's chip.
 *
 * Round 8 (owner): the receipt tag is the same `WorklistPill` as "via PO" at every width; in a
 * narrow cell its text ellipsizes ("Rec...", full wording in `title`). The number itself
 * never truncates.
 */
export function DocumentStatePills({
  receipts,
  deadReason,
  testIdPrefix,
  testIdSuffix,
  onOpen,
}: {
  receipts: OrderInquiryLinkReceipt[];
  deadReason: OrderInquiryDeadReason | null;
  /** Test ids read `<prefix>-received-<suffix>` (then `-1`, `-2` for further bins) and
   * `<prefix>-dead-<suffix>`. */
  testIdPrefix: string;
  testIdSuffix: string;
  /** Makes each receipt pill a button that opens the document, as the chip does. */
  onOpen?: (event: React.MouseEvent) => void;
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
        <span className="flex min-w-0 items-center gap-1 overflow-hidden">
          {receipts.map((receipt, index) => (
            <WorklistPill
              key={`${receipt.bin ?? ''}-${index}`}
              as={onOpen ? 'button' : 'span'}
              truncate
              title={texts[index]}
              testId={`${testIdPrefix}-received-${testIdSuffix}${index ? `-${index}` : ''}`}
              onClick={onOpen}
            >
              {texts[index]}
            </WorklistPill>
          ))}
        </span>
      ) : null}
    </>
  );
}

/** LINKAGE-UNIFY U4: one SPO line a PO line was transferred onto, as both PO screens
 * receive it (`goods_chain.spo_lines_of`). */
export interface DocumentSpoLine {
  spo_number: string | null;
  line_label: string | null;
  receipts?: OrderInquiryLinkReceipt[];
  dead_reason?: OrderInquiryDeadReason | null;
}

/**
 * LINKAGE-UNIFY U4: a PO line's SPO cell - every SPO line it was transferred onto, each its
 * number (`renderDocument`: the screen's own document link, never truncated), its line and
 * the U3 document pills ("Received <qty> at <bin>", red "SPO withdrawn"). The same piece on
 * the order inquiry's PO popup and the SCM purchase order's Lines tab. No "In transit" tag
 * (owner ruling): a line still at sea simply carries no pill.
 */
export function PoLineSpoCell({
  spos,
  lineDeadReason,
  renderDocument,
}: {
  spos: DocumentSpoLine[] | undefined;
  /** Owner Q5 (a): the PO line itself brings nothing (`po_cancelled`), so with no SPO line
   * to carry the mark the cell draws the same red pill. */
  lineDeadReason?: OrderInquiryDeadReason | null;
  renderDocument: (spoNumber: string) => React.ReactNode;
}) {
  if (!spos?.length) {
    return lineDeadReason ? (
      <DocumentStatePills
        receipts={[]}
        deadReason={lineDeadReason}
        testIdPrefix="po-line"
        testIdSuffix="cancelled"
      />
    ) : (
      <span className="text-muted-foreground">-</span>
    );
  }
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      {spos.map((spo, index) => (
        <span
          key={`${spo.spo_number ?? ''}-${spo.line_label ?? ''}-${index}`}
          className="flex min-w-0 items-center gap-1"
        >
          {spo.spo_number ? renderDocument(spo.spo_number) : null}
          {spo.line_label ? (
            <span className="shrink-0 text-2xs text-muted-foreground">{spo.line_label}</span>
          ) : null}
          <DocumentStatePills
            receipts={spo.receipts ?? []}
            deadReason={spo.dead_reason ?? null}
            testIdPrefix="po-line-spo"
            testIdSuffix={String(index)}
          />
        </span>
      ))}
    </span>
  );
}
