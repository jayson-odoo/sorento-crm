'use client';

/** The value behind the S/O column, exactly as the backend serves it on both surfaces
 *  (`PurchaseOrderLine` and `OrderInquiryPoDetailLine`). */
export interface BookSoLinkage {
  /** The sales order the AutoCount book names on this line. One value, never a list: the
   *  book records a purchase line as raised for a single sales-order line. */
  book_so_number?: string | null;
  /** True when the book named a sales order this CRM does not hold. */
  book_so_unresolved?: boolean | null;
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
  if (line.book_so_number) {
    return (
      <span className="block truncate" title={line.book_so_number}>
        {line.book_so_number}
      </span>
    );
  }
  if (line.book_so_unresolved) {
    return (
      <span
        className="block truncate text-muted-foreground"
        title={BOOK_SO_UNRESOLVED_LABEL}
      >
        {BOOK_SO_UNRESOLVED_LABEL}
      </span>
    );
  }
  return <span className="text-muted-foreground">-</span>;
}

/** The column's sort/filter value: the number when there is one, the marker when the book
 *  named an order we cannot resolve, and empty when it named none - so the three states
 *  sort into three groups rather than two. */
export function bookSoSortValue(line: BookSoLinkage): string {
  if (line.book_so_number) return line.book_so_number;
  return line.book_so_unresolved ? BOOK_SO_UNRESOLVED_LABEL : '';
}
