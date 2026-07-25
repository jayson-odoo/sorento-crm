/**
 * ============================================================================
 * Companies admin + access management — feature service
 * ============================================================================
 * Layering: hooks (useCompanies*) → THIS service → lib/api-client → backend.
 * No component fetches directly.
 *
 * ── PHASE-1 / PHASE-2 SWAP ──────────────────────────────────────────────────
 * `USE_COMPANY_MOCKS` is the single flag toggling this feature between the
 * deterministic prototype store (`lib/companyMock.ts`) and the live backend.
 * Phase 1 = true (no backend). Phase 2 flips it to false; every mock branch
 * below already has its real `apiFetch` counterpart wired to the contract, so
 * the swap is one line + deleting the mock import.
 *
 * ── PHASE-2 BACKEND CONTRACT (System Management → Companies; superadmin-only
 *    per PLAN §16) ────────────────────────────────────────────────────────────
 *
 *  GET    /api/v1/system/companies?page&limit&sort&dir&query
 *    → { data: Company[], total: number }   (Company.user_count / contact_count
 *      are derived server-side for the admin list)
 *  GET    /api/v1/system/companies/{id}                 → Company
 *  POST   /api/v1/system/companies       body CompanyFormData → Company (201)
 *  PUT    /api/v1/system/companies/{id}  body CompanyFormData → Company
 *  DELETE /api/v1/system/companies/{id}                 → 204 (hard delete)
 *
 *  Access — user grants (prototypes user_companies):
 *  GET    /api/v1/system/companies/{id}/users           → CompanyUser[]
 *  POST   /api/v1/system/companies/{id}/users   {user_id} → CompanyUser[]
 *  DELETE /api/v1/system/companies/{id}/users/{user_id}   → CompanyUser[]
 *
 *  Access — contact membership (prototypes respond_contact_companies):
 *  GET    /api/v1/system/companies/{id}/contacts        → CompanyContact[]
 *  GET    /api/v1/system/companies/{id}/contacts/available?query → CompanyContact[]
 *  POST   /api/v1/system/companies/{id}/contacts {contact_id} → CompanyContact[]
 *  DELETE /api/v1/system/companies/{id}/contacts/{contact_id}  → CompanyContact[]
 *
 *  Active-company context (any authenticated user — not superadmin-gated):
 *  GET    /api/v1/system/companies/my-context
 *    → { companies: Company[], active_company_id: string|null, last_active_company_id: string|null }
 *  POST   /api/v1/system/companies/switch  {company_id}
 *    → { active_company_id: string, company: Company }   (persists last_active;
 *       token re-mint is the FE's job via NextAuth session.update())
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  Company,
  CompanyContact,
  CompanyFormData,
  CompanyUser,
  MyCompanyContext,
} from '../types/company.types';
import {
  mockAddCompanyContact,
  mockAddCompanyUser,
  mockAvailableContacts,
  mockCreateCompany,
  mockDeleteCompany,
  mockGetCompany,
  mockListCompanies,
  mockListCompanyContacts,
  mockListCompanyUsers,
  mockRemoveCompanyContact,
  mockRemoveCompanyUser,
  mockUpdateCompany,
} from '../lib/companyMock';

/** Phase-1 flag — true = deterministic mock store, false = live backend. */
export const USE_COMPANY_MOCKS = false;

const BASE = '/api/v1/system/companies';

// ── Company CRUD ─────────────────────────────────────────────────────────────

