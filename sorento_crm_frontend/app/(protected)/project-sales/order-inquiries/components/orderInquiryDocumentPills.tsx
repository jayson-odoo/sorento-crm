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
 * number"). The cell root carries `@container`. Round 6: at 300px the number, "via PO" and
 * a readable receipt no longer fit side by side, so the chip takes over from there down to
 * the SPO column's own floor (`minSize`), which still fits the number, "via PO" and the
 * chip.
 */
const RECEIPTS_HIDE = '@max-[300px]:hidden';
const FALLBACK_SHOW = '@max-[300px]:inline-flex';

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
        // The "+N" pill's own Badge; `hidden` overrides its display until the container
        // query shows it.
        <Badge
          asChild
          size="sm"
          variant="secondary"
          appearance="light"
          className={`hidden shrink-0 ${FALLBACK_SHOW}`}
        >
          <button
            type="button"
            data-testid={`${testIdPrefix}-received-compact-${testIdSuffix}`}
            aria-label={texts.join(', ')}
            onClick={onShowAll}
          >
            Received
          </button>
        </Badge>
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
  renderDocument,
}: {
  spos: DocumentSpoLine[] | undefined;
  renderDocument: (spoNumber: string) => React.ReactNode;
}) {
  if (!spos?.length) return <span className="text-muted-foreground">-</span>;
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
