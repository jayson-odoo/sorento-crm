/**
 * AC-PI-47 (RED): the Preview step.
 *
 * Assumed (the coder matches these):
 *   `PreviewStep` (named export) from './PreviewStep', props:
 *     run: ProjectImportRun                      (carries preview_counts)
 *     onOpenLine: (kind: 'customer' | 'project' | 'developer' | 'person') => void
 *   Tiles from `run.preview_counts`: Will create (created), Already imported (unchanged),
 *   Skipped, Needs review (needs_review), Errors (error).
 *   Rows from `listRows(runId, grid, { outcome, code, sheet })` -> { data, total }.
 *   Outcome / Reason / Sheet are `SearchableMultiSelect` filters; the Outcome one is labelled
 *   "Outcome" (aria-label or placeholder) and its option values are the outcome keys.
 *   Import is the ONLY primary (variant="primary") button on the step.
 *   A needs_review row click calls onOpenLine with the kind of its FIRST blocking code:
 *   customer_* -> customer, project_* -> project, developer_* -> developer.
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

const service = vi.hoisted(() => ({
  listRows: vi.fn(),
  previewRun: vi.fn(),
  startImport: vi.fn(),
  getRun: vi.fn(),
}));
vi.mock('../../../_shared/services/projectImportService', () => service);

import { PreviewStep } from './PreviewStep';

const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';
const run = {
  id: RUN_ID,
  run_no: 'PIM-0002',
  filename: 'SO SUMMARY 2026.xlsx',
  status: 'previewed',
  missing_columns: [],
  preview_counts: { created: 903, updated: 0, unchanged: 7, skipped: 365, needs_review: 14, error: 2 },
  preview_codes: { customer_unmapped: 10, project_unmapped: 4 },
};

function reportRow(ps: string, outcome: string, codes: string[], n: number) {
  return {
    sheet: "JAN'26",
    row_number: n,
    ps_number: ps,
    customer: 'CUSTOMER 001 SDN BHD',
    project: 'PROJECT 001 SAMPLE NAME',
    po_number: `PO-${n}`,
    po_date: '2026-01-05',
    outcome,
    codes,
    message: null,
  };
}

const rows = [
  reportRow('PS26-0001', 'needs_review', ['customer_unmapped', 'so_not_synced'], 2),
  reportRow('PS26-0002', 'needs_review', ['project_unmapped'], 3),
  reportRow('PS26-0003', 'needs_review', ['developer_conflict'], 4),
  reportRow('PS26-0004', 'needs_review', ['customer_unmapped', 'project_unmapped'], 5),
  reportRow('PS26-0005', 'created', ['project_and_po_created'], 6),
];

const onOpenLine = vi.fn();

function renderStep() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PreviewStep run={run as never} onOpenLine={onOpenLine} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  service.listRows.mockResolvedValue({ data: rows, total: rows.length });
  service.startImport.mockResolvedValue({ job_id: 'job-1' });
});

describe('PreviewStep', () => {
  it('shows the outcome tiles from preview_counts', async () => {
    renderStep();
    await screen.findByText('PS26-0001');
    for (const [label, n] of [
      ['Will create', '903'],
      ['Already imported', '7'],
      ['Skipped', '365'],
      ['Needs review', '14'],
      ['Errors', '2'],
    ]) {
      const labels = screen.getAllByText(new RegExp(`^${label}$`, 'i'));
      const tile = labels
        .map((el) => el.parentElement)
        .find((p) => (p?.textContent ?? '').includes(n));
      expect(tile, `${label} tile shows ${n}`).toBeTruthy();
    }
  });

  it('has exactly one primary button, and it reads Import', async () => {
    const { container } = renderStep();
    await screen.findByText('PS26-0001');
    const primaries = Array.from(container.querySelectorAll('button')).filter((b) =>
      /(^|\s)bg-primary(\s|$)/.test(b.className)
    );
    expect(primaries).toHaveLength(1);
    expect(primaries[0].textContent?.trim()).toBe('Import');
  });

  it('choosing two outcomes asks listRows for both', async () => {
    const user = userEvent.setup();
    renderStep();
    await screen.findByText('PS26-0001');

    await user.selectOptions(screen.getByLabelText(/Outcome/i), ['needs_review', 'error']);

    await waitFor(() => {
      const last = service.listRows.mock.calls.at(-1)!;
      expect(last[0]).toBe(RUN_ID);
      expect([...(last[2]?.outcome ?? [])].sort()).toEqual(['error', 'needs_review']);
    });
  });

  it.each([
    ['PS26-0001', 'customer'],
    ['PS26-0002', 'project'],
    ['PS26-0003', 'developer'],
    ['PS26-0004', 'customer'],
  ])('clicking needs-review row %s opens the %s line', async (ps, kind) => {
    const user = userEvent.setup();
    renderStep();
    await user.click(await screen.findByText(ps));
    await waitFor(() => expect(onOpenLine).toHaveBeenCalledTimes(1));
    expect(onOpenLine.mock.calls[0][0]).toBe(kind);
  });

  it('a row that needs nothing does not open a line', async () => {
    const user = userEvent.setup();
    renderStep();
    await user.click(await screen.findByText('PS26-0005'));
    expect(onOpenLine).not.toHaveBeenCalled();
  });
});
