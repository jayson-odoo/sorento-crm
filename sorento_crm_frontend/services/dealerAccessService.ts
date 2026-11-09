/**
 * Dealer access screen (DEALER-ACCESS-SCREEN, UAC S2-S6): a salesperson's own accounts and the
 * people who hold access to them. Module `sales`, permission `user_management.contacts.edit_own`.
 *
 *   GET  /api/v1/sales/dealer-access/accounts?company=SRT  -> [{ id, code, name }]
 *   GET  /api/v1/sales/dealer-access/people?page&limit&query&company[]&access -> { data, pagination }
 *   POST /api/v1/sales/dealer-access/grant   { company, account_ids, people: [{ name, phone, role }] }
 *        422 carries `details.rows: [{ index, error }]`, one reason per refused person.
 *   PUT  /api/v1/sales/dealer-access/people/{contact_id}  { company, role, account_ids }
 * Unlink is the deferred action `dealer_access.unlink` on entity type `dealer_access_link`.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/sales/dealer-access';

export type DealerAccessRole = 'owner' | 'employee';

export interface DealerAccessAccount {
  id: string;
  code: string;
  name: string;
}

export interface DealerAccessLinkedAccount extends DealerAccessAccount {
  link_id: string;
}

export interface DealerAccessRow {
  contact_id: string;
  name: string;
  phone: string;
  /** Company code, e.g. `SRT`. */
  company: string;
  company_name: string;
  accounts: DealerAccessLinkedAccount[];
  access: DealerAccessRole;
  owner_tag: string | null;
  other_account: boolean;
}

export interface DealerAccessPage {
  data: DealerAccessRow[];
  pagination: { page: number; limit: number; total: number };
}

export interface DealerAccessPeopleParams {
  pageIndex: number;
  pageSize: number;
  searchQuery?: string;
  companies?: string[];
  access?: DealerAccessRole | '';
}

export interface DealerAccessPersonInput {
  name: string;
  phone: string;
  role: DealerAccessRole;
}

export interface DealerAccessGrantBody {
  company: string;
  account_ids: string[];
  people: DealerAccessPersonInput[];
}

export interface DealerAccessGrantResult {
  rows: { index: number; contact_id: string; created: boolean; notes: string[] }[];
}

export interface DealerAccessUpdateBody {
  company: string;
  role: DealerAccessRole;
  account_ids: string[];
}

/** A grant the server refused row by row: `rowErrors` maps a person's index to its reason. */
export class DealerAccessGrantError extends Error {
  rowErrors: Record<number, string>;
  constructor(message: string, rowErrors: Record<number, string>) {
    super(message);
    this.name = 'DealerAccessGrantError';
    this.rowErrors = rowErrors;
  }
}

function rowErrorsFrom(body: unknown): Record<number, string> {
  const b = body as { rows?: unknown; details?: { rows?: unknown } } | null;
  const rows = b?.details?.rows ?? b?.rows;
  const out: Record<number, string> = {};
  if (Array.isArray(rows)) {
    for (const r of rows as { index?: unknown; error?: unknown }[]) {
      if (typeof r?.index === 'number' && typeof r?.error === 'string') out[r.index] = r.error;
    }
  }
  return out;
}

export async function getAccounts(company: string): Promise<DealerAccessAccount[]> {
  const qs = new URLSearchParams({ company });
  const response = await apiFetch(`${BASE}/accounts?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load your accounts'));
  return response.json();
}

export async function getPeople(params: DealerAccessPeopleParams): Promise<DealerAccessPage> {
  const qs = buildDataGridParams(
    { pageIndex: params.pageIndex, pageSize: params.pageSize, searchQuery: params.searchQuery },
    { company: params.companies, access: params.access },
  );
  const response = await apiFetch(`${BASE}/people?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load people'));
  return response.json();
}

export async function grant(body: DealerAccessGrantBody): Promise<DealerAccessGrantResult> {
  const response = await apiFetch(`${BASE}/grant`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // The body is read from a clone so `extractApiError` still gets an unread one.
    const clone = response.clone();
    const message = await extractApiError(response, 'Failed to give access');
    const rowErrors = await clone.json().then(rowErrorsFrom, () => ({}));
    throw new DealerAccessGrantError(message, rowErrors);
  }
  return response.json();
}

export async function updatePerson(contactId: string, body: DealerAccessUpdateBody): Promise<void> {
  const response = await apiFetch(`${BASE}/people/${contactId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update access'));
}
