import type { QuotationDocumentBody } from '../services/quotationDocumentService';

const RECIPIENT_FIELDS = [
  'recipient_name_snapshot',
  'recipient_address_snapshot',
  'recipient_phone_snapshot',
  'recipient_email_snapshot',
] as const;

/**
 * The "To" part of a proposal / quotation save (PROJECT-PARTY-ROLES PR 2), added to the header
 * body the form already built (`body`, blanks as null).
 *
 * - A party picked, changed or cleared since the saved document is sent (`null` clears it), with
 *   the role a party not on the project is added in.
 * - On a new party, a block field the screen could not fill is left OUT, so the server fills it
 *   from the party (and the project's site address) instead of the null blanking it.
 * - Attn people are sent with their party.
 */
export function withRecipient(
  body: QuotationDocumentBody,
  header: QuotationDocumentBody | null | undefined,
  savedPartyId: string | null | undefined,
): QuotationDocumentBody {
  const out: QuotationDocumentBody = { ...body };
  const partyId = header?.recipient_party_id ?? null;
  const changed = partyId !== (savedPartyId ?? null);
  if (changed) {
    out.recipient_party_id = partyId;
    if (partyId) {
      if (header?.recipient_role) out.recipient_role = header.recipient_role;
      for (const field of RECIPIENT_FIELDS) {
        if (out[field] === null) delete out[field];
      }
    }
  }
  const attn = header?.attn_contact_ids ?? [];
  if (partyId && attn.length > 0) {
    out.recipient_party_id = partyId;
    out.attn_contact_ids = attn;
  }
  return out;
}
