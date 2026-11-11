/**
 * Form state for the sample request pages (SR-CORE), shared by the portal form and the staff
 * new/edit page: the draft shape, the payload it writes, and the submit refusals checked before
 * the round trip. The server makes the same refusals and stays the authority.
 */
import {
  type SampleRequestDeliveryMode,
  type SampleRequestDetail,
  type SampleRequestGoodsFrom,
  type SampleRequestLoanUnit,
  type SampleRequestProductSource,
  type SampleRequestQuotationPrefill,
  type SampleRequestWrite,
} from '@/types/sampleRequest';
import { codeWithName } from '@/lib/product-display';
import { formatPhone } from '@/app/(protected)/project-sales/_shared/lib/phoneDisplay';
import { numberFieldError } from '@/lib/number-field';

/** The one rule for a line quantity and the loan period. */
export const WHOLE_AT_LEAST_ONE = { min: 1, integer: true } as const;

export interface DraftLine {
  key: string;
  product_id: string;
  label: string;
  qty: string;
  remark: string;
  /** The product went inactive after it was put on the request (kept, shown as Inactive). */
  inactive?: boolean;
}

export interface FormState {
  customer_id: string;
  customer_label: string;
  /** Typed when the customer has no debtor code; used only while no debtor is picked. */
  customer_name: string;
  project_id: string;
  project_label: string;
  project_title: string;
  /** The quotation the rows were pre-filled from (SAMPLE-FROM-QUOTE); '' when none. */
  quotation_document_id: string;
  quotation_issue_id: string;
  /** The rows exactly as the pre-fill wrote them, to tell untouched pre-fill from a person's edits. */
  prefill_signature: string;
  scope_note: string;
  lines: DraftLine[];
  board_mounting: boolean;
  board_label: string;
  delivery_date: string;
  delivery_mode: SampleRequestDeliveryMode | '';
  /** SAMPLE-REQUEST-V2 (staff form): the ship-to party, the role it is added in when it is not on
   * the project yet, and the people picked at it. '' / [] when none. */
  ship_to_party_id: string;
  ship_to_role: string;
  /** The picked party is not on the project yet, so its role must be picked. */
  ship_to_needs_role: boolean;
  /** The party was picked from a names-only list (no parties view grant): its address is not
   * known here, so the server fills it (the party's, else the site address) on save. */
  ship_to_address_pending: boolean;
  ship_to_contact_ids: string[];
  /** An old request's typed Ship To with no party behind it (card example E), shown as a hint. */
  ship_to_typed_before: string;
  ship_to_name: string;
  ship_to_address: string;
  site_contact_name: string;
  site_contact_phone: string;
  site_contact_note: string;
  loan_value: string;
  loan_unit: SampleRequestLoanUnit;
  /** Goods Taken From ticks: neither or both = either, one = that value. */
  goods_demo: boolean;
  goods_new: boolean;
  purpose: string;
}

export const EMPTY_FORM: FormState = {
  customer_id: '',
  customer_label: '',
  customer_name: '',
  project_id: '',
  project_label: '',
  project_title: '',
  quotation_document_id: '',
  quotation_issue_id: '',
  prefill_signature: '',
  scope_note: '',
  lines: [],
  board_mounting: false,
  board_label: '',
  delivery_date: '',
  delivery_mode: '',
  ship_to_party_id: '',
  ship_to_role: '',
  ship_to_needs_role: false,
  ship_to_address_pending: false,
  ship_to_contact_ids: [],
  ship_to_typed_before: '',
  ship_to_name: '',
  ship_to_address: '',
  site_contact_name: '',
  site_contact_phone: '',
  site_contact_note: '',
  loan_value: '2',
  loan_unit: 'months',
  goods_demo: false,
  goods_new: false,
  purpose: '',
};

let lineSeq = 0;
export const nextKey = () => `line-${(lineSeq += 1)}`;

/** A row the user added but never picked a product for is not a line. */
const pickedLines = (s: FormState) => s.lines.filter((l) => l.product_id);

export const blankLine = (): DraftLine => ({
  key: nextKey(),
  product_id: '',
  label: '',
  qty: '1',
  remark: '',
});

const clean = (v: string): string | null => (v.trim() ? v.trim() : null);

