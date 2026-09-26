/**
 * Who wrote the order - or the LINE (PLAN-so-lines-autocount-order.md 3.2). One vocabulary,
 * lifted out of `SalesOrdersGrid` (S2) so the list's Source column, the list's Source filter
 * and the detail page's own line Source column read the same words. A second copy of this
 * map is how two screens start disagreeing about what one row is called.
 *
 * `Order inquiry` is separate from `Sales order upload` because an order Joey's sheet
 * created is one CS has never seen, and it decides who may edit it.
 */
export const SOURCE_LABELS: Record<string, string> = {
  autocount: 'AutoCount',
  inquiry: 'Order inquiry',
  // Just "Upload" (the captain, 27 Aug). The column is called Source and every row of this
  // list is a sales order, so "Sales order upload" spent two of its three words repeating
  // the screen it is on - and the pill is a fixed-width cell that truncated the third.
  upload: 'Upload',
  // 11,006 of the orders in the book were absorbed from a six-year AutoCount export. Calling
  // one "Manual" claims somebody keyed a 2020 order by hand, and it is the same word the
  // detail page uses so the two screens cannot disagree about the same row.
  history: 'Absorbed history',
  manual: 'Manual',
};

/** The list's Source filter, in the order the popover shows them. */
export const SOURCE_FILTER_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'autocount', label: 'AutoCount' },
  { value: 'inquiry', label: 'Order inquiry' },
  { value: 'upload', label: 'Upload' },
  { value: 'history', label: 'Absorbed history' },
  { value: 'manual', label: 'Manual' },
];
