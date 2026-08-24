/**
 * Friendly translation for integration_log technical fields.
 *
 * Maps backend `error_code` enum + status combinations to short
 * human-readable strings. Raw technical detail (request_payload,
 * status_code, retry_count, response_payload JSON) is intentionally
 * hidden behind a "View raw log ↗" link; never surface raw codes
 * to end users.
 *
 * Codes added in Phase 2 should be extended here. Unknown codes
 * fall back to `error_message` then to a generic phrase.
 */

import type {
  UploadActivityFile,
  UploadActivitySession,
} from './types';

export const ERROR_CODE_FRIENDLY: Record<string, string> = {
  N8N_CALLBACK_TIMEOUT: "Integration server didn't respond in 10 minutes",
  MAX_RETRIES_EXCEEDED: 'Tried 3 times, all failed',
  HTTP_5XX: 'Integration server error',
  HTTP_4XX: 'Bad request to integration server',
  WEBHOOK_DISABLED: 'Integration webhook is not configured',
  POST_FAILED: 'Upload failed',
  S3_DOWNLOAD_FAILED: "Couldn't read uploaded file from storage",
  VIRUS_DETECTED: 'File rejected by virus scan',
  FILE_TOO_LARGE: 'File exceeds size limit',
  DUPLICATE_PACKING_LIST:
    'Duplicate packing list - this container was already received',
};

function pluralise(word: string, count: number): string {
  return count === 1 ? word : `${word}s`;
}

/**
 * One-line friendly summary for a single file row.
 *
 * Order of precedence:
 *  1. terminal: linked → list names
 *  2. terminal: unlinked → reason or generic
 *  3. terminal: failed/post_failed → error_code map → error_message → generic
 *  4. in-flight: uploading / processing
 */
export function summariseFile(file: UploadActivityFile): string {
  if (file.status === 'linked') {
    if (file.linked.length === 0) return 'Linked';
    const names = file.linked.map((l) => l.display_name).join(', ');
    const entity = file.linked[0]?.entity_type ?? 'item';
    return `Linked to ${file.linked.length} ${pluralise(entity, file.linked.length)}: ${names}`;
  }

  if (file.status === 'unlinked') {
    const reason = file.unlinked_reasons[0]?.reason;
    return reason ?? 'No matching record found';
  }

  if (file.status === 'failed' || file.status === 'post_failed') {
    const code = file.error_code;
    if (code && ERROR_CODE_FRIENDLY[code]) return ERROR_CODE_FRIENDLY[code];
    if (file.error_message) return file.error_message;
    return 'Integration failed';
  }

  if (file.status === 'uploading') return 'Uploading…';
  if (file.status === 'processing') return 'Linking…';

  // fallback: any explicit summary the backend already shaped
  return file.summary || '';
}

/**
 * One-line summary for a whole session in the drawer header.
 * Uses aggregate counts for multi/bulk; falls back to single-file
 * summary when total==1.
 */
export function summariseSession(session: UploadActivitySession): string {
  if (session.session_type === 'import_job') {
    return summariseImportJob(session);
  }
  if (session.aggregate.total === 1 && session.files[0]) {
    return summariseFile(session.files[0]);
  }

  const { total, linked, unlinked, failed, uploading, processing } =
    session.aggregate;
  const done = linked + unlinked + failed;
  const inFlight = uploading + processing;

  const parts: string[] = [];
  if (inFlight > 0) {
    parts.push(`${done} / ${total}`);
  } else {
    parts.push(`${total} ${pluralise('file', total)}`);
  }
  if (linked > 0) parts.push(`${linked} linked`);
  if (unlinked > 0) parts.push(`${unlinked} unlinked`);
  if (failed > 0) parts.push(`${failed} failed`);
  return parts.join(' · ');
}

/**
 * One-line summary for an import_job session (Excel/data import - row counts
 * instead of file statuses).
 */
export function summariseImportJob(session: UploadActivitySession): string {
  const total = session.total_rows ?? 0;
  const processed = session.processed_rows ?? 0;
  const failed = session.failed_rows ?? 0;
  const skipped = session.skipped_rows ?? 0;

  if (session.status === 'failed') {
    return session.job_error || 'Import failed';
  }
  if (session.status === 'processing') {
    return total > 0 ? `Importing… ${processed} / ${total} rows` : 'Importing…';
  }
  const parts: string[] = [`${total} ${pluralise('row', total)}`];
  if (failed > 0) parts.push(`${failed} failed`);
  if (skipped > 0) parts.push(`${skipped} skipped`);
  return parts.join(' · ');
}

/**
 * Status icon character for compact rendering in rows.
 * Component layer maps these to Lucide icons; this is fallback text.
 */
export function statusGlyph(status: string): string {
  switch (status) {
    case 'linked':
      return '✅';
    case 'uploading':
    case 'processing':
      return '⏳';
    case 'unlinked':
      return 'ℹ️';
    case 'failed':
    case 'post_failed':
      return '❌';
    case 'partial':
      return '⚠️';
    default:
      return '•';
  }
}