export function stateFromDetail(d: SampleRequestDetail): FormState {
  return {
    customer_id: d.customer_id ?? '',
    customer_label: d.customer_name ?? '',
    customer_name: d.customer_id ? '' : (d.customer_name ?? ''),
    project_id: d.project_id ?? '',
    project_label: d.project_id ? [d.project_code, d.project_name].filter(Boolean).join(' - ') : '',
    project_title: d.project_id ? '' : (d.project_title ?? ''),
    quotation_document_id: d.quotation_document_id ?? '',
    quotation_issue_id: d.quotation_issue_id ?? '',
    prefill_signature: '',
    scope_note: d.scope_note ?? '',
    lines: (d.lines ?? []).map((l) => ({
      key: nextKey(),
      product_id: l.product_id,
      label: codeWithName(l.product_code, l.product_name),
      qty: String(l.qty),
      remark: l.remark ?? '',
      inactive: l.product_active === false,
    })),
    board_mounting: Boolean(d.board_mounting),
    board_label: d.board_label ?? '',
    delivery_date: d.delivery_date ?? '',
    delivery_mode: d.delivery_mode ?? '',
    ship_to_party_id: d.ship_to_party_id ?? '',
    ship_to_role: d.ship_to_role ?? '',
    ship_to_needs_role: false,
    ship_to_address_pending: false,
    ship_to_contact_ids: [],
    ship_to_typed_before: d.ship_to_party_id ? '' : (d.ship_to_name ?? ''),
    ship_to_name: d.ship_to_name ?? '',
    ship_to_address: d.ship_to_address ?? '',
    site_contact_name: d.site_contact_name ?? '',
    site_contact_phone: d.site_contact_phone ?? '',
    site_contact_note: d.site_contact_note ?? '',
    loan_value: String(d.loan_value ?? 2),
    loan_unit: d.loan_unit ?? 'months',
    goods_demo: d.goods_from === 'demo',
    goods_new: d.goods_from === 'new',
    purpose: d.purpose ?? '',
  };
}

const signature = (lines: DraftLine[]) =>
  JSON.stringify(lines.map((l) => [l.product_id, l.qty, l.remark]));

/**
 * True while the rows are still the pre-fill's own (or blank), so a project or quotation change
 * may replace them; any delete, add or edit makes them the person's.
 */
export function linesUntouched(s: FormState): boolean {
  if (s.lines.every((l) => !l.product_id && !l.remark.trim())) return true;
  return Boolean(s.prefill_signature) && s.prefill_signature === signature(s.lines);
}

/** The rows and source a new request takes from its project's quotation (SFQ-20, SFQ-25). */
export function prefillFromQuotation(
  prefill: SampleRequestQuotationPrefill,
): Pick<FormState, 'lines' | 'quotation_document_id' | 'quotation_issue_id' | 'prefill_signature'> {
  const lines: DraftLine[] = prefill.lines.map((l) => ({
    key: nextKey(),
    product_id: l.product_id,
    label: codeWithName(l.product_code, l.product_name),
    qty: '1',
    remark: '',
  }));
  if (lines.length === 0) {
    return {
      lines: [blankLine()],
      quotation_document_id: '',
      quotation_issue_id: '',
      prefill_signature: '',
    };
  }
  return {
    lines,
    quotation_document_id: prefill.document_id ?? '',
    quotation_issue_id: prefill.issue_id ?? '',
    prefill_signature: signature(lines),
  };
}

/**
 * One line under the table naming the quotation lines that did not become rows, or null. A line
 * with no catalogue product never becomes a row (owner Q3, 30 Oct: "free text product shouldn't be
 * allowed"); neither does an inactive product.
 */
export function prefillNote(prefill: SampleRequestQuotationPrefill): string | null {
  const noProduct = prefill.skipped.filter((s) => s.reason === 'no_product').length;
  const inactive = prefill.skipped.filter((s) => s.reason === 'inactive').length;
  const total = noProduct + inactive;
  if (total === 0) return null;
  const why = [
    noProduct ? `${noProduct} ${noProduct === 1 ? 'has' : 'have'} no product` : '',
    inactive ? `${inactive} ${inactive === 1 ? 'product is' : 'products are'} inactive` : '',
  ].filter(Boolean);
  return `${total} quotation ${total === 1 ? 'line was' : 'lines were'} not added: ${why.join(', ')}.`;
}

