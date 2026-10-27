/**
 * Contact access sheet import - feature service (BULK-CONTACT-ACCESS).
 *
 * Layering: AccessSheetImportDialog -> useAccessSheetImport -> THIS service -> lib/api.
 *
 *   POST /user-management/contacts/access-sheet  multipart file + dry_run (+ confirmed JSON)
 *        -> AccessSheetResult                     user_management.contacts.edit
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

// Staff requests run under one active company; the sheet spans Sorento and Mocha, so ask for every granted one.
const URL = '/api/v1/user-management/contacts/access-sheet?company_scope=grants';

export type AccessSheetAccount = {
  customer_id: string;
  customer_code: string;
  customer_name: string;
  company_code: string | null;
  is_active: boolean;
  sales_agent: string | null;
  sheet_agent: string | null;
  match: 'exact' | 'candidate';
  score: number | null;
  proposed: boolean;
  /** Found contacts of the block whose own row tags this account's company. */
  links_to: string[];
};

export type AccessSheetChange = { facet: string; before: unknown; after: unknown };

export type AccessSheetContact = {
  line: number;
  name: string;
  phone: string;
  in_crm: boolean;
  contact_id: string | null;
  role: 'owner' | 'employee';
  companies: string[];
  template: string;
  status: 'applied' | 'no_change' | 'skipped';
  skip_reason: null | 'not_in_crm' | 'ambiguous_phone' | 'dealer_not_confirmed' | 'row_error';
  changes: AccessSheetChange[];
  warnings: string[];
  /** Per facet, what the contact holds outside its template (warning `holds_more`). */
  holds_more_items: { facet: string; items: string[] }[];
  /** Accounts already linked whose company is not on the contact's row; shown, never removed. */
  outside_links: string[];
  not_applied: string[];
};

export type AccessSheetBlock = {
  key: string;
  dealer: string;
  alt_dealers: string[];
  companies: string[];
  status: 'exact' | 'pick' | 'none';
  warnings: string[];
  accounts: AccessSheetAccount[];
  contacts: AccessSheetContact[];
};

export type AccessSheetCounts = {
  rows: number;
  row_errors: number;
  contacts_found: number;
  not_in_crm: number;
  ambiguous: number;
  already_configured: number;
  blocks: number;
  blocks_exact: number;
  blocks_pick: number;
  blocks_none: number;
  applied: number;
  no_change: number;
  skipped: number;
};

export type AccessSheetResult = {
  dry_run: boolean;
  counts: AccessSheetCounts;
  errors: { line: number; reason: string }[];
  blocks: AccessSheetBlock[];
};

/** { dealer block key: [customer id] }, confirmed blocks only. */
export type AccessSheetConfirmed = Record<string, string[]>;

async function post(file: File, dryRun: boolean, confirmed?: AccessSheetConfirmed): Promise<AccessSheetResult> {
  const body = new FormData();
  body.append('file', file);
  body.append('dry_run', String(dryRun));
  if (confirmed) body.append('confirmed', JSON.stringify(confirmed));
  const response = await apiFetch(URL, { method: 'POST', body });
  if (!response.ok) {
    throw new Error(await extractApiError(response, dryRun ? 'Failed to read the sheet' : 'Failed to apply the sheet'));
  }
  return response.json();
}

export const previewAccessSheet = (file: File) => post(file, true);

export const applyAccessSheet = (file: File, confirmed: AccessSheetConfirmed) => post(file, false, confirmed);
