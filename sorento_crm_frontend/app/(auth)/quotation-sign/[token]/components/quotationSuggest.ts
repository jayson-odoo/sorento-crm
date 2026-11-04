import { compareMoney } from '@/app/(protected)/project-sales/_shared/lib/money';
import type {
  QuotationFeedbackBody,
  QuotationFeedbackItem,
  QuotationSignLine,
} from '../../services/quotationSignService';

/**
 * The customer's feedback (PS-QUOTE-MATRIX R19), as plain functions so the form, its Send button
 * and the tests read one answer.
 *
 * A note sits on a whole item or on one cell of a grid scope, and may carry ONE optional hint:
 * a quantity (item or cell), a price, "remove this item", or another model at an optional price
 * (item only). Nothing is accepted or applied: the hint is shown to the salesperson next to
 * today's value. The bounds are the backend's: quantity 0 to 9,999,999.99, price above 0, two
 * decimals at most, a model 1 to 200 characters, a note up to 1,000.
 */

export type FeedbackHint = 'none' | 'quantity' | 'unit_price' | 'remove' | 'model_swap';

/** What the form is about: an item, or one of its cells. */
export type FeedbackTarget = {
  line: QuotationSignLine;
  /** The item as the customer reads it. */
  itemLabel: string;
  scopeLabel: string;
  /** A cell of a grid scope; absent for the whole item. */
  cell?: { key: string; label: string; value: string };
};

export type FeedbackDraft = {
  note: string;
  hint: FeedbackHint;
  /** The quantity or price hint, or a model swap's optional price. */
  value: string;
  model: string;
};

export const EMPTY_FEEDBACK: FeedbackDraft = { note: '', hint: 'none', value: '', model: '' };

const AMOUNT = /^\d+(\.\d{1,2})?$/;
const MAX_QTY = '9999999.99';
const MAX_PRICE = '9999999999.99';
export const MAX_NOTE = 1000;
export const MAX_MODEL = 200;

/** The hints a target offers: a cell takes a quantity only, an item every kind. */
export function hintsFor(target: FeedbackTarget): FeedbackHint[] {
  return target.cell
    ? ['none', 'quantity']
    : ['none', 'quantity', 'unit_price', 'remove', 'model_swap'];
}

export const HINT_LABELS: Record<FeedbackHint, string> = {
  none: 'Just a note',
  quantity: 'Quantity',
  unit_price: 'Price',
  remove: 'Remove this item',
  model_swap: 'Another model',
};

function quantityError(value: string): string | null {
  const text = value.trim();
  if (!AMOUNT.test(text)) return 'Quantity must be a number, 0 or more, with at most 2 decimals.';
  if (compareMoney(text, MAX_QTY) === 1) return 'Quantity is too large.';
  return null;
}

function priceError(value: string, label = 'Price'): string | null {
  const text = value.trim();
  if (!AMOUNT.test(text) || compareMoney(text, '0') !== 1) return `${label} must be above 0.`;
  if (compareMoney(text, MAX_PRICE) === 1) return `${label} is too large.`;
  return null;
}

/** Why the form cannot be sent yet, or null when it can. */
export function feedbackError(target: FeedbackTarget, draft: FeedbackDraft): string | null {
  const note = draft.note.trim();
  if (note.length > MAX_NOTE) return `Keep the note under ${MAX_NOTE} characters.`;
  if (!hintsFor(target).includes(draft.hint)) return 'Pick a suggestion this item takes.';
  switch (draft.hint) {
    case 'none':
      return note ? null : 'Write a note.';
    case 'quantity':
      return quantityError(draft.value);
    case 'unit_price':
      return priceError(draft.value);
    case 'remove':
      return null;
    case 'model_swap': {
      const model = draft.model.trim();
      if (!model) return 'Name the other model.';
      if (model.length > MAX_MODEL) return `Keep the model under ${MAX_MODEL} characters.`;
      return draft.value.trim() ? priceError(draft.value) : null;
    }
  }
}

/** The one item the form sends. Call only when `feedbackError` is null. */
export function feedbackItem(target: FeedbackTarget, draft: FeedbackDraft): QuotationFeedbackItem {
  const note = draft.note.trim();
  const item: QuotationFeedbackItem = {
    line_id: target.line.id,
    kind: draft.hint === 'none' ? 'note' : draft.hint,
  };
  if (target.cell) item.cell_key = target.cell.key;
  if (note) item.note = note;
  if (draft.hint === 'quantity' || draft.hint === 'unit_price') item.value = draft.value.trim();
  if (draft.hint === 'model_swap') {
    item.model = draft.model.trim();
    if (draft.value.trim()) item.value = draft.value.trim();
  }
  return item;
}

/** The submit body: the items, a blank note or name as null. */
export function feedbackBody(
  items: QuotationFeedbackItem[],
  note: string,
  requesterName: string,
): QuotationFeedbackBody {
  return {
    items,
    note: note.trim() || null,
    requester_name: requesterName.trim() || null,
  };
}
