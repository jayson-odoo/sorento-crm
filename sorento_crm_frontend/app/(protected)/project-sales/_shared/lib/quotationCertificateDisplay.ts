import type { CertificateRow, CertificateValidity } from '../services/quotationCertificateService';

/** The validity pill of a quoted certificate: one wording and colour on the list and the page. */
export const VALIDITY: Record<
  CertificateValidity,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' }
> = {
  valid: { label: 'Valid', variant: 'success' },
  expiring: { label: 'Expiring', variant: 'warning' },
  expired: { label: 'Expired', variant: 'destructive' },
  unknown: { label: 'Unknown', variant: 'secondary' },
};

/**
 * The "Rows marked" filter (owner, 11 Nov 2026: exactly these six). A box found by a guessed code
 * is plain Marked: there is no "Suggested, check" state. A row whose code is not printed on its
 * file (`not_found`, and the greyed `not_on_certificate`) is Code not found. A hand-added row with
 * no quoted product (`none`) belongs to no bucket.
 */
export const MARKED_FILTERS = [
  { value: 'marked', label: 'Marked' },
  { value: 'edited', label: 'Edited' },
  { value: 'code_not_found', label: 'Code not found' },
  { value: 'code_needed', label: 'Code needed' },
  { value: 'no_text', label: 'No text' },
  { value: 'no_file', label: 'No file' },
] as const;

export type MarkedFilter = (typeof MARKED_FILTERS)[number]['value'];

export function markedFilterOf(state: CertificateRow['marked']['state']): MarkedFilter | null {
  switch (state) {
    case 'found':
      return 'marked';
    case 'edited':
      return 'edited';
    case 'not_found':
    case 'not_on_certificate':
      return 'code_not_found';
    case 'code_needed':
      return 'code_needed';
    case 'no_text':
      return 'no_text';
    case 'no_file':
      return 'no_file';
    default:
      return null;
  }
}

/** The one-line words of a row's Rows marked cell. */
export function markedText(marked: CertificateRow['marked']): string {
  const rows = `${marked.count} ${marked.count === 1 ? 'row' : 'rows'}`;
  switch (marked.state) {
    case 'found':
      return rows;
    case 'edited':
      return `${rows}, edited`;
    case 'not_found':
    case 'not_on_certificate':
      return 'Code not found';
    case 'code_needed':
      return 'Code needed';
    case 'no_text':
      return 'No text, draw the box';
    case 'no_file':
      return 'No file';
    default:
      return 'No quoted product';
  }
}
