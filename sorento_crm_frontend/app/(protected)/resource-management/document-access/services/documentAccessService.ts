import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { getContacts } from '@/app/(protected)/user-management/contacts/[id]/services/contactService';
import type { DocumentAccessDocumentsPage, DocumentAccessMatrix } from '../types/documentAccess.types';

const BASE = '/api/v1/resource-management/document-access';

export async function getDocumentAccess({ contactId }: { contactId?: string } = {}): Promise<DocumentAccessMatrix> {
  const params = new URLSearchParams({ company_scope: 'grants' });
  if (contactId) params.set('contact_id', contactId);
  const response = await apiFetch(`${BASE}?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load document access'));
  return response.json();
}

export async function getDocumentAccessDocuments(
  typeId: string,
  { contactId, page, limit }: { contactId?: string; page: number; limit: number },
): Promise<DocumentAccessDocumentsPage> {
  const params = new URLSearchParams({ company_scope: 'grants', page: String(page), limit: String(limit) });
  if (contactId) params.set('contact_id', contactId);
  const response = await apiFetch(`${BASE}/${typeId}/documents?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load documents'));
  return response.json();
}

export async function searchPreviewContacts(query: string): Promise<{ id: string; name: string }[]> {
  const result = await getContacts({ pageIndex: 0, pageSize: 20, searchQuery: query });
  return result.data.map((c) => ({ id: String(c.id), name: c.name || 'Unnamed contact' }));
}
