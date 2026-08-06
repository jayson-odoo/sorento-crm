/**
 * S2 - QuotationsPanel, now a list of quotation DOCUMENTS.
 *
 * What is worth pinning is that a document is readable WITHOUT opening it: the reference the
 * customer quotes back, what it is for, who it went to, whether it has been issued and what it
 * is worth - plus the footer that adds those values up, which is the number a sales manager
 * comes to this tab for. The price-floor guardrail stays on the toolbar, counted across the
 * project's scopes.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../_shared/services/quotationDocumentService';
import type { Project, ProjectQuotation } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listQuotationDocuments = vi.fn();
const createQuotationDocument = vi.fn();
const listQuotations = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  // Without this the grid never leaves its skeleton: the real hook fetches saved column
  // order and `isLoading` gates the body rows, and nothing answers that call under jsdom.
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    listQuotationDocuments: (...args: unknown[]) => listQuotationDocuments(...args),
    createQuotationDocument: (...args: unknown[]) => createQuotationDocument(...args),
  };
});

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listQuotations: (...args: unknown[]) => listQuotations(...args),
  };
});

import { QuotationsPanel } from './QuotationsPanel';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
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
  };
}

function scope(overrides: Partial<ProjectQuotation> = {}): ProjectQuotation {
  return {
    id: 'q1',
    project_id: 'p1',
    scope_label: 'House Units',
    outcome: 'open',
    version_count: 1,
    current_version_id: 'v1',
    current_version_no: 1,
    current_total: '12000.00',
    below_floor_count: 0,
    non_standard_count: 0,
    line_count: 0,
    ...overrides,
  };
}

function quotationDocument(overrides: Partial<QuotationDocument> = {}): QuotationDocument {
  return {
    id: 'd1',
    project_id: 'p1',
    document_no: 'SRT/Q/2026/0141',
    our_ref: 'SRT/Q/2026/0141 (R2)',
    your_ref: null,
    doc_date: '2026-02-26',
    recipient_party_id: null,
    recipient_name_snapshot: 'Nadi Cergas Sdn Bhd',
    recipient_address_snapshot: null,
    recipient_phone_snapshot: null,
    attn_name: 'Kelly',
    subject_title: 'CADANGAN MEMBINA PANGSAPURI RUMAH IDAM',
    cover_letter_html: null,
    terms_html: null,
    signatory_name: null,
    signatory_phone: null,
    scopes: [],
    grand_total: '696923.00',
    issue_count: 2,
    current_issue_no: 2,
    is_issued: true,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function renderPanel(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationsPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listQuotationDocuments.mockResolvedValue([]);
  listQuotations.mockResolvedValue([]);
});

describe('QuotationsPanel', () => {
  it('offers the first quotation when nothing is quoted', async () => {
    renderPanel();

    expect(await screen.findByText(/Nothing quoted yet/i)).toBeInTheDocument();
    // ONE way in, in the toolbar (ADR 1d): a second button in the middle of an empty state is
    // another thing to read and decide between.
    expect(screen.getByRole('button', { name: /Add a quotation/i })).toBeInTheDocument();
  });

  it('reads a document without opening it: reference, subject, recipient, status, date', async () => {
    listQuotationDocuments.mockResolvedValue([quotationDocument()]);

    renderPanel();

    // The REFERENCE the customer quotes back, revision included - not the document number on
    // its own, which is a different string once anything has been issued.
    expect(await screen.findByText('SRT/Q/2026/0141 (R2)')).toBeInTheDocument();
    expect(screen.getByText('CADANGAN MEMBINA PANGSAPURI RUMAH IDAM')).toBeInTheDocument();
    expect(screen.getByText('Nadi Cergas Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Issued')).toBeInTheDocument();
    expect(screen.getByText('26/02/2026')).toBeInTheDocument();
    // No UUID reaches the screen.
    expect(screen.queryByText('d1')).not.toBeInTheDocument();
  });

  it('says Draft on a document nobody has issued', async () => {
    listQuotationDocuments.mockResolvedValue([
      quotationDocument({
        our_ref: 'SRT/Q/2026/0142',
        issue_count: 0,
        current_issue_no: null,
        is_issued: false,
      }),
    ]);

    renderPanel();

    expect(await screen.findByText('Draft')).toBeInTheDocument();
  });

  /**
   * S17 on the list. The client asked "when i request changes, how can i see it from the
   * system?", and a salesperson scanning this tab is the second place that question gets asked:
   * the row has to say which quotation is waiting on THEM without being opened.
   *
   * It rides the Status column rather than a new one, because "the customer asked for changes"
   * IS where the quotation stands - a second column would be mostly empty and would push the
   * money off a 375px screen.
   */
  it('says Changes requested on the row, so a scan finds the one waiting on you', async () => {
    listQuotationDocuments.mockResolvedValue([
      quotationDocument({
        customer_decision: 'changes_requested',
        changes_requested_at: '2026-08-06T02:15:00',
        changes_requested_note: 'can you provide me more discount',
        changes_requested_by_name: 'Kelly',
      }),
    ]);

    renderPanel();

    expect(await screen.findByText('Changes requested')).toBeInTheDocument();
    // It replaces Issued rather than sitting beside it: an issued quotation the customer has
    // answered is not still "Issued, awaiting", it is answered.
    expect(screen.queryByText('Issued')).toBeNull();
  });

  it('says Accepted, and acceptance wins over an older request', async () => {
    listQuotationDocuments.mockResolvedValue([
      quotationDocument({
        customer_decision: 'accepted',
        accepted_at: '2026-08-06T04:00:00',
        changes_requested_at: '2026-08-06T02:15:00',
        changes_requested_note: 'can you provide me more discount',
      }),
    ]);

    renderPanel();

    expect(await screen.findByText('Accepted')).toBeInTheDocument();
    expect(screen.queryByText('Changes requested')).toBeNull();
  });

  it('leaves a quotation nobody has answered reading Issued', async () => {
    listQuotationDocuments.mockResolvedValue([quotationDocument({ customer_decision: null })]);

    renderPanel();

    expect(await screen.findByText('Issued')).toBeInTheDocument();
    expect(screen.queryByText('Changes requested')).toBeNull();
    expect(screen.queryByText('Accepted')).toBeNull();
  });

  it('adds up the values of the documents on the page', async () => {
    listQuotationDocuments.mockResolvedValue([
      quotationDocument({ id: 'd1', grand_total: '696923.00' }),
      quotationDocument({
        id: 'd2',
        our_ref: 'SRT/Q/2026/0142',
        document_no: 'SRT/Q/2026/0142',
        grand_total: '1250.50',
      }),
    ]);

    renderPanel();

    expect(await screen.findByText('RM 696,923.00')).toBeInTheDocument();
    expect(screen.getByText('RM 1,250.50')).toBeInTheDocument();
    // Summed to the cent off the strings, in the footer under the column it sums.
    expect(screen.getByText('RM 698,173.50')).toBeInTheDocument();
  });

  it('surfaces the price-floor guardrail across the project rather than per document', async () => {
    listQuotationDocuments.mockResolvedValue([quotationDocument()]);
    listQuotations.mockResolvedValue([
      scope({ id: 'q1', below_floor_count: 2, non_standard_count: 1 }),
      scope({ id: 'q2', below_floor_count: 1, non_standard_count: 3 }),
    ]);

    renderPanel();

    expect(await screen.findByText('3 below the price floor')).toBeInTheDocument();
    expect(screen.getByText('4 non-standard')).toBeInTheDocument();
  });

  it('opens the document when the row is clicked', async () => {
    listQuotationDocuments.mockResolvedValue([quotationDocument()]);

    renderPanel();

    fireEvent.click(await screen.findByText('Nadi Cergas Sdn Bhd'));

    expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1');
  });

  it('hides every write affordance on a project the user cannot edit', async () => {
    listQuotationDocuments.mockResolvedValue([quotationDocument()]);

    renderPanel({ can_edit: false });

    expect(await screen.findByText('SRT/Q/2026/0141 (R2)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add a quotation/i })).toBeNull();
  });
});
