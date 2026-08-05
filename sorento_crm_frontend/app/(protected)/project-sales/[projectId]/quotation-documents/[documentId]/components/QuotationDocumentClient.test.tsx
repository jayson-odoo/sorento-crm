/**
 * S7 - the signing gate on the internal quotation screen.
 *
 * What is worth pinning is the ONE rule the server enforces with a 422: an unsigned document
 * cannot be issued (AC-H1). The screen has to say so before the click, not after, and the reason
 * has to be readable rather than hidden in a tooltip. The rest of this file guards the two gear
 * actions that only exist once a revision does.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  QuotationDocument,
  QuotationSignatureRecord,
} from '../../../../_shared/services/quotationDocumentService';
import type { Project } from '../../../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const getQuotationDocument = vi.fn();
const listQuotationIssues = vi.fn();
const getProject = vi.fn();
const listQuotations = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('../../../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    getQuotationDocument: (...args: unknown[]) => getQuotationDocument(...args),
    listQuotationIssues: (...args: unknown[]) => listQuotationIssues(...args),
  };
});

vi.mock('../../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/projectService')
  >();
  return {
    ...actual,
    getProject: (...args: unknown[]) => getProject(...args),
    listQuotations: (...args: unknown[]) => listQuotations(...args),
  };
});

/**
 * Stubbed so this file tests the WIRING and not the line editor, which owns its own suite. The
 * stub does the one thing the wiring depends on: report a scope total the way the real editor
 * does, off a button a test can press.
 */
vi.mock('../../../components/QuotationVersionEditor', () => ({
  QuotationVersionEditor: ({ onTotalChange }: { onTotalChange?: (total: string) => void }) => (
    <button type="button" onClick={() => onTotalChange?.('9000.00')}>
      report a live total
    </button>
  ),
}));

import { QuotationDocumentClient } from './QuotationDocumentClient';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';

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

function signature(overrides: Partial<QuotationSignatureRecord> = {}): QuotationSignatureRecord {
  return {
    id: 's1',
    signer_name: 'Ahmad Faizal',
    mode: 'draw',
    image_data_uri: 'data:image/png;base64,STUB',
    signed_at: '2026-08-04T02:15:00',
    ip_address: '203.0.113.9',
    gps_lat: null,
    gps_lng: null,
    ...overrides,
  };
}

// No scopes on purpose: the line editor is a separate component with its own tests, and the
// signing gate is identical either way.
function quotationDocument(overrides: Partial<QuotationDocument> = {}): QuotationDocument {
  return {
    id: 'd1',
    project_id: 'p1',
    document_no: 'SRT/Q/2026/0141',
    our_ref: 'SRT/Q/2026/0141',
    your_ref: null,
    doc_date: '2026-02-26',
    recipient_party_id: null,
    recipient_name_snapshot: 'Nadi Cergas Sdn Bhd',
    recipient_address_snapshot: null,
    recipient_phone_snapshot: null,
    attn_name: 'Kelly',
    subject_title: 'CADANGAN MEMBINA PANGSAPURI',
    cover_letter_html: null,
    terms_html: null,
    signatory_name: 'Ahmad Faizal',
    signatory_phone: null,
    scopes: [],
    grand_total: '0.00',
    issue_count: 0,
    current_issue_no: null,
    is_issued: false,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuotationDocumentClient projectId="p1" documentId="d1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getProject.mockResolvedValue(project());
  listQuotations.mockResolvedValue([]);
  listQuotationIssues.mockResolvedValue([]);
});

/**
 * The header total has the same defect the in-table total had: read straight off the server it
 * sits still while the user edits a line, so the figure they are watching disagrees with the
 * figure they are typing. It takes the live one whenever the screen has one.
 */
