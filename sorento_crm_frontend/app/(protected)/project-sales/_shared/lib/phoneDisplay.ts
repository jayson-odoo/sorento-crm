import { parsePhoneNumberFromString } from 'libphonenumber-js';
import { DEFAULT_PHONE_COUNTRY } from '@/components/common/PhoneInput';

/**
 * A phone as people read it (owner hand test, 10 Nov 2026): numbers are stored as E.164
 * ("+60129876543") and shown in one local format, "012-987 6543", next to older numbers typed by
 * hand. A Malaysian number reads in national format, a foreign one in international format; one
 * it cannot read is shown exactly as typed.
 */
export function formatPhone(value?: string | null): string {
  const raw = (value ?? '').trim();
  if (!raw) return '';
  const parsed = parsePhoneNumberFromString(raw.startsWith('60') ? `+${raw}` : raw, DEFAULT_PHONE_COUNTRY);
  if (!parsed?.isValid()) return raw;
  return parsed.country === DEFAULT_PHONE_COUNTRY ? parsed.formatNational() : parsed.formatInternational();
}