/** One tick is that value; neither or both is either. */
export function goodsFromTicks(demo: boolean, fresh: boolean): SampleRequestGoodsFrom {
  if (demo && !fresh) return 'demo';
  if (fresh && !demo) return 'new';
  return 'either';
}

export function payloadFromState(s: FormState): SampleRequestWrite {
  return {
    customer_id: s.customer_id || null,
    customer_name: s.customer_id ? null : clean(s.customer_name),
    project_id: s.project_id || null,
    project_title: s.project_id ? null : clean(s.project_title),
    quotation_document_id: s.quotation_document_id || null,
    quotation_issue_id: s.quotation_issue_id || null,
    scope_note: clean(s.scope_note),
    delivery_date: s.delivery_date || null,
    delivery_mode: s.delivery_mode || null,
    ship_to_name: clean(s.ship_to_name),
    ship_to_address: clean(s.ship_to_address),
    site_contact_name: clean(s.site_contact_name),
    site_contact_phone: clean(s.site_contact_phone),
    site_contact_note: clean(s.site_contact_note),
    // Only built from a form whose numberErrors() is empty: the typed whole number goes through as typed.
    loan_value: Number(s.loan_value),
    loan_unit: s.loan_unit,
    goods_from: goodsFromTicks(s.goods_demo, s.goods_new),
    purpose: clean(s.purpose),
    board_mounting: s.board_mounting,
    board_label: s.board_mounting ? clean(s.board_label) : null,
    lines: pickedLines(s).map((l) => ({
      product_id: l.product_id,
      qty: Number(l.qty),
      remark: clean(l.remark),
    })),
  };
}

/** The same refusals the server makes on submit, so the message lands before the round trip. */
export function validate(
  s: FormState,
  rules: { requireProject?: boolean } = {},
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!s.customer_id && !s.customer_name.trim()) {
    errors.customer_id = 'Pick the customer, or type the customer name';
  }
  if (rules.requireProject) {
    if (!s.project_id) errors.project_id = 'Pick a registered project';
  } else if (!s.project_id && !s.project_title.trim()) {
    errors.project_id = 'Pick the project, or type its title';
  }
  if (!s.delivery_date) errors.delivery_date = 'Enter the Request Delivery Date';
  if (!s.delivery_mode) errors.delivery_mode = 'Choose a delivery mode';
  if (!s.ship_to_name.trim()) errors.ship_to_name = 'Enter who the samples go to';
  if (pickedLines(s).length === 0 && !s.board_mounting) errors.lines = 'Add at least one item';
  if (s.board_mounting && !s.board_label.trim()) errors.board_label = 'Enter the board label';
  return { ...errors, ...numberErrors(s) };
}

/** The qty and loan-period checks: shared by Submit and Save as draft, which never sends a bad figure. */
export function numberErrors(s: FormState): Record<string, string> {
  const errors: Record<string, string> = {};
  const loanError = numberFieldError(s.loan_value, WHOLE_AT_LEAST_ONE);
  if (loanError) errors.loan_value = loanError;
  for (const line of pickedLines(s)) {
    const qtyError = numberFieldError(line.qty, WHOLE_AT_LEAST_ONE);
    if (qtyError) errors[`qty_${line.key}`] = qtyError;
  }
  return errors;
}

/** The source quotation a row's product search is narrowed to, or undefined without one (SFQ-27). */
export function productSource(
  documentId: string | null | undefined,
  issueId: string | null | undefined,
): SampleRequestProductSource | undefined {
  return documentId
    ? { quotation_document_id: documentId, quotation_issue_id: issueId || null }
    : undefined;
}

/** The product search query string, with the source quotation when there is one. */
export function productSearchQuery(q: string, source?: SampleRequestProductSource): string {
  const usp = new URLSearchParams({ q });
  if (source) {
    usp.set('quotation_document_id', source.quotation_document_id);
    if (source.quotation_issue_id) usp.set('quotation_issue_id', source.quotation_issue_id);
  }
  return usp.toString();
}

// ------------------------------------------------------------------ SAMPLE-REQUEST-V2 staff form

/** A party picked as Ship to (null clears it). */
export interface ShipToPick {
  id: string;
  name: string;
  address?: string | null;
  /** The role it plays on the project, or the role it would be added in. */
  role: string | null;
  /** The project's site address: the fallback for a party with none (card rule 2). */
  siteAddress?: string | null;
  /** Not on the project yet: the role must be picked before submit. */
  needsRole?: boolean;
  /** Picked from a names-only list: the address is unknown here (the server fills it). */
  addressUnknown?: boolean;
}