describe('QuotationDocumentClient header total', () => {
  it('prefers the live total over the server one', () => {
    render(
      <QuotationDocumentHeader
        document={quotationDocument({ grand_total: '235000.00' })}
        liveGrandTotal="253420.50"
      />,
    );

    expect(screen.getByText('RM 253,420.50')).toBeInTheDocument();
    expect(screen.queryByText('RM 235,000.00')).not.toBeInTheDocument();
  });

  it('falls back to the saved total when nothing live is on offer', () => {
    render(<QuotationDocumentHeader document={quotationDocument({ grand_total: '235000.00' })} />);

    expect(screen.getByText('RM 235,000.00')).toBeInTheDocument();
  });

  it('takes the figure the line editor reports and keeps the other scopes saved', async () => {
    // Two scopes, only one of them open. The live figure replaces ITS saved total and nothing
    // else, so the header reads 9,000.00 + 18,420.50 rather than the server's 253,420.50.
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '253420.50',
        scopes: [
          {
            id: 'q1',
            scope_label: 'Townhouse',
            sort_order: 1,
            outcome: 'open',
            current_version_id: 'v1',
            current_version_no: 1,
            line_count: 2,
            scope_total: '235000.00',
          },
          {
            id: 'q2',
            scope_label: 'Guard house',
            sort_order: 2,
            outcome: 'open',
            current_version_id: 'v2',
            current_version_no: 1,
            line_count: 1,
            scope_total: '18420.50',
          },
        ],
      }),
    );
    listQuotations.mockResolvedValue([
      {
        id: 'q1',
        project_id: 'p1',
        scope_label: 'Townhouse',
        outcome: 'open',
        version_count: 1,
        below_floor_count: 0,
        non_standard_count: 0,
        line_count: 2,
      },
    ]);
    renderScreen();

    // The server's own total until anything moves.
    expect(await screen.findByText('RM 253,420.50')).toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: 'report a live total' }));

    await waitFor(() => expect(screen.getByText('RM 27,420.50')).toBeInTheDocument());
    expect(screen.queryByText('RM 253,420.50')).not.toBeInTheDocument();
  });

  it('renders every field of the letterhead, with a dash where there is no value', () => {
    // Never a hidden section: a document with no Your Ref is a normal document, not a fault.
    render(
      <QuotationDocumentHeader
        document={quotationDocument({ your_ref: null, attn_name: null, grand_total: '0.00' })}
      />,
    );

    expect(screen.getByText('Your Ref')).toBeInTheDocument();
    expect(screen.getByText('Attn:')).toBeInTheDocument();
    expect(screen.getByText('RM 0.00')).toBeInTheDocument();
  });
});

describe('QuotationDocumentClient signing gate', () => {
  it('refuses to offer Issue until the quotation is signed, and says why', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const issue = await screen.findByRole('button', { name: 'Issue R1' });
    expect(issue).toBeDisabled();
    expect(issue).toHaveAttribute('title', 'Sign it first');
    // Readable without hovering: the tooltip alone is unusable on a phone.
    expect(screen.getByText('Sign it first')).toBeInTheDocument();
    // And the way out of it is right there.
    expect(screen.getByRole('button', { name: 'Sign' })).toBeEnabled();
  });

  it('opens Issue once a signature is on the draft', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ signatory_signature: signature() }),
    );
    renderScreen();

    const issue = await screen.findByRole('button', { name: 'Issue R1' });
    expect(issue).toBeEnabled();
    expect(screen.queryByText('Sign it first')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign' })).not.toBeInTheDocument();
  });

  it('refuses to re-issue an issued document that carries no signature', async () => {
    // "It is issued, so it must have been signed" is the tempting shortcut and it is wrong on
    // every document issued before the signature gate existed. Those rows are real: pressing
    // Issue on one puts the user straight into the server's `quotation_document_unsigned` 422.
    // Signed-ness is read off the signature and nothing else.
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        is_issued: true,
        current_issue_no: 1,
        issue_count: 1,
        signatory_signature: null,
      }),
    );
    listQuotationIssues.mockResolvedValue([
      {
        id: 'i1',
        document_id: 'd1',
        issue_no: 1,
        our_ref_text: 'SRT/Q/2026/0141 (R2)',
        issued_at: '2026-08-04T02:00:00',
        issued_by: 'u1',
        issued_by_name: 'Ahmad',
        grand_total: '0.00',
        scope_count: 0,
      },
    ]);
    renderScreen();

    const issue = await screen.findByRole('button', { name: 'Issue R2' });
    expect(issue).toBeDisabled();
    expect(issue).toHaveAttribute('title', 'Sign it first');
    // And the way out is offered, not just the refusal.
    expect(screen.getByRole('button', { name: 'Sign' })).toBeEnabled();
  });

  it('shows the captured signature read-only in the signatures panel', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ signatory_signature: signature() }),
    );
    renderScreen();

    await waitFor(() => expect(screen.getByTestId('signature-pad-readonly')).toBeInTheDocument());
    // The pad labels the image from its heading, and the heading is who signed.
    expect(screen.getByRole('img', { name: 'Ahmad Faizal image' })).toHaveAttribute(
      'src',
      'data:image/png;base64,STUB',
    );
    expect(screen.getByText('203.0.113.9')).toBeInTheDocument();
    // The customer half still renders, stating its own resting state rather than vanishing.
    expect(
      screen.getByText(/Issue this quotation to send the customer a link/i),
    ).toBeInTheDocument();
  });
});
