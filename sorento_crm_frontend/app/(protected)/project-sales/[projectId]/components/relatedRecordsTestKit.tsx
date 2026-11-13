/**
 * Shared fixtures for the PROJECT-RELATED-RECORDS panel tests (RelatedRecordsPanel.test.tsx,
 * relatedRecordTypes.test.ts). Fake values only.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { Project } from '../../_shared/types/project.types';

export type FakeRow = {
  kind: string;
  id: string;
  number: string | null;
  status: string | null;
  approval_status: string | null;
  date: string | null;
  raised_by: string | null;
  subject: string | null;
  value: string | number | null;
};

export const ROWS: FakeRow[] = [
  {
    kind: 'sponsorship_form',
    id: 'sf-1',
    number: 'SF-ZZT-0001',
    status: 'submitted',
    approval_status: 'pending',
    date: '2026-04-10',
    raised_by: 'Cara Requester',
    subject: 'Launch event',
    value: '1200.00',
  },
  {
    kind: 'purchase_request',
    id: 'pr-1',
    number: 'PR-ZZT-0001',
    status: 'processed_by_cs',
    approval_status: 'approved',
    date: '2026-03-10',
    raised_by: 'Ben Requester',
    subject: 'Tower lobby',
    value: '5000.00',
  },
  {
    kind: 'complaint',
    id: 'cx-1',
    number: 'CX-ZZT-0001',
    status: 'submitted',
    approval_status: null,
    date: '2026-02-05',
    raised_by: 'Amy Salesperson',
    subject: 'Cracked tile',
    value: null,
  },
  {
    kind: 'stock_inquiry',
    id: 'si-1',
    number: 'SI-ZZT-0001',
    status: 'responded',
    approval_status: null,
    date: '2026-01-09',
    raised_by: 'Zack Salesperson',
    subject: 'Basin mixer',
    value: null,
  },
  {
    kind: 'new_product_application',
    id: 'npa-1',
    number: 'NPA-990001',
    status: 'completed',
    approval_status: null,
    date: '2026-05-10',
    raised_by: 'Dina Applicant',
    subject: 'New sink',
    value: '300.00',
  },
];

export const TYPES = [
  { kind: 'stock_inquiry', label: 'Stock Inquiry' },
  { kind: 'complaint', label: 'Complaint' },
  { kind: 'purchase_request', label: 'Purchase request' },
  { kind: 'sponsorship_form', label: 'Sponsorship form' },
  { kind: 'new_product_application', label: 'New product application' },
];

export function response(
  rows: FakeRow[] = ROWS,
  types: { kind: string; label: string }[] = TYPES,
) {
  const type_counts: Record<string, number> = {};
  for (const row of rows) type_counts[row.kind] = (type_counts[row.kind] ?? 0) + 1;
  return {
    data: rows,
    pagination: { total: rows.length, page: 1, limit: 25 },
    empty: rows.length === 0,
    type_counts,
    types,
  };
}

export function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-ZZT-0001',
    title: 'Zzt Harbour View',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  } as Project;
}

export function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
