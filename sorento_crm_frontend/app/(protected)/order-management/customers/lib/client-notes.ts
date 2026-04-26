/** Lines optionally appended to `Customer.notes` when saving the client form (aligned with CreateClientModal). */
import { AGE_GROUPS, CONTACT_METHODS, RACE_OPTIONS } from '../forms/client-form-constants';

function normalizedKey(v: string): string {
  return v
    .trim()
    .toLowerCase()
    .replace(/[–—−]/g, '-')
    .replace(/\s+/g, ' ');
}

function pickCanonical(raw: string, options: readonly string[]): string {
  const k = normalizedKey(raw);
  const exact = options.find((x) => normalizedKey(x) === k);
  return exact ?? raw.trim();
}

export function parseClientNotesMeta(notes?: string | null) {
  let referredBy = '';
  let picName = '';
  let ageGroup = '';
  let race = '';
  let preferredContact = '';
  if (!notes?.trim()) {
    return { referredBy, picName, ageGroup, race, preferredContact };
  }
  for (const raw of notes.split('\n')) {
    const line = raw.trim();
    const rb = /^referred\s*by\s*[:\-]\s*(.+)$/i.exec(line);
    if (rb?.[1]) referredBy = rb[1].trim();
    const pic = /^pic\s*name\s*[:\-]\s*(.+)$/i.exec(line);
    if (pic?.[1]) picName = pic[1].trim();
    const ag = /^age\s*group\s*[:\-]\s*(.+)$/i.exec(line);
    if (ag?.[1]) ageGroup = pickCanonical(ag[1], AGE_GROUPS);
    const rc = /^race\s*[:\-]\s*(.+)$/i.exec(line);
    if (rc?.[1]) race = pickCanonical(rc[1], RACE_OPTIONS);
    const pc = /^preferred\s*contact(?:\s*method)?\s*[:\-]\s*(.+)$/i.exec(line);
    if (pc?.[1]) preferredContact = pickCanonical(pc[1], CONTACT_METHODS);
  }
  return { referredBy, picName, ageGroup, race, preferredContact };
}

export function buildClientNotesLines(parts: {
  referred_by?: string;
  pic_name?: string;
  age_group?: string;
  race?: string;
  preferred_contact_method?: string;
}): string | undefined {
  const lines = [
    parts.referred_by?.trim() && `Referred by: ${parts.referred_by.trim()}`,
    parts.pic_name?.trim() && `PIC name: ${parts.pic_name.trim()}`,
    parts.age_group?.trim() && `Age group: ${parts.age_group.trim()}`,
    parts.race?.trim() && `Race: ${parts.race.trim()}`,
    parts.preferred_contact_method?.trim() && `Preferred contact: ${parts.preferred_contact_method.trim()}`,
  ].filter(Boolean) as string[];
  return lines.length ? lines.join('\n') : undefined;
}
