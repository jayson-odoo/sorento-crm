/**
 * The three composed cells the Order summary sheet renders (S9, `reorder-feedback-9sep.md`,
 * AC-S9.2): month groups (Delivery), project/customer names (Project / customer), and the
 * remarks sentence (BRW PO qty, incoming SPO qty, last receipt, MOQ). One place, so the
 * composition is tested once here rather than three ways inside the grid.
 *
 * Every separator is a PLAIN hyphen with a space on either side - never an em or en dash
 * (repo-wide rule, CLAUDE.md) - because these are table cells copy-pasted into the sheet the
 * buyer already prints, and the sheet has never carried anything but a hyphen.
 */
import { fmtDate } from '../../lib/format';

const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

export interface DeliveryMonthGroup {
  /** `YYYY-MM`, or null for the undated bucket - a line with no required/delivery date. */
  month: string | null;
  qty: number;
}

/**
 * "Sep 30 - Oct 30 - undated 5" - oldest dated month first, newest last, the undated
 * bucket always trailing (it has no place in the ordering the other months carry).
 */
export function monthText(groups: DeliveryMonthGroup[]): string {
  const dated = groups.filter(
    (g): g is { month: string; qty: number } => g.month !== null,
  );
  const undated = groups.find((g) => g.month === null);
  const parts = [...dated]
    .sort((a, b) => a.month.localeCompare(b.month))
    .map((g) => {
      const monthIndex = Number(g.month.split('-')[1]) - 1;
      const abbr = MONTH_ABBR[monthIndex] ?? g.month;
      return `${abbr} ${g.qty}`;
    });
  if (undated) parts.push(`undated ${undated.qty}`);
  return parts.join(' - ');
}

export interface ProjectCustomerGroup {
  label: string;
  qty: number;
}

/** "OIB Construction (364), Sepang (480)" - who is behind the Project quantity, and how
 *  much of it is theirs. */
export function customersText(groups: ProjectCustomerGroup[]): string {
  return groups.map((g) => `${g.label} (${g.qty})`).join(', ');
}

export interface RemarksInput {
  /** Open BRW pool PO quantity for this product. 0 = nothing to say. */
  po_open_qty: number;
  /** Open incoming SPO quantity for this product. 0 = nothing to say. */
  incoming_spo_qty: number;
  /** The latest goods-received picking line, or null when this product has never been
   *  received. */
  last_receipt: { date: string; qty: number } | null;
  /** The chosen supplier's MOQ, or null when there is none on file. */
  moq: number | null;
}

/**
 * "PO 400 + incoming 89 = 489 - Last in 21/07/2026, 300 - MOQ 1000" - every figure the
 * sheet's own Remarks column states, composed from the run's frozen row rather than typed
 * twice. A section with nothing to say is OMITTED, never printed as a zero nobody meant.
 */
export function remarksText(input: RemarksInput): string {
  const parts: string[] = [];
  if (input.po_open_qty > 0 || input.incoming_spo_qty > 0) {
    const total = input.po_open_qty + input.incoming_spo_qty;
    parts.push(`PO ${input.po_open_qty} + incoming ${input.incoming_spo_qty} = ${total}`);
  }
  if (input.last_receipt) {
    parts.push(`Last in ${fmtDate(input.last_receipt.date)}, ${input.last_receipt.qty}`);
  }
  if (input.moq !== null && input.moq !== undefined) {
    parts.push(`MOQ ${input.moq}`);
  }
  return parts.join(' - ');
}