export async function getCompanies(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<Company>> {
  if (USE_COMPANY_MOCKS) {
    const data = mockListCompanies();
    return { data, empty: data.length === 0, pagination: { total: data.length, page: 1 } };
  }
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const res = await apiFetch(`${BASE}?${queryParams.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to fetch companies'));
  return res.json();
}

/** Lightweight active-company list for pickers (superadmin-only). */
export type CompanySelectOption = { id: string; name: string; code: string };

export async function getCompaniesSelect(): Promise<CompanySelectOption[]> {
  const res = await apiFetch(`${BASE}/select`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load companies'));
  return res.json();
}

export async function getCompany(id: string): Promise<Company> {
  if (USE_COMPANY_MOCKS) return mockGetCompany(id);
  const res = await apiFetch(`${BASE}/${id}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to fetch company'));
  return res.json();
}

export async function createCompany(data: CompanyFormData): Promise<Company> {
  if (USE_COMPANY_MOCKS) return mockCreateCompany(data);
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create company'));
  return res.json();
}

export async function updateCompany(id: string, data: CompanyFormData): Promise<Company> {
  if (USE_COMPANY_MOCKS) return mockUpdateCompany(id, data);
  const res = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update company'));
  return res.json();
}

export async function deleteCompany(id: string): Promise<void> {
  if (USE_COMPANY_MOCKS) {
    mockDeleteCompany(id);
    return;
  }
  const res = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete company'));
}

// ── User access grants ───────────────────────────────────────────────────────

export async function getCompanyUsers(companyId: string): Promise<CompanyUser[]> {
  if (USE_COMPANY_MOCKS) return mockListCompanyUsers(companyId);
  const res = await apiFetch(`${BASE}/${companyId}/users`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load assigned users'));
  return res.json();
}

export async function addCompanyUser(companyId: string, user: CompanyUser): Promise<CompanyUser[]> {
  if (USE_COMPANY_MOCKS) return mockAddCompanyUser(companyId, user);
  const res = await apiFetch(`${BASE}/${companyId}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: user.id }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to assign user'));
  return res.json();
}

export async function removeCompanyUser(companyId: string, userId: string): Promise<CompanyUser[]> {
  if (USE_COMPANY_MOCKS) return mockRemoveCompanyUser(companyId, userId);
  const res = await apiFetch(`${BASE}/${companyId}/users/${userId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove user'));
  return res.json();
}

// ── Contact membership ───────────────────────────────────────────────────────

export async function getCompanyContacts(companyId: string): Promise<CompanyContact[]> {
  if (USE_COMPANY_MOCKS) return mockListCompanyContacts(companyId);
  const res = await apiFetch(`${BASE}/${companyId}/contacts`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load tagged contacts'));
  return res.json();
}

export async function getAvailableContacts(
  companyId: string,
  query?: string,
): Promise<CompanyContact[]> {
  if (USE_COMPANY_MOCKS) return mockAvailableContacts(companyId);
  const sp = new URLSearchParams();
  if (query) sp.set('query', query);
  const suffix = sp.toString() ? `?${sp.toString()}` : '';
  const res = await apiFetch(`${BASE}/${companyId}/contacts/available${suffix}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load contacts'));
  return res.json();
}

export async function addCompanyContact(
  companyId: string,
  contactId: string,
): Promise<CompanyContact[]> {
  if (USE_COMPANY_MOCKS) return mockAddCompanyContact(companyId, contactId);
  const res = await apiFetch(`${BASE}/${companyId}/contacts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_id: contactId }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to tag contact'));
  return res.json();
}

export async function removeCompanyContact(
  companyId: string,
  contactId: string,
): Promise<CompanyContact[]> {
  if (USE_COMPANY_MOCKS) return mockRemoveCompanyContact(companyId, contactId);
  const res = await apiFetch(`${BASE}/${companyId}/contacts/${contactId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove contact'));
  return res.json();
}

// ── Active-company context (switcher) ─────────────────────────────────────────

/** Switchable companies + active/last-active for the current user. */
export async function getMyCompanyContext(): Promise<MyCompanyContext> {
  const res = await apiFetch(`${BASE}/my-context`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load company context'));
  return res.json();
}

/** Persist the active company server-side. Token re-mint is the caller's job. */
export async function switchCompany(companyId: string): Promise<{ active_company_id: string }> {
  const res = await apiFetch(`${BASE}/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_id: companyId }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to switch company'));
  return res.json();
}
