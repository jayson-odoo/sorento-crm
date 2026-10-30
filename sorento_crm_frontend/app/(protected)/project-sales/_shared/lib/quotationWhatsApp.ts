import type { QuotationDocument, QuotationIssue } from '../services/quotationDocumentService';

/** Digits only; `00` dropped, `600` folded to `60`, a leading `0` read as Malaysian (`60`). */
function normalise(raw: string): string {
  let digits = raw.replace(/\D/g, '');
  if (digits.startsWith('00')) digits = digits.slice(2);
  // "+60 012-...": the country code typed together with the trunk 0.
  if (digits.startsWith('600')) return `60${digits.slice(3)}`;
  if (digits.startsWith('0')) return `60${digits.slice(1)}`;
  return digits;
}

/**
 * One typed phone number as wa.me digits. On top of the field rules a mobile typed without its
 * trunk 0 ("12-000 0001") is read as Malaysian; 1300, 1700 and 1800 numbers stay as typed.
 */
export function toWaDigits(raw: string): string {
  const digits = normalise(raw);
  if (/^1\d{8,9}$/.test(digits) && !/^1[378]00/.test(digits)) return `60${digits}`;
  return digits;
}

const MY_MOBILE = /^601\d{8,9}$/;

/**
 * The first number in a recipient field that WhatsApp can reach: a Malaysian mobile, or a foreign
 * number written with `+` or `00`. Landlines and bare digits that merely look foreign give ''.
 */
export function pickMobile(field: string | null | undefined): string {
  if (!field) return '';
  for (const part of field.split(/[\n/,;&]|\sor\s/i)) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    // Strict: a bare `1...` in the stored field is never taken for a mobile.
    const digits = normalise(trimmed);
    if (MY_MOBILE.test(digits)) return digits;
    const international = /^\s*(\+|00)/.test(trimmed);
    if (international && !digits.startsWith('60') && digits.length >= 8) return digits;
  }
  return '';
}

/** The number the customer reads on the paper; the printed ref when the revision has one. */
export function quotationNumberLabel(
  document: Pick<QuotationDocument, 'document_no'>,
  issue: Pick<QuotationIssue, 'issue_no' | 'our_ref_text'>,
): string {
  return issue.our_ref_text ?? `${document.document_no} (R${issue.issue_no})`;
}

export function whatsAppMessage({
  attn,
  numberLabel,
  subject,
  link,
  signatory,
}: {
  attn?: string | null;
  numberLabel: string;
  subject?: string | null;
  link: string;
  signatory?: string | null;
}): string {
  const to = attn?.trim();
  const about = subject?.trim();
  const from = signatory?.trim();
  return [
    to ? `Hi ${to},` : 'Hi,',
    '',
    `Here is our quotation ${numberLabel}${about ? ` for ${about}` : ''}.`,
    'You can view and accept it here:',
    link,
    '',
    'Thank you,',
    ...(from ? [from] : []),
  ].join('\n');
}
