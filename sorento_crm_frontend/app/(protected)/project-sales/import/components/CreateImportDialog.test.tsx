/**
 * Round 6, D9 (RED): the project import dialogs carry a description, so Radix logs no
 * "Missing `Description` or `aria-describedby={undefined}` for {DialogContent}" warning.
 *
 * Assumed: `CreateImportDialog({ open, onOpenChange })` from './CreateImportDialog' and
 * `LineChoiceDialog({ open, kind, action, title, onCancel, onSave })` from
 * '../[runId]/components/LineChoiceDialog'.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/import',
  useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn() }),
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
const service = vi.hoisted(() => ({ createRun: vi.fn(), saveColumns: vi.fn(), getRun: vi.fn() }));
vi.mock('../../_shared/services/projectImportService', () => service);

import { LineChoiceDialog } from '../[runId]/components/LineChoiceDialog';
import { CreateImportDialog } from './CreateImportDialog';

const DESCRIPTION_WARNING = /Missing `Description`|aria-describedby=\{undefined\}/;
let warn: ReturnType<typeof vi.spyOn>;
let error: ReturnType<typeof vi.spyOn>;

function logged(): string[] {
  return [...warn.mock.calls, ...error.mock.calls].map((args) => args.map(String).join(' '));
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  error = vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => {
  warn.mockRestore();
  error.mockRestore();
});

describe('project import dialogs, round 6', () => {
  it('r6: D9 the Create dialog logs no missing-description warning', async () => {
    render(wrap(<CreateImportDialog open onOpenChange={() => {}} />));
    await screen.findByRole('dialog');
    expect(logged().filter((m) => DESCRIPTION_WARNING.test(m))).toEqual([]);
  });

  it('r6: D9 the Link dialog logs no missing-description warning', async () => {
    render(wrap(
      <LineChoiceDialog open kind="customer" action="link" title="Link customer"
        onCancel={() => {}} onSave={() => {}} />
    ));
    await screen.findByRole('dialog');
    expect(logged().filter((m) => DESCRIPTION_WARNING.test(m))).toEqual([]);
  });
});

describe('CreateImportDialog, round 9 (AC-PI-44)', () => {
  const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';
  const probeRun = {
    id: RUN_ID,
    run_no: 'PIM-0009',
    filename: 'SO SUMMARY 2026.xlsx',
    status: 'draft',
    missing_columns: [],
    columns: { ps_number: 'RUNNING \nPS NUMBER' },
    sheets: [
      { name: "JAN'26", name_trimmed: "JAN'26", has_ps_heading: true, row_count: 170, ticked: true, columns: [] },
      { name: "FEB'26", name_trimmed: "FEB'26", has_ps_heading: true, row_count: 128, ticked: true, columns: [] },
      { name: 'SUMMARY JAN-JUN', name_trimmed: 'SUMMARY JAN-JUN', has_ps_heading: false, row_count: 0, ticked: false, columns: [] },
      { name: "AUG'26", name_trimmed: "AUG'26", has_ps_heading: true, row_count: 194, ticked: true, columns: [] },
    ],
  };

  it('r9: lists each sheet with its count, ticks the monthly ones, and Next saves the ticks', async () => {
    const user = userEvent.setup();
    service.createRun.mockResolvedValue(probeRun);
    service.saveColumns.mockResolvedValue({});
    render(wrap(<CreateImportDialog open onOpenChange={() => {}} />));
    const dialog = await screen.findByRole('dialog');
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File([new Uint8Array([80, 75, 3, 4])], 'SO SUMMARY 2026.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }));
    const upload = within(dialog).queryByRole('button', { name: /^Upload$/ });
    if (upload) await user.click(upload);

    expect(await within(dialog).findByText(/170 rows/)).toBeInTheDocument();
    expect(within(dialog).getByText(/194 rows/)).toBeInTheDocument();
    expect(within(dialog).getByText(/No PS numbers/)).toBeInTheDocument();
    const box = (name: string) => within(dialog).getByRole('checkbox', { name: new RegExp(name) });
    expect(box("JAN'26")).toBeChecked();
    expect(box("AUG'26")).toBeChecked();
    expect(box('SUMMARY JAN-JUN')).not.toBeChecked();

    await user.click(box("FEB'26"));
    await user.click(within(dialog).getByRole('button', { name: /^Next$/ }));

    await waitFor(() => expect(service.saveColumns).toHaveBeenCalledTimes(1));
    const [runId, body] = service.saveColumns.mock.calls[0];
    expect(runId).toBe(RUN_ID);
    expect(body.sheets).toEqual(["JAN'26", "AUG'26"]);
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    expect(String(nav.push.mock.calls[0][0])).toContain(`/project-sales/import/${RUN_ID}`);
  });
});
