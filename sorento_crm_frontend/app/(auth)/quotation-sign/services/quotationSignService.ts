import { extractApiError } from '@/lib/api-client';
import type { MatrixHeader } from '@/app/(protected)/project-sales/_shared/lib/quotationMatrix';

/**
 * The customer's counter-sign page. PUBLIC: a token is the only credential.
 *
 * Contract, matching `app/api/v1/public/quotation_sign.py` exactly:
 *
 *   GET  /api/v1/public/quotation-sign/{token}                  -> QuotationSignPage
 *   POST /api/v1/public/quotation-sign/{token}/accept           -> QuotationSignPage (same shape)
 *   (`/request-changes`, the older free-text request, stays on the backend; this page no longer
 *   sends it.)
 *   POST /api/v1/public/quotation-sign/{token}/amendment-request -> QuotationSignPage (same shape)
 *
 * `amendment-request` carries the customer's FEEDBACK (PS-QUOTE-MATRIX R19): notes on an item or
 * on one cell, each with an optional hint (a quantity, a price, removal, another model). It may be
 * sent more than once and never blocks signing; nothing in it is accepted or applied.
 *
 * Both decisions answer with the whole page, so the browser settles on the new state without a
 * second fetch. `request-changes` answers 409 on a quotation that is already accepted: the
 * counter-signature won the scopes, and the two decisions cannot both stand.
 *
 * Two deliberate departures from the rest of the app's services:
 *
 * 1. **Plain `fetch`, not `apiFetch`.** `apiFetch` mints a NextAuth bearer token and attaches it
 *    to anything under `/api/v1/`. The signer is a stranger with no session, and a staff member
 *    opening the same link would otherwise send their own credential to a public endpoint. Plain
 *    `fetch` against a resolved base is also what the contact portal already does
 *    (`app/(auth)/portal/lib/portal-client.ts`), so this is the established public-surface path
 *    rather than a new one. See `apiBase` below for why the base cannot be left off.
 * 2. **A typed error carrying the HTTP status**, because the page has to tell "this link is dead"
 *    (a calm, final message) apart from "the network hiccuped" (retry). A bare Error string cannot.
 *
 * Money and quantities arrive as decimal STRINGS and stay strings all the way to the screen. The
 * backend already excluded rate-only lines from every total it sends, so there is nothing to add
 * up here - and a float sum is how a quotation ends up disagreeing with its own PDF by a cent.
 */

const PATH = '/api/v1/public/quotation-sign';

/**
 * Where the backend actually is.
 *
 * A relative path alone is NOT enough, and looks fine right up until it 404s: the dev rewrite in
 * `next.config` only proxies `/api/v1/*` when `NEXT_PUBLIC_API_URL` is UNSET. Set it (every
 * deployed environment does, and so does any worktree running the backend off :8000) and the
 * relative URL resolves against the Next origin, which serves no such route. Same resolution the
 * contact portal uses, for the same reason.
 */
function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? configured.replace(/\/$/, '') : '';
}

function signUrl(path: string): string {
  return `${apiBase()}${PATH}${path}`;
}

/** Carries the status so the page can render 404 as a resting state, not as a failure. */
export class QuotationSignError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'QuotationSignError';
    this.status = status;
  }

  /** An unknown OR expired token. The backend answers both identically, on purpose. */
  get isDeadLink(): boolean {
    return this.status === 404;
  }
}

export type QuotationSignSignature = {
  id: string;
  signer_name: string | null;
  mode: string;
  image_data_uri: string | null;
  signed_at: string | null;
  ip_address: string | null;
  /** Decimal strings, or null when the browser refused. Rendered as `-`, never guessed. */
  gps_lat: string | null;
  gps_lng: string | null;
  /**
   * The nearest known town to those coordinates, e.g. "Kajang, Selangor". Resolved by the backend
   * from one offline table it shares with the PDF renderer, so the screen and the printed
   * document cannot disagree. Null when nothing known is near enough to name.
   */
  gps_place?: string | null;
};

export type QuotationSignLine = {
  /** The issued line's id: what a suggested change names, and nothing else. */
  id: string;
  item_label: string | null;
  description: string | null;
  technical_spec: string | null;
  /** The product photo as an inline data URI (the PDF's own bytes), null when the line has none. */
  image_url?: string | null;
  /** The technical drawing, the same way. It fills the TECHNICAL SPEC column. */
  drawing_url?: string | null;
  brand: string | null;
  product_code: string | null;
  quantity: string;
  /** Printed after the quantity, as the PDF's QTY cell does ("2 pcs"). */
  uom?: string | null;
  unit_price: string;
  complete_set: string | null;
  band_label: string | null;
  is_rate_only: boolean;
  /** Null on a rate-only line: the money column prints the words instead of a zero. */
  amount: string | null;
  /** PS-QUOTE-MATRIX: quantity per column on a scope with column headers. */
  qty_cells?: Record<string, string> | null;
};

/**
 * One column of the quotation, as the server decides it for this scope: the same set, order and
 * label as the PDF (backend `app/services/quotation_columns.py`). The page keeps no list of its own.
 */
export type QuotationSignColumn = {
  key: string;
  label: string;
};

