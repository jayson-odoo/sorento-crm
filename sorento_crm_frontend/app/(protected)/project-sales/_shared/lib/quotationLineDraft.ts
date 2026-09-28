import {
  isInlineChecked,
  INLINE_CHECKED,
  type InlineDraft,
} from '../components/InlineLineTable';
import type {
  QuotationLine,
  QuotationLineBulkItem,
  UnitType,
} from '../types/project.types';
import { isDecimalString, multiplyMoney, sumMoney } from './money';

/**
 * One quotation line as the form page holds it before Save (#1341).
 *
 * `id` is the stored line's id, or null for one added on the form: the whole-set write reads a
 * line with no id as new, and a stored line whose id never reaches the request is deleted. `key`
 * is the row's identity on screen for as long as the page is open. `line` is the stored row, for
 * the facts only the server decides (the photo, the saved flags); null on a line added here.
 */
export type QuotationFormLine = {
  key: string;
  id: string | null;
  line: QuotationLine | null;
  draft: InlineDraft;
};

/** A stored line as an editable draft. Every field the write sends has to be in here. */
export function serverToDraft(line: QuotationLine): InlineDraft {
  return {
    product_id: line.product_id ?? '',
    description: line.description ?? '',
    technical_spec: line.technical_spec ?? '',
    // The response names this one `brand`, the request `brand_snapshot`. The draft holds the
    // request's name so the payload stays a copy rather than a translation.
    brand_snapshot: line.brand ?? '',
    quantity: line.quantity ?? '1',
    uom: line.uom ?? '',
    unit_price: line.unit_price ?? '',
    complete_set: line.complete_set ?? '',
    unit_type: line.unit_type ?? '',
    is_rate_only: line.is_rate_only ? INLINE_CHECKED : '',
    band_label: line.band_label ?? '',
    notes: line.notes ?? '',
    // Read under the unit price, never sent back (the server snapshots it from the product).
    list_price: line.list_price ?? '',
  };
}

/** A brand-new line's starting draft. */
export function emptyDraft(): InlineDraft {
  return {
    product_id: '',
    description: '',
    technical_spec: '',
    brand_snapshot: '',
    quantity: '1',
    uom: '',
    unit_price: '',
    complete_set: '',
    unit_type: '',
    is_rate_only: '',
    band_label: '',
    notes: '',
    list_price: '',
  };
}

export function lineToFormLine(line: QuotationLine): QuotationFormLine {
  return { key: line.id, id: line.id, line, draft: serverToDraft(line) };
}

let newLineCounter = 0;

/** A line added on the form: no id, so the write stores it as new. */
export function newFormLine(
  patch: Partial<InlineDraft> = {},
): QuotationFormLine {
  newLineCounter += 1;
  return {
    key: `new:${Date.now().toString(36)}:${newLineCounter}`,
    id: null,
    line: null,
    draft: { ...emptyDraft(), ...patch } as InlineDraft,
  };
}

/**
 * The one rule a line has to satisfy before it can be stored: an off-catalog line carries the
 * description the customer reads. Written once, used to mark the field and to stop a Save that
 * would only come back as a 422.
 */
export function lineErrors(draft: InlineDraft): Record<string, string> {
  return !draft.product_id && !(draft.description ?? '').trim()
    ? { description: 'Needed on an off-catalog line' }
    : {};
}

export function unfinishedLines(lines: QuotationFormLine[]): number {
  return lines.filter((line) => Object.keys(lineErrors(line.draft)).length > 0)
    .length;
}

/** Lines whose quantity or unit price is typed but is not a number: the server would 422. */
export function invalidNumberLines(lines: QuotationFormLine[]): number {
  return lines.filter((line) =>
    [line.draft.quantity, line.draft.unit_price].some(
      (value) =>
        (value ?? '').trim() !== '' && !isDecimalString((value ?? '').trim()),
    ),
  ).length;
}

/** Draft to the body the line write takes. `brand_snapshot` is the request's name for `brand`. */
export function draftToBody(
  draft: InlineDraft,
): Omit<QuotationLineBulkItem, 'id'> {
  return {
    product_id: draft.product_id || null,
    description_snapshot: (draft.description ?? '').trim() || null,
    unit_price: (draft.unit_price ?? '').trim() || '0',
    quantity: (draft.quantity ?? '').trim() || '1',
    uom: (draft.uom ?? '').trim() || null,
    unit_type: (draft.unit_type || null) as UnitType | null,
    notes: (draft.notes ?? '').trim() || null,
    brand_snapshot: (draft.brand_snapshot ?? '').trim() || null,
    technical_spec: (draft.technical_spec ?? '').trim() || null,
    complete_set: (draft.complete_set ?? '').trim() || null,
    band_label: (draft.band_label ?? '').trim() || null,
    is_rate_only: isInlineChecked(draft.is_rate_only),
  };
}

/** The whole line set as the whole-set write takes it: array order is the line order. */
export function formLinesToBody(
  lines: QuotationFormLine[],
): QuotationLineBulkItem[] {
  return lines.map((line) =>
    line.id
      ? { id: line.id, ...draftToBody(line.draft) }
      : draftToBody(line.draft),
  );
}

/**
 * What the lines come to, by the backend's rule: rate-only lines add nothing, and a cell that is
 * not a number yet counts as zero rather than blanking the whole total. Off the STRINGS, to the
 * cent, so the footer and the document total cannot drift apart.
 */
export function totalFromDrafts(drafts: InlineDraft[]): string | null {
  return sumMoney(
    drafts
      .filter((draft) => !isInlineChecked(draft.is_rate_only))
      .map((draft) => multiplyMoney(draft.quantity, draft.unit_price) ?? '0'),
  );
}

export function formLinesTotal(lines: QuotationFormLine[]): string | null {
  return totalFromDrafts(lines.map((line) => line.draft));
}
