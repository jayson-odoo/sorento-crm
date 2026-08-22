'use client';

const DEFAULT_ACCEPT = '.xlsx,.xls,.xlsm';

/**
 * Excel uploader accept attribute (`.xlsx,.xls,.xlsm`).
 *
 * This used to read `excel_upload_accept_extensions` off the system settings,
 * but that is NOT a column on the backend SystemSetting model and never has
 * been, so the read could only ever fall through to this constant - and the
 * `/settings/app-config` projection pins six fields by response_model, so the
 * key is dropped before it reaches the client. The request bought nothing and
 * is gone. Making the extensions configurable needs a column and a projection
 * field first, not a fetch.
 */
export function useExcelAccept(): string {
  return DEFAULT_ACCEPT;
}
