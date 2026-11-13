/**
 * Round 6, D5 (RED): the Results view reads in plain words.
 *
 * Assumed: `ResultsView` (named export) from './ResultsView', props { run }. The breakdown
 * shows the API's labels and never a raw reason code; once imported, the tiles read in the
 * past tense ("Created", never "Will create").
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
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
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
const service = vi.hoisted(() => ({ listRows: vi.fn(), getLinesSummary: vi.fn(), listLines: vi.fn() }));
vi.mock('../../../_shared/services/projectImportService', () => service);
vi.mock('./ValuesStep', () => ({ ValuesStep: () => null, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));

import { ResultsView } from './ResultsView';

const LABELS: Record<string, string> = {
  project_and_po_created: 'Project and PO created',
  po_added: 'PO added to a project',
  customer_unmapped: 'Customer not linked yet',
};

const run = {
  id: '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11',
  run_no: 'PIM-0007',
  filename: 'SO SUMMARY 2026.xlsx',
  status: 'imported',
  missing_columns: [],
  sheets: [],
  columns: {},
  preview_counts: { created: 3, needs_review: 1 },
  preview_codes: { project_and_po_created: 1, po_added: 2, customer_unmapped: 1 },
  result_counts: { created: 3, needs_review: 1 },
  result_codes: { project_and_po_created: 1, po_added: 2, customer_unmapped: 1 },
  code_labels: LABELS,
  result: {
    message: 'Imported',
    counts: { total: 4, processed: 4, successful: 3, failed: 0, skipped: 1 },
    breakdown: {
      successful: [
        { code: 'project_and_po_created', label: LABELS.project_and_po_created, count: 1 },
        { code: 'po_added', label: LABELS.po_added, count: 2 },
      ],
      skipped: [{ code: 'customer_unmapped', label: LABELS.customer_unmapped, count: 1 }],
      failed: [],
    },
  },
  imported_at: '2026-11-12T10:00:00',
  sheet_errors: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  service.listRows.mockResolvedValue({ data: [], total: 0 });
});

function renderResults() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ResultsView run={run as never} />
    </QueryClientProvider>
  );
}

describe('ResultsView, round 6', () => {
  it('r6: D5 the breakdown shows plain labels and no raw reason code', async () => {
    const { container } = renderResults();
    expect((await screen.findAllByText(LABELS.po_added)).length).toBeGreaterThan(0);
    const text = container.textContent ?? '';
    for (const code of Object.keys(LABELS)) {
      expect(text, code).not.toContain(code);
    }
  });

  it('r6: D5 the tiles read Created once imported, never Will create', async () => {
    const { container } = renderResults();
    await screen.findAllByText(LABELS.po_added);
    const text = container.textContent ?? '';
    expect(text).not.toMatch(/Will create/i);
    const tile = screen
      .getAllByText(/^Created$/)
      .map((el) => el.parentElement)
      .find((p) => (p?.textContent ?? '').includes('3'));
    expect(tile).toBeTruthy();
  });
});
