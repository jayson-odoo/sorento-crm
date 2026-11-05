'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { OrderInquiryLine } from '../../_shared/lib/orderInquiryLineFold';
import {
  documentChipsOf,
  ReserveText,
  reserveTextOfRows,
  type DocumentEntry,
} from './orderInquiryWorklistColumns';
import { DocumentStatePills, WorklistPill } from './orderInquiryDocumentPills';
import {
  OrderInquiryDocumentDialog,
  OrderInquiryDocumentLink,
  ViaSpoPoNumber,
} from './OrderInquiryDocumentDialog';

/*
 * The OI Lines tab's PO / SPO chips, shared (SO-LINE-OI-STATUS-UNIFY, owner 5 Nov 2026:
 * "it should reuse OI as much as possible like I also can click on the PO and go to linked
 * line"). The OI Lines tab's PO / SPO columns and the Sales Order Lines tab's Order inquiry
 * cell render these same chips, with the same click: the number opens the document at the
 * linked line, the receipt pill opens the same document, "+N" lists the rest.
 */

/** Every chip of `kind` across the line's live rows (LINKAGE-UNIFY U3, owner round 2):
 * one per document LINE, built by the worklist's OWN derivation (`documentChipsOf`) over
 * every row of the sales order line at once, so one SPO line two rows sit on (one via its
 * PO, one directly) is one chip whose receipts add up, and a withdrawn line is one more
 * chip behind "+N" - never lost to a de-dup by document number. */
export function lineDocumentsOf(line: OrderInquiryLine, kind: 'po' | 'spo'): DocumentEntry[] {
  return documentChipsOf(
    line.liveRows.flatMap((row) => (row.links ?? []).map((link) => ({ row, link }))),
    kind,
  );
}

/** The PO cell: the line's purchase documents and, beside them, a reserve ("Reserved @ BRW 3"). */
export function LineDocumentsCell({ line, kind }: { line: OrderInquiryLine; kind: 'po' | 'spo' }) {
  const reserve =
    kind === 'po' ? reserveTextOfRows(line.liveRows) : null;
  if (!reserve) return <LinePurchaseDocumentsCell line={line} kind={kind} />;
  if (lineDocumentsOf(line, kind).length === 0) return <ReserveText text={reserve} />;
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <LinePurchaseDocumentsCell line={line} kind={kind} />
      <ReserveText text={reserve} />
    </div>
  );
}

export function LinePurchaseDocumentsCell({ line, kind }: { line: OrderInquiryLine; kind: 'po' | 'spo' }) {
  // Round 5: the popover opens from "+N" or from the narrow-cell receipt chip, so it is
  // positioned against the whole cell rather than one trigger.
  const [open, setOpen] = React.useState(false);
  const chips = lineDocumentsOf(line, kind);
  if (chips.length === 0) return <span className="text-muted-foreground">-</span>;
  const [first, ...rest] = chips;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <span className="flex w-full min-w-0 items-center gap-1">
          <DocumentCell
            chip={first}
            kind={kind}
          />
          {rest.length > 0 ? (
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-5 shrink-0 rounded-full px-1.5 text-xs text-muted-foreground"
                aria-label={`${rest.length} more ${kind.toUpperCase()}`}
              >
                +{rest.length}
              </Button>
            </PopoverTrigger>
          ) : null}
        </span>
      </PopoverAnchor>
      {/* Portalled (owner, 29 Sep 2026): unportalled, the content painted inside the
          table and the next row's own "+N" chip showed through it. At the document
          root it sits above every row, and `collisionPadding` keeps it inside the
          viewport the way the shared `PillOverflow` popover does. */}
      <PopoverPortal>
        <PopoverContent align="start" collisionPadding={8} className="w-auto max-w-xs space-y-1 p-2">
          {chips.map((chip) => (
            <div key={chip.key}>
              <DocumentCell chip={chip} kind={kind} showLine />
            </div>
          ))}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

function DocumentCell({
  chip,
  kind,
  showLine = false,
}: {
  chip: DocumentEntry;
  kind: 'po' | 'spo';
  /** Name the line (`L7`) beside the number - the "+N" list, where lines of one
   * document sit side by side. */
  showLine?: boolean;
}) {
  // LINKAGE-UNIFY U3 round 2: the receipt pill opens the same document the number does,
  // as the worklist's own receipt pill opens its lightbox.
  const [documentOpen, setDocumentOpen] = React.useState(false);
  // The REAL link behind this chip, for the PO/SPO popover's own id and (#1215 point 2,
  // R15) the line it sits on.
  const link = chip.link;
  // R17 (owner rulings, 25 Sep 2026, "I also need here to be clickable"): a PO entry
  // read off an SPO link's own `source_po_number` (`chip.via === 'spo'`) has no real
  // po-kind link behind it - `chip.poId` is the resolved identity instead.
  const derived = kind === 'po' && chip.via === 'spo';
  const row = chip.row;
  return (
    <span className="flex min-w-0 items-center gap-1">
      {derived ? (
        <ViaSpoPoNumber poNumber={chip.document} purchaseOrderId={chip.poId} whole />
      ) : (
        <OrderInquiryDocumentLink
          kind={kind}
          document={chip.document}
          poId={link?.po_id}
          poLineId={link?.po_line_id}
          spoLineId={link?.spo_allocation_id}
          whole
        />
      )}
      {showLine && chip.lineLabel ? (
        <span className="shrink-0 text-2xs text-muted-foreground">{chip.lineLabel}</span>
      ) : null}
      {chip.via ? (
        <WorklistPill testId={`lines-${kind}-via-${row.id}`}>
          via {chip.via === 'po' ? 'PO' : 'SPO'}
        </WorklistPill>
      ) : null}
      {/* LINKAGE-UNIFY U3 (AC-D4): the worklist's own document pills, the same piece. */}
      <DocumentStatePills
        receipts={chip.receipts}
        deadReason={chip.deadReason}
        testIdPrefix="lines"
        testIdSuffix={`${kind}-${row.id}`}
        onOpen={(event) => {
          event.stopPropagation();
          setDocumentOpen(true);
        }}
      />
      {documentOpen ? (
        <OrderInquiryDocumentDialog
          kind={kind}
          document={chip.document}
          poId={link?.po_id}
          poLineId={link?.po_line_id}
          spoLineId={link?.spo_allocation_id}
          open
          onOpenChange={setDocumentOpen}
        />
      ) : null}
    </span>
  );
}


/**
 * Every PO and SPO chip of the line as a list, each the OI Lines tab's own chip (the
 * number opens the document at the linked line). The Sales Order's Order inquiry pill
 * opens this in a lightbox (owner hand test, 5 Nov 2026).
 */
export function LineDocumentsList({ line }: { line: OrderInquiryLine }) {
  const chips = [
    ...lineDocumentsOf(line, 'po').map((chip) => ({ chip, kind: 'po' as const })),
    ...lineDocumentsOf(line, 'spo').map((chip) => ({ chip, kind: 'spo' as const })),
  ];
  if (chips.length === 0) {
    return <p className="text-muted-foreground">No PO or SPO linked yet.</p>;
  }
  return (
    <ul className="space-y-1.5" data-testid="line-documents-list">
      {chips.map(({ chip, kind }) => (
        <li key={`${kind}-${chip.key}`} className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="w-9 shrink-0 text-2xs font-medium text-muted-foreground">
            {kind === 'po' ? 'PO' : 'SPO'}
          </span>
          <DocumentCell chip={chip} kind={kind} showLine />
        </li>
      ))}
    </ul>
  );
}
