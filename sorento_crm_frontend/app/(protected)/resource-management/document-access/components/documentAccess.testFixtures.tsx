/**
 * Shared fixtures + harness for the Document Access tests (DAS-FE-2 .. 8). Not a test file.
 * Ids are real UUIDs on purpose: the DAS-FE-8 test asserts no rendered text matches one.
 */
import React from 'react';
import { render } from '@testing-library/react';
import type { DocumentAccessRow, PreviewContact, RowPreview, RowVerdict } from '../types/documentAccess.types';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

export const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export const TECH = '11111111-1111-4111-8111-111111111111';
export const DIRECT = '22222222-2222-4222-8222-222222222222';
export const EMPTY = '33333333-3333-4333-8333-333333333333';
export const ALPHA = '44444444-4444-4444-8444-444444444444';
export const CONTACT_A = '55555555-5555-4555-8555-555555555555';
export const CONTACT_E = '66666666-6666-4666-8666-666666666666';
export const COMPANY_1 = '77777777-7777-4777-8777-777777777777';

export const ACCESS_TYPES = [
  { code: 'dealer', name: 'Dealer' },
  { code: 'end_user', name: 'End User' },
  { code: 'mocha_dealer', name: 'Mocha Dealer' },
];

function row(over: Partial<DocumentAccessRow> & { id: string; type_name: string }): DocumentAccessRow {
  return {
    is_shared: false,
    is_direct_access: false,
    grant_count: 0,
    file_count: 0,
    readable_count: 0,
    ai_read_staff: false,
    ai_read_codes: [] as string[],
    reach: { dealer: 0, end_user: 0, mocha_dealer: 0 },
    preview: null,
    ...over,
  };
}

export const ROWS = [
  // Staff and Dealer ticked; Dealer reaches 2 of the 3 readable documents (amber 2/3).
  row({
    id: TECH, type_name: 'Technical Specifications', is_shared: true, file_count: 4, readable_count: 3,
    ai_read_staff: true, ai_read_codes: ['dealer'], reach: { dealer: 2, end_user: 3, mocha_dealer: 0 },
  }),
  row({
    id: DIRECT, type_name: 'Direct Access', is_direct_access: true, grant_count: 3, file_count: 15, readable_count: 15,
    reach: { dealer: 15, end_user: 15, mocha_dealer: 15 },
  }),
  row({ id: EMPTY, type_name: 'Empty Type' }),
  row({ id: ALPHA, type_name: 'Alpha Zero' }),
];

export function matrix(over: Record<string, unknown> = {}) {
  return { access_types: ACCESS_TYPES, contact: null, rows: ROWS, ...over };
}

export const CONTACT_BLOCK: PreviewContact = {
  id: CONTACT_A,
  name: 'CONTACT A',
  runs_as: 'contact',
  agent_on: false,
  access_types: ['end_user'],
  companies: [{ id: COMPANY_1, name: 'Sorento' }],
  blocked: null,
};

/** The matrix as seen by CONTACT A: one row of each flavour. */
export function matrixFor(contact: PreviewContact = CONTACT_BLOCK) {
  const pv = (over: Partial<RowPreview>): RowPreview => ({ verdict: 'reads', reads: 0, total: 0, no_shared_code: 0, other_company: 0, ...over });
  const previews: Record<string, RowPreview> = {
    [TECH]: pv({ verdict: 'not_ticked', total: 3 }),
    [DIRECT]: pv({ verdict: 'reads', reads: 5, total: 15, no_shared_code: 2, other_company: 8 }),
    [EMPTY]: pv({ verdict: 'no_documents' }),
    [ALPHA]: pv({ verdict: 'off' }),
  };
  const blocked: RowVerdict | null = contact.blocked;
  return matrix({
    contact,
    rows: ROWS.map((r) => ({ ...r, preview: blocked ? pv({ verdict: blocked, total: r.readable_count }) : previews[r.id] })),
  });
}

export const DOCS = {
  items: [
    { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', original_filename: 'Cabana Warranty.pdf', access_levels: ['dealer'], company_name: null, ai_read_status: 'done', verdict: null, can_edit_levels: true },
    { id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', original_filename: 'Tile Care.docx', access_levels: ['dealer', 'end_user'], company_name: 'Sorento', ai_read_status: 'queued', verdict: null, can_edit_levels: false },
  ],
  total: 2,
  page: 1,
  limit: 50,
};

export const VIEW = 'resource.attachment_types.view';
export const EDIT = 'resource.attachment_types.edit';
export const CONTACTS_VIEW = 'user_management.contacts.view';

export function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
