/**
 * Round 5 follow-up, REV-M2 (owner standing rule: "the page and its filters are in the
 * address bar"): the runs list WRITES its search, filters and sort to the URL as they change,
 * so a reload or Back keeps them. Read on entry is covered in ProjectImportListClient.test.tsx.
 *
 * Shape: the query string is the one a row click carries to the run (`page`, `limit`, `sort`,
 * `dir`, `query`, `status`, `uploaded_by`), written with `history.replaceState`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
  usePathname: () => '/project-sales/import',
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
  apiFetch: vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ data: [], total: 0 }) })),
}));
type MultiProps = {
  value: string[];
  onChange: (next: string[]) => void;
  options?: { value: string; label: string }[];
  placeholder?: string;
  'aria-label'?: string;
};
vi.mock('@/components/common/SearchableMultiSelect', () => {
  const Stand = (p: MultiProps) => (
    // A test stand-in for SearchableMultiSelect, driven with user.selectOptions.
    // eslint-disable-next-line no-restricted-syntax
    <select
      multiple
      aria-label={p['aria-label'] ?? p.placeholder}
      value={p.value ?? []}
      onChange={(e) => p.onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}
    >
      {(p.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return { SearchableMultiSelect: Stand, default: Stand };
});

const service = vi.hoisted(() => ({ listRuns: vi.fn() }));
vi.mock('../../_shared/services/projectImportService', () => service);
vi.mock('./CreateImportDialog', () => ({ CreateImportDialog: () => null, default: () => null }));

import { ProjectImportListClient } from './ProjectImportListClient';

const runs = [
  {
    id: '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11',
    run_no: 'PIM-0001',
    filename: 'SO SUMMARY 2026.xlsx',
    status: 'previewed',
    uploaded_by: 'ZZT Importer',
    uploaded_by_id: '7d2a9f4e-1c3b-4e8d-a5f6-2b9c8d7e6f50',
    uploaded_at: '2026-11-12T09:30:00',
    rows: 10,
    created: 0,
    skipped: 3,
    to_review: 7,
    imported_at: null,
  },
];

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectImportListClient />
    </QueryClientProvider>
  );
}

function urlParams() {
  return new URLSearchParams(window.location.search);
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/project-sales/import');
  service.listRuns.mockResolvedValue({ data: runs, total: 1 });
});

describe('ProjectImportListClient, address bar', () => {
  it('r5: a search typed in the box is written to the URL (REV-M2)', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('PIM-0001');

    await user.type(screen.getByRole('textbox', { name: /Search imports/i }), 'SUMMARY');

    await waitFor(() => expect(urlParams().get('query')).toBe('SUMMARY'), { timeout: 3000 });
    expect(window.location.pathname).toBe('/project-sales/import');
  });

  it('r5: a status filter is written to the URL (REV-M2)', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('PIM-0001');

    await user.click(screen.getByRole('button', { name: /^Filters/ }));
    await user.selectOptions(await screen.findByLabelText(/^Status$/), ['imported', 'reverted']);

    await waitFor(() =>
      expect((urlParams().get('status') ?? '').split(',').sort()).toEqual(['imported', 'reverted'])
    );
  });

  it('r5: nothing is written before the person changes anything', async () => {
    renderList();
    await screen.findByText('PIM-0001');

    expect(window.location.search).toBe('');
  });
});
