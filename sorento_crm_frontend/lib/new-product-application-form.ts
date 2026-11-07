/**
 * Form state for the new product application pages (NEW-PRODUCT-APP), shared by the staff
 * form and the portal form: the draft shape, the payload it writes, and the number checks run
 * before the round trip. The server makes the required-field refusals on Submit and names the
 * line; it stays the authority.
 */
import type {
  NewProductApplicationDetail,
  NewProductApplicationLine,
  NewProductApplicationPrefill,
  NewProductApplicationSuggestion,
  NewProductApplicationWrite,
} from '@/types/newProductApplication';
import { numberFieldError } from '@/lib/number-field';

/** One product block of the paper sheet (v4). */
export interface DraftLine {
  key: string;
  /** Set once the product is saved: it travels with the write so the server keeps it. */
  id?: string;
  /** The old free text; it leaves the form and is never part of the write body. */
  proposed_code: string;
  /** The CURRENT catalogue codes this line is based on, in picked order; none = a brand-new item. */
  current_products: { id: string; product_code: string }[];
  /** What the inquiry's code field said when it was not one catalogue code; shown read-only. */
  inquiry_code_hint: string;
  /** Earlier codes made from exactly these current codes, read with the line. */
  suggestions: NewProductApplicationSuggestion[];
  /** The current-code ids (comma list) `suggestions` answers; a different pick asks again. */
  suggestions_for: string;
  /** PRODUCT TYPE, the only required field. */
  description: string;
  dimension: string;
  material: string;
  thickness: string;
  packing: string;
  brand_id: string;
  brand_label: string;
  /** Typed text; an emptied box is sent as null, never 0. */
  expected_qty: string;
  /** Purchasing feedback, shown and edited on the sheet but never part of the write body. */
  cost_price: string;
}

export interface FormState {
  stock_inquiry_id: string;
  stock_inquiry_label: string;
  customer_id: string;
  /** The debtor's name when picked, otherwise the typed text. */
  customer_name: string;
  project_name: string;
  needed_by: string;
  remark: string;
  /** Purchasing feedback, one per application; not part of the write body. */
  lead_time: string;
  lines: DraftLine[];
}

export const EMPTY_FORM: FormState = {
  stock_inquiry_id: '',
  stock_inquiry_label: '',
  customer_id: '',
  customer_name: '',
  project_name: '',
  needed_by: '',
  remark: '',
  lead_time: '',
  lines: [],
};

let lineSeq = 0;
export const nextKey = () => `npa-line-${(lineSeq += 1)}`;

export const blankLine = (): DraftLine => ({
  key: nextKey(),
  proposed_code: '',
  current_products: [],
  inquiry_code_hint: '',
  suggestions: [],
  suggestions_for: '',
  description: '',
  dimension: '',
  material: '',
  thickness: '',
  packing: '',
  brand_id: '',
  brand_label: '',
  expected_qty: '',
  cost_price: '',
});

/** "SI26-0412 - XY-1234-MB": the inquiry as the header picker and the detail page name it. */
export const stockInquiryLabel = (
  number?: string | null,
  productCode?: string | null,
) => [number, productCode].filter(Boolean).join(' - ');

const text = (v: string | null | undefined) => v ?? '';
const clean = (v: string): string | null => (v.trim() ? v.trim() : null);
const figure = (v: string | number | null | undefined) =>
  v === null || v === undefined ? '' : String(v);

/** The ids of a pick as one comparable key. */
export const currentIdsKey = (ids: string[]) => ids.join(',');

