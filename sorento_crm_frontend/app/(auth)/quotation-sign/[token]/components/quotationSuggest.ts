import {
  compareMoney,
  formatQty,
  multiplyMoney,
  subtractMoney,
  sumMoney,
} from '@/app/(protected)/project-sales/_shared/lib/money';
import type {
  QuotationSignAmendmentBody,
  QuotationSignLine,
  QuotationSignScope,
} from '../../services/quotationSignService';

/**
 * The customer's suggest mode (QUOTE-CUSTOMER-AMEND), as plain functions over the typed values so
 * the table, the summary row and Send all read one answer.
 *
 * The same bounds the backend enforces: quantity 1 to 9,999,999.99 and price above 0, both with
 * at most two decimals. The server still checks; this keeps a bad value from being sent at all.
 */

export type LineEdit = {
  quantity: string;
  unit_price: string;
  remove: boolean;
};
export type LineEdits = Record<string, LineEdit>;

const AMOUNT = /^\d+(\.\d{1,2})?$/;
const MAX_QTY = '9999999.99';
const MAX_PRICE = '9999999999.99';

export const QTY_ERROR = 'Quantity must be at least 1.';
export const PRICE_ERROR = 'Unit rate must be above 0.';

/** A zero-priced line that is not rate-only: its money sits on the line above it. */
export function priceIsEditable(line: QuotationSignLine): boolean {
  return line.is_rate_only || compareMoney(line.unit_price, '0') === 1;
}

/** What the inputs open at: the issued values, as the page prints them. */
export function startingEdit(line: QuotationSignLine): LineEdit {
  return {
    quantity: formatQty(line.quantity),
    unit_price: line.unit_price,
    remove: false,
  };
}

export function editOf(edits: LineEdits, line: QuotationSignLine): LineEdit {
  return edits[line.id] ?? startingEdit(line);
}

export function quantityError(value: string): string | null {
  const text = value.trim();
  if (!AMOUNT.test(text)) return QTY_ERROR;
  if (compareMoney(text, '1') === -1) return QTY_ERROR;
  if (compareMoney(text, MAX_QTY) === 1) return 'Quantity is too large.';
  return null;
}

export function priceError(value: string): string | null {
  const text = value.trim();
  if (!AMOUNT.test(text) || compareMoney(text, '0') !== 1) return PRICE_ERROR;
  if (compareMoney(text, MAX_PRICE) === 1) return 'Unit rate is too large.';
  return null;
}

function differs(value: string, issued: string): boolean {
  return compareMoney(value.trim(), issued) !== 0;
}

/** The changed fields of one line, or null when it is as issued. */
export function changeOf(
  line: QuotationSignLine,
  edit: LineEdit,
): {
  quantity: string | null;
  unit_price: string | null;
  remove: boolean;
} | null {
  if (edit.remove) return { quantity: null, unit_price: null, remove: true };
  const quantity = differs(edit.quantity, line.quantity)
    ? edit.quantity.trim()
    : null;
  const price =
    priceIsEditable(line) && differs(edit.unit_price, line.unit_price)
      ? edit.unit_price.trim()
      : null;
  if (quantity === null && price === null) return null;
  return { quantity, unit_price: price, remove: false };
}

/** True when any line that is not staged for removal holds a value that cannot be sent. */
export function hasErrors(
  scopes: QuotationSignScope[],
  edits: LineEdits,
): boolean {
  return scopes.some((scope) =>
    scope.lines.some((line) => {
      const edit = edits[line.id];
      if (!edit || edit.remove) return false;
      return (
        quantityError(edit.quantity) !== null ||
        (priceIsEditable(line) && priceError(edit.unit_price) !== null)
      );
    }),
  );
}

/** A line's amount with the edit applied. A removed or rate-only line adds nothing. */
export function editedAmount(line: QuotationSignLine, edit: LineEdit): string {
  if (edit.remove || line.is_rate_only) return '0.00';
  return (
    multiplyMoney(
      edit.quantity.trim(),
      priceIsEditable(line) ? edit.unit_price.trim() : line.unit_price,
    ) ??
    line.amount ??
    '0.00'
  );
}

/** The request body: only changed lines, and a blank note as null. */
export function suggestionBody(
  scopes: QuotationSignScope[],
  edits: LineEdits,
  note: string,
  requesterName: string,
): QuotationSignAmendmentBody {
  const lines: QuotationSignAmendmentBody['lines'] = [];
  for (const scope of scopes) {
    for (const line of scope.lines) {
      const change = changeOf(line, editOf(edits, line));
      if (change) lines.push({ line_id: line.id, ...change });
    }
  }
  return {
    requester_name: requesterName.trim() || null,
    note: note.trim() || null,
    lines,
  };
}

/** How many lines differ from what was issued (a removal counts). */
export function changedLineCount(
  scopes: QuotationSignScope[],
  edits: LineEdits,
): number {
  let count = 0;
  for (const scope of scopes) {
    for (const line of scope.lines) {
      if (changeOf(line, editOf(edits, line))) count += 1;
    }
  }
  return count;
}

/**
 * What `base` (a section subtotal, or the grand total, as issued) comes to with the edits on
 * `lines` applied: each changed line's issued amount out, its edited amount in. A removed or
 * rate-only line adds nothing, by the same rule as every total.
 */
export function totalAfter(
  lines: QuotationSignLine[],
  edits: LineEdits,
  base: string,
): string {
  const removed: string[] = [];
  const added: string[] = [];
  for (const line of lines) {
    const edit = editOf(edits, line);
    if (!changeOf(line, edit)) continue;
    removed.push(line.is_rate_only ? '0.00' : (line.amount ?? '0.00'));
    added.push(editedAmount(line, edit));
  }
  return subtractMoney(sumMoney([base, ...added]), sumMoney(removed)) ?? base;
}
