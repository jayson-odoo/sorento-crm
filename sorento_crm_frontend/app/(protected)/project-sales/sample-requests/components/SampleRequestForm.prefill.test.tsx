/**
 * SAMPLE-FROM-QUOTE on the staff form (owner Q6 a: staff pre-fill too; UAC SFQ-20..24,
 * documentation/plans/project-sales/sample-from-quote-29oct-acceptance-criteria.md).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

vi.mock('@/hooks/useRequestScope', () => ({
  useRequestScope: () => ({ limited: false, isLoading: false }),
}));

const mut = vi.hoisted(() => ({
  createAsync: vi.fn(),
  updateAsync: vi.fn(),
  submitAsync: vi.fn(),
  existing: { data: undefined as unknown, isLoading: false },
}));

vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return {
    ...actual,
    useSampleRequestMutations: () => ({
      create: { mutateAsync: mut.createAsync, isPending: false },
      update: { mutateAsync: mut.updateAsync, isPending: false },
      submit: { mutateAsync: mut.submitAsync, isPending: false },
    }),
    useSampleRequestQuery: () => mut.existing,
    useSampleRequestSwitches: () => ({ data: { requireProject: false } }),
  };
});

vi.mock('../services/sampleRequestService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/sampleRequestService')>();
  return {
    ...actual,
    searchSampleRequestProducts: vi.fn(async () => []),
    getSampleRequestQuotationPrefill: vi.fn(),
  };
});

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    getProject: vi.fn(async () => ({ id: 'proj-1', project_code: 'PRJ-1', title: 'Tower' })),
    listProjects: vi.fn(async () => ({ data: [] })),
  };
});

vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);

import {
  getSampleRequestQuotationPrefill,
  searchSampleRequestProducts,
} from '../services/sampleRequestService';
import SampleRequestForm from './SampleRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const PREFILL = {
  documents: [
    { id: 'doc-1', document_no: 'Q-0001', issue_id: null, issue_no: null, label: 'Q-0001 (not issued)' },
  ],
  document_id: 'doc-1',
  issue_id: null,
  lines: [
    { product_id: 'p-1', product_code: 'BASIN-1', product_name: 'Basin', brand_name: null },
    { product_id: 'p-2', product_code: 'TAP-2', product_name: 'Tap', brand_name: null },
  ],
  skipped: [{ reason: 'inactive', description: 'OLD-9' }],
};

function renderForm(props: { requestId?: string; projectId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestForm {...props} />
    </QueryClientProvider>,
  );
}

const rows = () =>
  Array.from(document.querySelectorAll<HTMLElement>('[data-testid="sample-request-line"]'));
const rowText = (r: HTMLElement) =>
  `${r.textContent} ${Array.from(r.querySelectorAll('input')).map((i) => (i as HTMLInputElement).value).join(' ')}`;

beforeEach(() => {
  vi.clearAllMocks();
  mut.existing = { data: undefined, isLoading: false };
  mut.createAsync.mockResolvedValue({ id: 'sr-new' });
  asMock(getSampleRequestQuotationPrefill).mockResolvedValue(PREFILL);
});

describe('SFQ-20 the staff form starts from the project quotation', () => {
  it('a project from the stage action fills the rows', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(getSampleRequestQuotationPrefill).toHaveBeenCalledWith('proj-1', undefined);
    expect(rowText(rows()[0])).toContain('BASIN-1');
    expect(rowText(rows()[1])).toContain('TAP-2');
  });

  it('saves the source quotation with the draft', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(mut.createAsync).toHaveBeenCalled());
    expect(mut.createAsync.mock.calls[0][0]).toMatchObject({
      quotation_document_id: 'doc-1',
      quotation_issue_id: null,
    });
  });

  it('names the inactive product it left out', async () => {
    renderForm({ projectId: 'proj-1' });
    expect(
      await screen.findByText('1 quotation line was not added: 1 product is inactive.'),
    ).toBeTruthy();
  });

  it('each pre-filled row has Remove line', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(within(rows()[1]).getByRole('button', { name: 'Remove line' }));
    expect(rows()).toHaveLength(1);
  });
});

describe('SFQ-21 editing a draft never pre-fills', () => {
  it('does not ask for the quotation', async () => {
    mut.existing = {
      data: {
        id: 'sr-1',
        request_no: 'SR-000001',
        status: 'draft',
        status_label: 'Draft',
        project_id: 'proj-1',
        project_code: 'PRJ-1',
        project_name: 'Tower',
        lines: [],
      },
      isLoading: false,
    };
    renderForm({ requestId: 'sr-1' });
    await new Promise((r) => setTimeout(r, 30));
    expect(getSampleRequestQuotationPrefill).not.toHaveBeenCalled();
  });
});

describe('SFQ-27 owner hand test: Add row offers only the quotation products', () => {
  it('searches with the source quotation once the request comes from one', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: /^\+?\s*add row$/i }));
    const row = rows()[2];
    const box = within(row).getByRole('combobox', { name: /item code/i });
    if (box.tagName === 'INPUT') {
      fireEvent.focus(box);
      fireEvent.change(box, { target: { value: 'basin' } });
    } else {
      fireEvent.click(box);
      fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'basin' } });
    }
    await waitFor(() =>
      expect(searchSampleRequestProducts).toHaveBeenCalledWith('basin', {
        quotation_document_id: 'doc-1',
        quotation_issue_id: null,
      }),
    );
  });
});

