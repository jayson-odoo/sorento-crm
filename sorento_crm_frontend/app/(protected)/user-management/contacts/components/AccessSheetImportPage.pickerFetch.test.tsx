/**
 * ACCESS-SHEET-FIXES fix 2 (owner 27 Oct: "the search customer is hella glitchy, the searching
 * keeps running"). The REAL SearchableMultiSelect re-runs its search whenever `fetchOptions`
 * changes identity, so the pick card's customer search must hand it a stable function: opening
 * the picker is one request, not a loop. AccessSheetImportPage.test.tsx mocks the multi-select
 * (it fetches once on mount), which is why it could not see this.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
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
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
const svc = vi.hoisted(() => ({ previewAccessSheet: vi.fn(), applyAccessSheet: vi.fn() }));
vi.mock('@/services/contactAccessSheetService', () => svc);
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  usePathname: () => '/user-management/contacts/access-sheet',
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: (props: { title: string }) => <h1>{props.title}</h1>,
}));
const customerSvc = vi.hoisted(() => ({ searchCustomersSelect: vi.fn() }));
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => customerSvc);

import AccessSheetImportPage from './AccessSheetImportPage';

const PREVIEW = {
  dry_run: true,
  counts: {
    rows: 1, row_errors: 0, contacts_found: 1, not_in_crm: 0, ambiguous: 0, already_configured: 0,
    blocks: 1, blocks_exact: 0, blocks_pick: 1, blocks_none: 0, applied: 1, no_change: 0, skipped: 0,
  },
  errors: [],
  blocks: [
    {
      key: 'beta tiles', dealer: 'BETA TILES SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'pick', warnings: [],
      accounts: [],
      contacts: [
        {
          line: 2, name: 'Bob', phone: '+60100000001', in_crm: true, contact_id: 'id-bob', role: 'owner',
          companies: ['SRT'], template: 'SRT owner', status: 'applied', skip_reason: null, changes: [],
          warnings: [], not_applied: [], holds_more_items: [], outside_links: [],
        },
      ],
    },
  ],
};

beforeEach(() => {
  customerSvc.searchCustomersSelect.mockResolvedValue([
    { value: 'c1', label: 'Mocha · 300-Y055 - EXTRA TRADING', description: '' },
  ]);
  svc.previewAccessSheet.mockResolvedValue(PREVIEW);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AccessSheetImportPage customer search', () => {
  it('opening the pick card search fetches once and shows the results, not a spinner loop', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AccessSheetImportPage />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText('Access sheet file'), {
      target: { files: [new File(['x'], 'sheet.csv', { type: 'text/csv' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await screen.findAllByText('BETA TILES SDN BHD');

    fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);
    expect(await screen.findByText(/300-Y055 - EXTRA TRADING/)).toBeTruthy();
    // Let any re-render driven re-search run its course.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    expect(customerSvc.searchCustomersSelect).toHaveBeenCalledTimes(1);
    expect(customerSvc.searchCustomersSelect.mock.calls[0][2]).toEqual({ companyScope: 'grants' });
    expect(screen.getByText(/300-Y055 - EXTRA TRADING/)).toBeTruthy();
  });
});
