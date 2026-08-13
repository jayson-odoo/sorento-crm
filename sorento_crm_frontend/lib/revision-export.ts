/**
 * Shared pieces of "export one version of a revisable form" (round 6, 6.3/6.4).
 *
 * The PDF side of this lives on the backend (`pdf_revision_support.py`); the
 * Excel side is client-side and split across two libraries (ExcelJS for the
 * stock inquiry, SheetJS for PR/SF). These helpers are the bits BOTH of those
 * need - the filename marker, the sheet name, and the rows that say which
 * version a sheet is - so the two exporters cannot describe the same revision
 * differently, and neither can disagree with the PDF.
 *
 * Pure and presentation-free: no service, no hook, no React.
 */

import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import { withRevisionSuffix } from '@/lib/document-number';
import { formatDateInMalaysia } from '@/lib/helpers';

/**
 * Body of the two PDF export endpoints (round 6).
 *
 * Both keys are optional and mutually exclusive - the backend 400s on the pair
 * ("Ask for one revision or for the full history, not both."). An omitted body
 * is the export as it has always behaved: the current form, no lineage.
 */
export interface FormPdfExportOptions {
  /** Print ONE stored version, by revision entry id. */
  revision_id?: string | null;
  /** Current form first, then the whole lineage. */
  include_revisions?: boolean;
}

/** The entry kinds the backend writes (mirrors `PortalRevisionService`). */
const KIND_ORIGINAL = 'original';
const KIND_RESUBMISSION = 'resubmission';

/** Excel caps a sheet name at 31 characters and rejects `[]:*?/\`. */
export const EXCEL_SHEET_NAME_MAX = 31;

/**
 * The document number AS AT this version: `SI-26-0184-R2`.
 *
 * Mirrors the backend's `revision_document_number` - read off the version's own
 * SNAPSHOT, suffixed through the one shared helper (UAC N1/N4), with the live
 * record's number only as a fallback for a snapshot that never stored one.
 */
export function revisionDocumentNumber(
  entry: FormRevisionEntry,
  numberField: string,
  fallback?: string | null,
): string | null {
  const snapshot = (entry.snapshot ?? {}) as Record<string, unknown>;
  const base = (snapshot[numberField] as string | null | undefined) ?? fallback;
  return withRevisionSuffix(base, entry.revision_no);
}

/**
 * The ONE word that says this file is a stored version, not the live record -
 * the same rule `_entry_filename_marker` applies to the PDF.
 *
 * Always present, exactly one of three: `original` for the version-0 entry
 * (whose own number is the bare one), `resubmitted-v<N>` for a resubmission
 * (which carries the record's CURRENT revision number, since an office reject
 * never burns a revision, UAC C4), and `as-submitted` for any other revision.
 *
 * The last one is not decoration. A revision export and the current-form export
 * of a record sitting at that same revision are two DIFFERENT documents: the
 * live one carries office fields the snapshot cannot. Landing them side by side
 * in a downloads folder under one name is exactly the filing failure UAC N5/P2
 * exists to prevent.
 */
export function revisionFileMarker(entry: FormRevisionEntry): string {
  const kind = String(entry.kind ?? '');
  if (kind === KIND_ORIGINAL) return 'original';
  if (kind === KIND_RESUBMISSION) {
    const version = Number(entry.version_no ?? 0);
    return `resubmitted-v${Number.isFinite(version) ? Math.trunc(version) : 0}`;
  }
  return 'as-submitted';
}

/**
 * The filename of a ONE-version export:
 * `Stock_Inquiry_SI-26-0184-R1-as-submitted.xlsx`.
 *
 * Named after THAT version's own document number, exactly as the PDF is
 * (`filename_with_revision`), so the two exports of one revision agree. The old
 * form appended a second revision marker to the record's CURRENT number and
 * produced `Purchase_Request_PR-26-0007-R2-rev1.xlsx`: two revision markers
 * meaning different things in one filename.
 *
 * Exactly one marker, always. The number says WHICH version; the marker says
 * this is that stored version rather than the live record, and the two never
 * stack. The plain current-form export and the include-revisions export keep
 * their unmarked names.
 */
