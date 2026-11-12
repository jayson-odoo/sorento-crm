'use client';

import * as React from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  lineShowsRejectedBadge,
  OrderInquiryLineStatusPill,
} from '@/app/(protected)/project-sales/_shared/components/OrderInquiryLineStatusPill';
import {
  foldInquiryLines,
  type OrderInquiryLine,
} from '@/app/(protected)/project-sales/_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '@/app/(protected)/project-sales/_shared/types/orderInquiry.types';
import { LineDocumentsList } from '@/app/(protected)/project-sales/order-inquiries/components/OrderInquiryLineDocuments';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ReserveText,
  reserveTextOfRows,
} from '@/app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns';

/** One order inquiry's own fold of this sales order line. */
interface InquiryEntry {
  inquiryId: string | null;
  inquiryNo: string;
  line: OrderInquiryLine;
}

/**
 * Every OI on the line, one entry each, newest raised first. Each OI's rows are folded by
 * the OI Lines tab's own `foldInquiryLines`, so used and cancelled rows are hidden by the
 * one visibility rule, and an OI left with no live row drops out entirely (it is History
 * on the OI page too).
 */
export function soLineInquiryEntries(
  rows: OrderInquiryWorklistRow[] | null | undefined,
): InquiryEntry[] {
  if (!rows || rows.length === 0) return [];
  const byInquiry = new Map<string, OrderInquiryWorklistRow[]>();
  for (const row of rows) {
    const key = row.order_inquiry_id ?? row.inquiry_no ?? row.id;
    const group = byInquiry.get(key);
    if (group) group.push(row);
    else byInquiry.set(key, [row]);
  }
  const entries: InquiryEntry[] = [];
  for (const group of [...byInquiry.values()].reverse()) {
    for (const line of foldInquiryLines(group)) {
      entries.push({
        inquiryId: group[0].order_inquiry_id ?? null,
        inquiryNo: group[0].inquiry_no ?? '-',
        line,
      });
    }
  }
  return entries;
}

function InquiryEntryView({ entry, testId }: { entry: InquiryEntry; testId: string }) {
  const { line } = entry;
  const [open, setOpen] = React.useState(false);
  const href = entry.inquiryId
    ? `/project-sales/order-inquiries/${entry.inquiryId}?row=${line.primary.id}`
    : null;
  // The pill's own rule: only when the pill IS the Rejected button does it keep that lightbox.
  const rejected = lineShowsRejectedBadge(line);
  const reserve = reserveTextOfRows(line.liveRows);
  return (
    <span className="flex min-w-0 items-center gap-1.5 overflow-hidden" data-testid={testId}>
      {href ? (
        <Link
          href={href}
          className="shrink-0 tabular-nums font-medium text-primary hover:underline"
          title={entry.inquiryNo}
        >
          {entry.inquiryNo}
        </Link>
      ) : (
        <span className="shrink-0 tabular-nums" title={entry.inquiryNo}>
          {entry.inquiryNo}
        </span>
      )}
      {rejected ? (
        // A refusal's pill already opens its own lightbox (who, when, why).
        <OrderInquiryLineStatusPill line={line} rejectedTestId={`${testId}-rejected`} />
      ) : (
        // Owner hand test (5 Nov 2026): the PO / SPO rows are not in the column; the pill
        // opens them in a lightbox.
        <button
          type="button"
          className="inline-flex min-w-0 shrink-0 rounded-full outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`PO and SPO for ${entry.inquiryNo}`}
          data-testid={`${testId}-pill`}
          onClick={(event) => {
            event.stopPropagation();
            setOpen(true);
          }}
        >
          <OrderInquiryLineStatusPill line={line} />
        </button>
      )}
      {open ? (
        <Dialog open onOpenChange={setOpen}>
          <DialogContent
            className="max-w-lg"
            data-testid={`${testId}-documents`}
            onClick={(event) => event.stopPropagation()}
          >
            <DialogHeader>
              <DialogTitle className="tabular-nums">{entry.inquiryNo}</DialogTitle>
              <DialogDescription>PO and SPO for this line</DialogDescription>
            </DialogHeader>
            <DialogBody className="space-y-3 text-sm">
              <OrderInquiryLineStatusPill line={line} />
              <LineDocumentsList line={line} />
              {reserve ? <ReserveText text={reserve} /> : null}
            </DialogBody>
          </DialogContent>
        </Dialog>
      ) : null}
    </span>
  );
}

/**
 * SO-LINE-OI-STATUS-UNIFY (owner, 5 Nov 2026): the Sales Order Lines tab's Order inquiry
 * cell says what the OI Lines tab says about the same line, from the same fold and the
 * same pill (`OrderInquiryLineStatusPill`). The cell is the OI number and the pill only
 * (owner hand test, 5 Nov): the pill opens a lightbox with the OI page's own PO / SPO
 * chips (click goes to the linked line) and the reserve text; a refusal's pill opens its
 * Rejected lightbox. One row always: a second OI on the line sits behind "+N".
 */
export function SoLineOrderInquiryCell({
  rows,
  lineId,
}: {
  rows: OrderInquiryWorklistRow[] | null | undefined;
  lineId: string;
}) {
  const entries = React.useMemo(() => soLineInquiryEntries(rows), [rows]);
  if (entries.length === 0) return <span className="text-muted-foreground">-</span>;
  const [first, ...rest] = entries;
  return (
    <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
      <InquiryEntryView entry={first} testId={`so-line-oi-${lineId}`} />
      {rest.length > 0 ? (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-5 shrink-0 rounded-full px-1.5 text-xs text-muted-foreground"
              aria-label={`${rest.length} more order inquiry`}
              onClick={(event) => event.stopPropagation()}
            >
              +{rest.length}
            </Button>
          </PopoverTrigger>
          <PopoverPortal>
            <PopoverContent
              align="start"
              collisionPadding={8}
              className="w-auto max-w-[92vw] space-y-1.5 p-2"
            >
              {entries.map((entry, index) => (
                <InquiryEntryView
                  key={`${entry.inquiryId ?? entry.inquiryNo}-${entry.line.primary.id}`}
                  entry={entry}
                  testId={`so-line-oi-${lineId}-more-${index}`}
                />
              ))}
            </PopoverContent>
          </PopoverPortal>
        </Popover>
      ) : null}
    </div>
  );
}
