/**
 * Round 5, REV-minor8 (RED): the Columns step takes its field names from the API.
 *
 * Assumed (the coder matches these):
 *   `ColumnsStep` (named export) from './ColumnsStep', props: { run: ProjectImportRun }.
 *   The run detail carries `field_labels` ({field key: plain label}); the step shows those
 *   labels and keeps no copy of the field list. An unknown label proves the source.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/hooks/usePermissions', () => {
  const set = new Set(['projects.import.view', 'projects.import.run']);
  return {
    usePermissions: () => ({ permissions: [...set], permissionSet: set, isLoading: false,
      isError: false, isFetching: false, error: null, refetch: () => {} }),
    useHasPermission: (slug: string) => set.has(slug),
    useHasAnyPermission: (slugs: string[]) => slugs.some((s) => set.has(s)),
    PERMISSIONS_QUERY_KEY: ['my-permissions'],
  };
});
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/import/run-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ data: [], items: [], total: 0 }),
  })),
}));

const service = vi.hoisted(() => ({ saveColumns: vi.fn(), getRun: vi.fn() }));
vi.mock('../../../_shared/services/projectImportService', () => service);

import { ColumnsStep } from './ColumnsStep';

const FIELDS = [
  'ps_number', 'salesperson', 'customer_service', 'customer', 'project_name', 'developer',
  'po_number', 'po_value', 'po_date', 'amended_date', 'schedule', 'delivery', 'outstanding',
  'so_number', 'remarks',
];
const field_labels = Object.fromEntries(FIELDS.map((f) => [f, `ZZ API ${f.replace(/_/g, ' ')}`]));

const run = {
  id: '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11',
  run_no: 'PIM-0004',
  filename: 'SO SUMMARY 2026.xlsx',
  status: 'draft',
  missing_columns: ['customer'],
  columns: {},
  field_labels,
  sheets: [
    {
      name: "JAN'26",
      name_trimmed: "JAN'26",
      has_ps_heading: true,
      row_count: 2,
      ticked: true,
      columns: [
        { position: 1, header: 'RUNNING \nPS NUMBER', sample: 'PS26-0001', field: 'ps_number' },
        { position: 2, header: 'CUST NAME', sample: 'CUSTOMER 001 SDN BHD', field: null },
        { position: 3, header: 'PO \nNUMBER', sample: 'PO-1', field: 'po_number' },
      ],
    },
  ],
};

beforeEach(() => vi.clearAllMocks());

describe('ColumnsStep, round 5', () => {
  it('r5: field names come from the run field_labels (REV-minor8)', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <ColumnsStep run={run as never} />
      </QueryClientProvider>
    );
    await screen.findAllByText(/CUST NAME/);
    const text = container.textContent ?? '';
    expect(text).toContain('ZZ API ps number');
    expect(text).toContain('ZZ API po number');
  });
});