export type QuotationSignScope = {
  scope_label: string;
  scope_total: string;
  columns: QuotationSignColumn[];
  lines: QuotationSignLine[];
  /** PS-QUOTE-MATRIX: the scope's column headers; `[]` or absent = one Qty column. */
  matrix_columns?: MatrixHeader[] | null;
};

/** One cover page row. The terms row carries `html`, every other row `text`. */
export type QuotationCoverRow = {
  key: string;
  label: string;
  text?: string | null;
  html?: string | null;
};

export type QuotationSignPage = {
  our_ref: string | null;
  /** PS-PROPOSAL-QUOTATION: what the customer holds, a proposal or the quotation. */
  document_kind?: 'proposal' | 'quotation';
  /** The cover page rows of a new-layout issue; null for an issue from before the cover page. */
  cover_rows?: QuotationCoverRow[] | null;
  issue_no: number;
  doc_date: string | null;
  subject_title: string | null;
  sender_name: string | null;
  /** The company logo, null when none is set. */
  sender_logo_url: string | null;
  recipient_name: string | null;
  recipient_address: string | null;
  attn_name: string | null;
  /** Rendered HTML off the issue snapshot. Sanitized at the render site, never trusted. */
  cover_letter: string | null;
  terms: string | null;
  signatory_name: string | null;
  signatory_phone: string | null;
  scopes: QuotationSignScope[];
  grand_total: string;
  sorento_signature: QuotationSignSignature | null;
  customer_signature: QuotationSignSignature | null;
  accepted_at: string | null;
  is_accepted: boolean;
  /**
   * The other decision, on the same issue. Both can be set - somebody who asked for changes may
   * still sign - and the page renders whichever one was REACHED, so acceptance wins the display
   * while the request stays on the record.
   */
  changes_requested_at: string | null;
  changes_requested_note: string | null;
  changes_requested_by_name: string | null;
  is_changes_requested: boolean;
  /**
   * Feedback already sent on this issue, when the page carries it: read only to mark what already
   * has a note (amber corner / dot). Null when none was sent.
   */
  amendment_request?: QuotationSignAmendment | null;
  /** The later revision's `Quotation No.` when this one was replaced, else null. */
  superseded_by_ref: string | null;
  can_sign: boolean;
  /** The one reason Sign is off, or null when the issue can be signed. */
  sign_blocked_reason: 'accepted' | 'superseded' | null;
};

/** One note already sent, as far as this page reads it: what it points at. */
export type QuotationSignAmendmentRow = {
  id: string;
  line_id: string;
  cell_key?: string | null;
};

export type QuotationSignAmendment = {
  id: string;
  submitted_at: string | null;
  rows: QuotationSignAmendmentRow[];
};

export type QuotationFeedbackKind = 'note' | 'quantity' | 'unit_price' | 'remove' | 'model_swap';

/**
 * One feedback item: a note on a whole item, or on one cell (`cell_key`, kinds `note` and
 * `quantity` only). `value` is the hint as a decimal STRING (a quantity, a price, or a swap's
 * optional price); `model` is the other model as typed.
 */
export type QuotationFeedbackItem = {
  line_id: string;
  cell_key?: string;
  kind: QuotationFeedbackKind;
  value?: string;
  model?: string;
  note?: string;
};

/** One submit: items, and/or a free note. At least one of the two. */
export type QuotationFeedbackBody = {
  items: QuotationFeedbackItem[];
  note?: string | null;
  requester_name?: string | null;
};

export type QuotationSignAcceptBody = {
  signer_name: string;
  mode: string;
  image_data_uri: string;
  /** Sent as strings so a browser's 13-decimal fix reaches Postgres exactly as observed. */
  gps_lat: string | null;
  gps_lng: string | null;
  /** The customer ticked the Terms box. The backend refuses an issue with terms without it. */
  terms_accepted: boolean;
};

export async function getQuotationSignPage(token: string): Promise<QuotationSignPage> {
  const response = await fetch(signUrl(`/${encodeURIComponent(token)}`));
  if (!response.ok) {
    throw new QuotationSignError(
      await extractApiError(response, 'This quotation could not be loaded.'),
      response.status,
    );
  }
  return response.json();
}

export async function acceptQuotation(
  token: string,
  body: QuotationSignAcceptBody,
): Promise<QuotationSignPage> {
  const response = await fetch(signUrl(`/${encodeURIComponent(token)}/accept`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new QuotationSignError(
      await extractApiError(response, 'Your signature could not be saved.'),
      response.status,
    );
  }
  return response.json();
}

export async function submitQuotationFeedback(
  token: string,
  body: QuotationFeedbackBody,
): Promise<QuotationSignPage> {
  const response = await fetch(signUrl(`/${encodeURIComponent(token)}/amendment-request`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new QuotationSignError(
      await extractApiError(response, 'Your feedback could not be sent.'),
      response.status,
    );
  }
  return response.json();
}

/**
 * The view beacon (PS-QUOTE-VIEWS): the customer opened this link. `visitorId` is a random id this
 * browser keeps; the backend stores only its digest, for the 30-minute "same browser" rule.
 * Best-effort by design: a lost beacon costs one count, never the customer's page.
 */
export async function recordQuotationView(token: string, visitorId: string): Promise<void> {
  await fetch(signUrl(`/${encodeURIComponent(token)}/view`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visitor_id: visitorId }),
    keepalive: true,
  });
}