function lineFromDetail(l: NewProductApplicationLine): DraftLine {
  const current = (l.current_products ?? []).map((p) => ({
    id: p.id,
    product_code: p.product_code,
  }));
  return {
    key: nextKey(),
    id: l.id,
    proposed_code: text(l.proposed_code),
    current_products: current,
    inquiry_code_hint: '',
    suggestions: l.suggestions ?? [],
    suggestions_for: currentIdsKey(current.map((p) => p.id)),
    description: text(l.description),
    dimension: text(l.dimension),
    material: text(l.material),
    thickness: text(l.thickness),
    packing: text(l.packing),
    brand_id: text(l.brand_id),
    brand_label: text(l.brand_name),
    expected_qty: figure(l.expected_qty),
    cost_price: figure(l.cost_price),
  };
}

export function stateFromDetail(d: NewProductApplicationDetail): FormState {
  return {
    stock_inquiry_id: text(d.stock_inquiry_id),
    stock_inquiry_label: d.stock_inquiry_id
      ? stockInquiryLabel(d.stock_inquiry_number, d.stock_inquiry_product_code)
      : '',
    customer_id: text(d.customer_id),
    customer_name: text(d.customer_name),
    project_name: text(d.project_name),
    needed_by: text(d.needed_by),
    remark: text(d.remark),
    lead_time: text(d.lead_time),
    lines: (d.lines ?? []).map((l) => {
      const line = lineFromDetail(l);
      // An old line typed its code as text: keep it visible when it came from an inquiry.
      return d.stock_inquiry_id && !line.current_products.length
        ? { ...line, inquiry_code_hint: line.proposed_code.trim() }
        : line;
    }),
  };
}

/**
 * The pre-fill copies the inquiry's text; the customer stays typed text with no debtor. Line 1
 * starts with the current code the server matched (exactly one catalogue code), otherwise empty
 * with the inquiry's code text shown read-only. Nothing is split or guessed here.
 */
export function stateFromPrefill(p: NewProductApplicationPrefill): FormState {
  const first = p.lines?.[0];
  return {
    ...EMPTY_FORM,
    stock_inquiry_id: text(p.stock_inquiry_id),
    stock_inquiry_label: stockInquiryLabel(
      p.stock_inquiry_number,
      first?.proposed_code,
    ),
    customer_name: text(p.customer_name),
    project_name: text(p.project_name),
    needed_by: text(p.needed_by),
    remark: text(p.remark),
    lines: [
      {
        ...blankLine(),
        proposed_code: text(first?.proposed_code),
        current_products: (first?.current_products ?? []).map((p) => ({
          id: p.id,
          product_code: p.product_code,
        })),
        inquiry_code_hint: first?.current_products?.length
          ? ''
          : text(first?.proposed_code).trim(),
        description: text(first?.description),
        expected_qty: figure(first?.expected_qty),
      },
    ],
  };
}

export function payloadFromState(s: FormState): NewProductApplicationWrite {
  return {
    stock_inquiry_id: s.stock_inquiry_id || null,
    customer_id: s.customer_id || null,
    customer_name: clean(s.customer_name),
    project_name: clean(s.project_name),
    needed_by: s.needed_by || null,
    remark: clean(s.remark),
    lines: s.lines.map((l) => ({
      ...(l.id ? { id: l.id } : {}),
      // proposed_code is never sent: the server keeps the stored text.
      current_product_ids: l.current_products.map((p) => p.id),
      description: clean(l.description),
      dimension: clean(l.dimension),
      material: clean(l.material),
      thickness: clean(l.thickness),
      packing: clean(l.packing),
      brand_id: l.brand_id || null,
      expected_qty: clean(l.expected_qty),
    })),
  };
}

/** The quantity may be emptied or above 0 (cost is purchasing feedback, checked where it is saved). */
const QTY = { min: 0, minExclusive: true, optional: true } as const;

/** Keys are `<field>_<line key>`; empty means every number is fine or blank. */
export function numberErrors(
  s: Pick<FormState, 'lines'>,
): Record<string, string> {
  const found: Record<string, string> = {};
  for (const l of s.lines) {
    const problem = numberFieldError(l.expected_qty, QTY);
    if (problem) found[`expected_qty_${l.key}`] = problem;
  }
  return found;
}