/** Ship to = a party: its name, its address or else the project site address; the old contact
 * person belonged to the old party, so it goes. */
export function withShipToParty(s: FormState, party: ShipToPick | null): FormState {
  const cleared = {
    ...s,
    ship_to_contact_ids: [],
    site_contact_name: '',
    site_contact_phone: '',
  };
  if (!party) {
    return {
      ...cleared,
      ship_to_party_id: '',
      ship_to_role: '',
      ship_to_needs_role: false,
      ship_to_address_pending: false,
      ship_to_name: '',
      ship_to_address: '',
    };
  }
  return {
    ...cleared,
    ship_to_party_id: party.id,
    ship_to_role: party.role ?? '',
    ship_to_needs_role: Boolean(party.needsRole),
    ship_to_address_pending: Boolean(party.addressUnknown),
    ship_to_name: party.name,
    ship_to_address: (party.address ?? '').trim() || (party.siteAddress ?? '').trim(),
    ship_to_typed_before: '',
  };
}

/** The contact person = the party's people picked in the registration popup: "A & B", the first
 * one's phone (owner Q3 a, the proposal Attn rule). */
export function withShipToContacts(
  s: FormState,
  contacts: { id: string; name: string; phone?: string | null }[],
): FormState {
  const first = contacts[0];
  return {
    ...s,
    ship_to_contact_ids: contacts.map((c) => c.id),
    site_contact_name: contacts.map((c) => c.name).join(' & '),
    site_contact_phone: first?.phone ? formatPhone(first.phone) || first.phone : '',
  };
}

/** The staff submit refusals, the server's own (card rules 1-2), checked before the round trip. */
export function validateStaff(
  s: FormState,
  opts: { requireProject?: boolean } = {},
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!s.customer_id) errors.customer_id = 'Pick the customer';
  if (opts.requireProject) {
    if (!s.project_id) errors.project_id = 'Pick a registered project';
  } else if (!s.project_id && !s.project_title.trim()) {
    errors.project_id = 'Pick the project, or type its title';
  }
  if (!s.ship_to_party_id) errors.ship_to_party_id = 'Pick who the samples go to';
  else if (s.ship_to_needs_role && !s.ship_to_role) errors.ship_to_role = 'Pick the role it plays';
  if (s.ship_to_party_id && !s.ship_to_address_pending && !s.ship_to_address.trim()) {
    errors.ship_to_address = 'Enter the shipping address';
  }
  if (!s.delivery_date) errors.delivery_date = 'Enter the Request Delivery Date';
  if (!s.delivery_mode) errors.delivery_mode = 'Choose a delivery mode';
  if (pickedLines(s).length === 0 && !s.board_mounting) errors.lines = 'Add at least one item';
  if (s.board_mounting && !s.board_label.trim()) errors.board_label = 'Enter the board label';
  return { ...errors, ...numberErrors(s) };
}

/**
 * The staff form's write. Ship to is sent as the form shows it: the party (null when cleared), its
 * role, the picked people, the printed name, the address and the contact person (null when
 * cleared), so a cleared field is cleared on the server too. An address the form could not see
 * (names-only pick, `ship_to_address_pending`) is left to the server. "For", the contact note and
 * a typed customer are never sent: an old row keeps whatever it had (card rules 1, 3, 4).
 */
export function staffPayloadFromState(s: FormState): SampleRequestWrite {
  const {
    customer_name: _typedCustomer,
    scope_note: _scope,
    site_contact_note: _note,
    ship_to_address: address,
    ...rest
  } = payloadFromState(s);
  const body: SampleRequestWrite = { ...rest };
  if (s.ship_to_party_id) {
    body.ship_to_party_id = s.ship_to_party_id;
    if (s.ship_to_role) body.ship_to_role = s.ship_to_role;
    body.ship_to_contact_ids = s.ship_to_contact_ids;
    if (address || !s.ship_to_address_pending) body.ship_to_address = address;
  } else {
    // Cleared, or a draft still on its typed Ship To (example E): no party on the server either.
    body.ship_to_party_id = null;
    body.ship_to_address = address;
  }
  return body;
}
