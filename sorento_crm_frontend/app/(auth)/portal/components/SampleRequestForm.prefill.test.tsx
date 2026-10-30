/**
 * SAMPLE-FROM-QUOTE on the shared portal form, which is also the CRM's My Requests form
 * (UAC SFQ-20..25, documentation/plans/project-sales/sample-from-quote-29oct-acceptance-criteria.md).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

vi.mock('../lib/sample-request-service', () => ({
  searchSampleRequestProducts: vi.fn(async () => []),
  lookupSampleRequestCustomers: vi.fn(async () => []),
  getSampleRequestQuotationPrefill: vi.fn(),
  createSampleRequest: vi.fn(),
  updateSampleRequest: vi.fn(),
  submitSampleRequest: vi.fn(),
  getSampleRequest: vi.fn(),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...actual,
    lookupDebtors: vi.fn(async () => []),
    lookupProjects: vi.fn(async () => []),
    fetchSubmissionNeighbours: vi.fn(async () => ({ prev: null, next: null })),
  };
});

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: () => null,
}));

import {
  createSampleRequest,
  getSampleRequest,
  getSampleRequestQuotationPrefill,
} from '../lib/sample-request-service';
import SampleRequestForm from './SampleRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const doc = (id: string, label: string, issue: string | null = null) => ({
  id,
  document_no: label,
  issue_id: issue,
  issue_no: issue ? 2 : null,
  label: issue ? `${label} (R2)` : `${label} (not issued)`,
});

const PREFILL = {
  documents: [doc('doc-1', 'Q-0001', 'iss-1')],
  document_id: 'doc-1',
  issue_id: 'iss-1',
  lines: [
    { product_id: 'p-1', product_code: 'BASIN-1', product_name: 'Basin', brand_name: null },
    { product_id: 'p-2', product_code: 'TAP-2', product_name: 'Tap', brand_name: null },
  ],
  skipped: [{ reason: 'no_product', description: 'Bespoke top' }],
};

function renderForm(props: { requestId?: string; projectId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { projectId, ...rest } = props;
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestForm
        slug="zzt-space"
        {...rest}
        initialValues={
          projectId ? { project_id: projectId, project_label: 'PRJ-1 - Tower' } : undefined
        }
      />
    </QueryClientProvider>,
  );
}

const rows = () =>
  Array.from(document.querySelectorAll<HTMLElement>('[data-testid="sample-request-line"]'));
const rowText = () => rows().map((r) => r.textContent + ' ' + Array.from(r.querySelectorAll('input')).map((i) => (i as HTMLInputElement).value).join(' '));

beforeEach(() => {
  vi.clearAllMocks();
  asMock(getSampleRequestQuotationPrefill).mockResolvedValue(PREFILL);
  asMock(createSampleRequest).mockResolvedValue({ id: 'sr-new', lines: [] });
});

describe('SFQ-20 a new request on a project starts from its quotation', () => {
  it('fills one row per quotation product, qty 1', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(getSampleRequestQuotationPrefill).toHaveBeenCalledWith('proj-1', undefined);
    expect(rowText()[0]).toContain('BASIN-1');
    expect(rowText()[1]).toContain('TAP-2');
    for (const row of rows()) {
      expect((within(row).getByLabelText('Quantity') as HTMLInputElement).value).toBe('1');
    }
  });

  it('records the source quotation in the saved draft', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(createSampleRequest).toHaveBeenCalled());
    expect(asMock(createSampleRequest).mock.calls[0][0]).toMatchObject({
      quotation_document_id: 'doc-1',
      quotation_issue_id: 'iss-1',
      lines: [
        { product_id: 'p-1', qty: 1 },
        { product_id: 'p-2', qty: 1 },
      ],
    });
  });

  it('names the quotation lines that were not added (Q3 note)', async () => {
    renderForm({ projectId: 'proj-1' });
    expect(
      await screen.findByText('1 quotation line was not added: 1 has no product.'),
    ).toBeTruthy();
  });

  it('a project with no quotation keeps the one blank row', async () => {
    asMock(getSampleRequestQuotationPrefill).mockResolvedValue({
      documents: [],
      document_id: null,
      issue_id: null,
      lines: [],
      skipped: [],
    });
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(getSampleRequestQuotationPrefill).toHaveBeenCalled());
    expect(rows()).toHaveLength(1);
  });
});

describe('SFQ-21 editing a draft never pre-fills', () => {
  it('does not ask for the quotation', async () => {
    asMock(getSampleRequest).mockResolvedValue({
      id: 'sr-1',
      request_no: 'SR-000001',
      status: 'draft',
      status_label: 'Draft',
      project_id: 'proj-1',
      project_code: 'PRJ-1',
      project_name: 'Tower',
      lines: [],
    });
    renderForm({ requestId: 'sr-1' });
    await waitFor(() => expect(getSampleRequest).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(getSampleRequestQuotationPrefill).not.toHaveBeenCalled();
  });
});

describe('SFQ-23 each pre-filled row can be removed', () => {
  it('Remove line drops that row only', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(within(rows()[0]).getByRole('button', { name: 'Remove line' }));
    expect(rows()).toHaveLength(1);
    expect(rowText()[0]).toContain('TAP-2');
  });
});

describe('SFQ-24 a project with several quotations shows a picker', () => {
  it('no picker for one quotation', async () => {
    renderForm({ projectId: 'proj-1' });
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(screen.queryByLabelText('Quotation')).toBeNull();
  });

  it('a picker for two', async () => {
    asMock(getSampleRequestQuotationPrefill).mockResolvedValue({
      ...PREFILL,
      documents: [doc('doc-1', 'Q-0001', 'iss-1'), doc('doc-2', 'Q-0002')],
    });
    renderForm({ projectId: 'proj-1' });
    expect(await screen.findByLabelText('Quotation')).toBeTruthy();
    expect(screen.getByText('Q-0001 (R2)')).toBeTruthy();
  });
});

describe('SFQ-26 a recorded source shows on the request', () => {
  it('names the quotation on a loaded draft', async () => {
    asMock(getSampleRequest).mockResolvedValue({
      id: 'sr-1',
      request_no: 'SR-000001',
      status: 'draft',
      status_label: 'Draft',
      project_id: 'proj-1',
      project_code: 'PRJ-1',
      project_name: 'Tower',
      quotation_document_id: 'doc-1',
      quotation_ref: 'Q-0001 (R2)',
      lines: [],
    });
    renderForm({ requestId: 'sr-1' });
    expect(await screen.findByText('Quotation: Q-0001 (R2)')).toBeTruthy();
  });
});
