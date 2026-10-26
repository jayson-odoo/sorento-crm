/**
 * Lane BULK-CONTACT-ACCESS, UAC U11, U13-U15, U20: Import access sheet dialog.
 * Upload -> Preview -> Result, as mock v1. Red until the dialog, hook and service exist.
 * The feature service is mocked: `previewAccessSheet(file)` and `applyAccessSheet(file, confirmed)`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/components/common/FileDropzone', () => ({
  FileDropzone: (props: { onFilesChange: (files: File[]) => void }) => (
    <input
      aria-label="Access sheet file"
      type="file"
      onChange={(e) => props.onFilesChange(Array.from(e.target.files ?? []))}
    />
  ),
}));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toastMock }));

const svc = vi.hoisted(() => ({ previewAccessSheet: vi.fn(), applyAccessSheet: vi.fn() }));
vi.mock('@/services/contactAccessSheetService', () => svc);

import AccessSheetImportDialog from './AccessSheetImportDialog';

const acct = (id: string, over: Record<string, unknown> = {}) => ({
  customer_id: id, customer_code: `300-${id}`, customer_name: `ACCOUNT ${id}`, company_code: 'SRT', is_active: true,
  sales_agent: 'AG ONE', sheet_agent: 'AG ONE', match: 'exact', score: 1, proposed: true, ...over,
});
const person = (name: string, over: Record<string, unknown> = {}) => ({
  line: 2, name, phone: '+60100000001', in_crm: true, contact_id: `id-${name}`, role: 'owner', companies: ['SRT'],
  template: 'SRT owner', status: 'applied', skip_reason: null, changes: [], warnings: [], not_applied: [], ...over,
});

const PREVIEW = {
  dry_run: true,
  counts: {
    rows: 3, row_errors: 0, contacts_found: 3, not_in_crm: 0, ambiguous: 0, already_configured: 0,
    blocks: 2, blocks_exact: 1, blocks_pick: 1, blocks_none: 0, applied: 3, no_change: 0, skipped: 0,
  },
  errors: [],
  blocks: [
    {
      key: 'alpha bath', dealer: 'ALPHA BATH SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'exact', warnings: [],
      accounts: [acct('a1'), acct('a2')], contacts: [person('Ann'), person('Ari')],
    },
    {
      key: 'beta tiles', dealer: 'BETA TILES SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'pick', warnings: [],
      accounts: [acct('b1', { match: 'candidate', score: 0.9, proposed: false })], contacts: [person('Bob')],
    },
  ],
};

const RESULT = {
  ...PREVIEW,
  dry_run: false,
  counts: { ...PREVIEW.counts, applied: 2, no_change: 0, skipped: 1 },
  blocks: [
    { ...PREVIEW.blocks[0] },
    { ...PREVIEW.blocks[1], contacts: [person('Bob', { status: 'skipped', skip_reason: 'dealer_not_confirmed' })] },
  ],
};

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <AccessSheetImportDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

const file = new File(['First Name,Phone Number,Tags\n'], 'sheet.csv', { type: 'text/csv' });

function pickFile() {
  fireEvent.change(screen.getByLabelText('Access sheet file'), { target: { files: [file] } });
}

async function toPreview() {
  pickFile();
  fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
  await screen.findAllByText('ALPHA BATH SDN BHD');
}

beforeEach(() => {
  svc.previewAccessSheet.mockResolvedValue(PREVIEW);
  svc.applyAccessSheet.mockResolvedValue(RESULT);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AccessSheetImportDialog', () => {
  it('upload step: Preview stays off until a file is chosen, then sends the file to the dry run', async () => {
    renderDialog();
    expect((screen.getByRole('button', { name: /^Preview/ }) as HTMLButtonElement).disabled).toBe(true);
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await waitFor(() => expect(svc.previewAccessSheet).toHaveBeenCalledWith(file));
    expect(svc.applyAccessSheet).not.toHaveBeenCalled();
  });

  it('U13: preview renders each dealer block with its status and the sheet counts', async () => {
    renderDialog();
    await toPreview();
    expect(screen.getAllByText('BETA TILES SDN BHD').length).toBeGreaterThan(0);
    expect(screen.getByText(/exact/i)).toBeInTheDocument();
    expect(screen.getByText(/needs a pick/i)).toBeInTheDocument();
    expect(screen.getByText(/3 contacts in sheet/i)).toBeInTheDocument();
    expect(screen.getByText(/3 found in CRM/i)).toBeInTheDocument();
  });

  it('U11: Confirm all exact then Apply posts the file and the exact block ticked ids only', async () => {
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    expect(svc.applyAccessSheet).toHaveBeenCalledWith(file, { 'alpha bath': ['a1', 'a2'] });
  });

  it('U15: the result step shows applied and skipped counts and offers Download result', async () => {
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    expect(await screen.findByText(/Applied 2 contacts/i)).toBeInTheDocument();
    expect(screen.getByText(/Skipped 1/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download result/i })).toBeInTheDocument();
  });

  it('a refused file shows the error and stays on the upload step', async () => {
    svc.previewAccessSheet.mockRejectedValueOnce(new Error('The file has no Tags column.'));
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /^Preview/ })).toBeInTheDocument();
    expect(screen.queryByText('ALPHA BATH SDN BHD')).toBeNull();
  });
});
