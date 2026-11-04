'use client';

import type { ReactNode } from 'react';
import { History } from 'lucide-react';

import { SoCustomerProject } from '@/components/common/SoCustomerProject';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import type { BookSoLinkEvent } from '../types/scm.types';

/** The value behind the S/O column, exactly as the backend serves it on both surfaces
 *  (`PurchaseOrderLine` and `OrderInquiryPoDetailLine`). */
export interface BookSoLinkage {
  /** The sales order the AutoCount book names on this line. One value, never a list: the
   *  book records a purchase line as raised for a single sales-order line. */
  book_so_number?: string | null;
  /** That sales order's customer (debtor name, else customer master) and project label. */
  book_so_customer_name?: string | null;
  book_so_project_label?: string | null;
  /** True when the book named a sales order this CRM does not hold. */
  book_so_unresolved?: boolean | null;
  /** PO-LINK-HISTORY: the latest S/O link event. Served on the PO detail only, so the order
   *  inquiry's PO lightbox (which does not carry it) shows the plain cell. */
  book_so_link?: BookSoLinkEvent | null;
}

/** What the cell prints when the book names a sales order this system does not hold.
 *  Neither the number nor a dash: the linkage exists, we just cannot name it here. */
export const BOOK_SO_UNRESOLVED_LABEL = 'Linked, not held';

/**
 * The AutoCount book's own sales-order linkage for one purchase-order line.
 *
 * ONE component, used by both the SCM purchase-order detail's Lines tab and the order
 * inquiry worklist's PO lightbox, so the same fact cannot come to read two ways on two
 * screens a click apart.
 *
 * THREE states, and they are deliberately distinguishable:
 *  - no linkage at all: a muted dash;
 *  - a linkage this system can name: the sales order number;
 *  - a linkage naming a sales order this system does not hold: a muted marker, because
 *    collapsing it into the dash would report "nothing linked" about a line the book has
 *    linked, and on the current data that is most of them.
 *
 * Never a link: a sales order lives on two different screens depending on whether it is a
 * project order or an adopted book order, and picking the wrong one is worse than plain
 * text. Never the raw ref either - that is a machine key.
 */
export function BookSoCell({ line }: { line: BookSoLinkage }) {
  const history = line.book_so_link ? (
    <BookSoLinkPopover event={line.book_so_link} linked={Boolean(line.book_so_number || line.book_so_unresolved)} />
  ) : null;
  if (line.book_so_number) {
    return (
      <>
        <WithHistory history={history}>
          <span className="block truncate" title={line.book_so_number}>
            {line.book_so_number}
          </span>
        </WithHistory>
        <SoCustomerProject
          customer={line.book_so_customer_name}
          project={line.book_so_project_label}
        />
      </>
    );
  }
  if (line.book_so_unresolved) {
    return (
      <WithHistory history={history}>
        <span
          className="block truncate text-muted-foreground"
          title={BOOK_SO_UNRESOLVED_LABEL}
        >
          {BOOK_SO_UNRESOLVED_LABEL}
        </span>
      </WithHistory>
    );
  }
  return (
    <WithHistory history={history}>
      <span className="text-muted-foreground">-</span>
    </WithHistory>
  );
}

function WithHistory({ history, children }: { history: ReactNode; children: ReactNode }) {
  if (!history) return <>{children}</>;
  return (
    <span className="flex min-w-0 items-center gap-1">
      <span className="min-w-0">{children}</span>
      {history}
    </span>
  );
}

function PopoverLine({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-end">{children}</span>
    </div>
  );
}

/**
 * PO-LINK-HISTORY: when the AutoCount sync last moved this line's S/O link, and what it was
 * before. AutoCount never says WHO changed it, so the sync is the only actor this can name.
 * A backfilled event is an upper bound ("on or before"), never the moment.
 */
function BookSoLinkPopover({ event, linked }: { event: BookSoLinkEvent; linked: boolean }) {
  const when = formatDateTimeInMalaysia(event.changed_at);
  const previous = !event.previous_linked
    ? 'Not linked'
    : event.previous_so_number || BOOK_SO_UNRESOLVED_LABEL;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="S/O link history"
          title="S/O link history"
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={(e) => e.stopPropagation()}
        >
          <History className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-[280px] max-w-[calc(100vw-2rem)] p-0">
          <div className="border-b px-3 py-2 text-xs font-semibold">S/O link</div>
          {event.estimated ? (
            <div className="space-y-1 px-3 py-2 text-xs">
              {/* A date only: the bound is an upper limit, not a moment to the minute. */}
              <p>{`Linked on or before ${formatDateInMalaysia(event.changed_at)}`}</p>
              <p className="text-muted-foreground">Earlier history not recorded</p>
            </div>
          ) : (
            <div className="space-y-1 px-3 py-2">
              <p className="text-xs font-medium">
                {linked ? 'Linked by AutoCount sync' : 'Unlinked by AutoCount sync'}
              </p>
              <PopoverLine label="When">
                <span className="tabular-nums">{when}</span>
              </PopoverLine>
              <PopoverLine label="Was">{previous}</PopoverLine>
            </div>
          )}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** The column's sort/filter value: the number when there is one, the marker when the book
 *  named an order we cannot resolve, and empty when it named none - so the three states
 *  sort into three groups rather than two. */
export function bookSoSortValue(line: BookSoLinkage): string {
  if (line.book_so_number) return line.book_so_number;
  return line.book_so_unresolved ? BOOK_SO_UNRESOLVED_LABEL : '';
}