export function revisionExportFilename(
  stem: string,
  entry: FormRevisionEntry,
  documentNumber: string | null | undefined,
  extension = 'xlsx',
): string {
  const safe = String(documentNumber ?? '')
    .trim()
    .replace(/[^A-Za-z0-9\-_]/g, '');
  // `_` between stem and number is the Excel exports' own convention
  // (`Stock_Inquiry_...`); the PDF stems use `-`. Everything after the number is
  // identical on both sides.
  const name = safe ? `${stem}_${safe}` : stem;
  return `${name}-${revisionFileMarker(entry)}.${extension}`;
}

/** A sheet name Excel will accept: no `[]:*?/\`, never blank, never over 31. */
export function sanitizeSheetName(name: string | null | undefined, fallback = 'Revision'): string {
  const cleaned = String(name ?? '')
    .replace(/[[\]:*?/\\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return (cleaned || fallback).slice(0, EXCEL_SHEET_NAME_MAX);
}

/**
 * A sheet name not already used in this workbook.
 *
 * Labels are unique per lineage today ("Original", "Revision 1", ...), but a
 * duplicate name makes both ExcelJS and SheetJS throw, and losing a whole export
 * to a repeated label is not a trade worth taking.
 */
export function uniqueSheetName(name: string, taken: Set<string>): string {
  const base = sanitizeSheetName(name);
  if (!taken.has(base)) {
    taken.add(base);
    return base;
  }
  for (let i = 2; i < 100; i += 1) {
    const suffix = ` (${i})`;
    const candidate = `${base.slice(0, EXCEL_SHEET_NAME_MAX - suffix.length)}${suffix}`;
    if (!taken.has(candidate)) {
      taken.add(candidate);
      return candidate;
    }
  }
  taken.add(base);
  return base;
}

/** The sheet name for one revision: its own label ("Revision 2"). */
export function revisionSheetName(entry: FormRevisionEntry, taken: Set<string>): string {
  return uniqueSheetName(
    entry.label || (entry.revision_no ? `Revision ${entry.revision_no}` : 'Original'),
    taken,
  );
}

/** `12/08/2026 by Alice Tan` - when the version was sent, and by whom. */
export function revisionSubmittedLine(entry: FormRevisionEntry): string {
  const when = entry.submitted_at ? formatDateInMalaysia(entry.submitted_at) : '';
  const who = String(entry.submitted_by ?? '').trim();
  if (when && who) return `${when} by ${who}`;
  return when || who;
}

/**
 * The rows that name a revision sheet: which version, why it changed, when it
 * was sent.
 *
 * A sheet of superseded values is dangerous without them - it looks exactly like
 * the current form. `uppercase` follows the label casing of the sheet it joins
 * (the product inquiry form shouts its labels, the purchase request does not).
 * The reason row is omitted when there is none, exactly as the PDF omits it.
 */
export function revisionInfoRows(
  entry: FormRevisionEntry,
  options: { uppercase?: boolean } = {},
): (string | number)[][] {
  const label = (text: string) => (options.uppercase ? text.toUpperCase() : text);
  const rows: (string | number)[][] = [
    [label('Revision:'), entry.label || 'Revision'],
  ];
  const reason = String(entry.reason ?? '').trim();
  if (reason) rows.push([label('Reason:'), reason]);
  const submitted = revisionSubmittedLine(entry);
  if (submitted) rows.push([label('Submitted:'), submitted]);
  return rows;
}

/**
 * Whether a lineage holds anything beyond the record itself.
 *
 * A lone `original` entry IS the current form, so an include-revisions export of
 * a never-revised submission is silently just the form (mirrors the backend's
 * `has_revision_history`). A second entry counts even at revision 0, because a
 * resubmit after rejection writes a history row without consuming a revision
 * (UAC C4).
 */
export function hasRevisionLineage(
  entries: Pick<FormRevisionEntry, 'revision_no'>[] | null | undefined,
): boolean {
  const list = entries ?? [];
  if (list.length === 0) return false;
  if (list.length > 1) return true;
  return Number(list[0]?.revision_no ?? 0) > 0;
}

/**
 * The lineage in the order an export prints it: newest first, behind the current
 * form.
 *
 * The newest entry is NOT redundant with the current form - the live row can
 * carry office edits made after the contact's last submission, and only the
 * entry carries the reason and who sent it (same call the PDF makes).
 */
export function revisionsNewestFirst(
  entries: FormRevisionEntry[] | null | undefined,
): FormRevisionEntry[] {
  return [...(entries ?? [])].reverse();
}
