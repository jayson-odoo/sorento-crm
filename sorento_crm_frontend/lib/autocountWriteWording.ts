/**
 * AC-QTSO-CRM: what an AutoCount write answer says, in plain words. One module owns the
 * sentences so the result dialog, the greyed menu items and the toasts cannot drift. The Shared
 * Service's codes are branched on in the server and never shown here.
 */
import { formatDateInMalaysia } from '@/lib/helpers';

export const AUTOCOUNT_WAITING_TEXT = 'Waiting for AutoCount';
export const AUTOCOUNT_SWITCHED_OFF_HERE = 'Changes to AutoCount are switched off here';
export const AUTOCOUNT_UNREACHABLE_TEXT = 'Could not reach AutoCount';
export const AUTOCOUNT_PENDING_TEXT =
  'Sent; AutoCount has not confirmed yet. It will show after the next sync.';
export const AUTOCOUNT_NOT_ACCEPTED_TEXT = 'The customer has not accepted this quotation yet';
export const AUTOCOUNT_NOT_IN_AUTOCOUNT_TEXT = 'Not in AutoCount yet';

export type WriteOutcome = 'done' | 'refused' | 'pending_verification' | 'unreachable';

/** The one sentence for an outcome. `done` names the document, `refused` quotes AutoCount. */
export function writeOutcomeText(
  outcome: WriteOutcome,
  detail: { docNo?: string | null; reason?: string | null } = {},
): string {
  switch (outcome) {
    case 'done':
      return `${detail.docNo ?? 'The document'} created in AutoCount`;
    case 'refused':
      return `AutoCount refused: ${(detail.reason ?? '').trim().replace(/\.+$/, '')}. Nothing was changed.`;
    case 'pending_verification':
      return AUTOCOUNT_PENDING_TEXT;
    case 'unreachable':
      return AUTOCOUNT_UNREACHABLE_TEXT;
  }
}

/** A capability reason code in plain words; anything unknown reads as waiting. */
export function reasonCodeText(code: string | null | undefined): string {
  if (code === 'WRITE_DISABLED' || code === 'WRITE_NOT_ALLOWED' || code === 'WRITE_COMPANY_NOT_TEST') {
    return AUTOCOUNT_SWITCHED_OFF_HERE;
  }
  return AUTOCOUNT_WAITING_TEXT;
}

/** "Changed in AutoCount since dd/mm/yyyy, open Compare first." from the stored last-modified. */
export function staleText(lastModified: string): string {
  return `Changed in AutoCount since ${formatDateInMalaysia(lastModified)}, open Compare first.`;
}
