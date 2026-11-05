/**
 * S12 - the document read as four tabs instead of one long scroll.
 *
 * The client's words: "the cover letter, terms and conditions, signatures should be their own tab,
 * so I don't need to scroll down to see". Three things are worth pinning, because each is one
 * careless edit from coming back:
 *
 * 1. Every tab is a ROUTE, so the terms can be linked to and Back walks through them.
 * 2. The letterhead - ref, recipient, total, the CTA - is on screen on EVERY tab. It is the
 *    identity of the record, not a section of it.
 * 3. An empty tab still renders, with its empty state. A tab that hid itself when it had nothing
 *    in it would read as a missing feature.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';
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

const BASE = '/project-sales/p1/quotation-documents/d1';

// QUOTE-COVER-DESIGN: only the cover preview call is intercepted; every other apiFetch is real.
const coverPreview = vi.fn();
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: (url: string, init?: RequestInit) =>
      String(url).includes('/quotation-documents/cover-preview')
        ? coverPreview(String(url), init)
        : actual.apiFetch(url, init),
  };
});

const previewOk = (intro = '<p>Dear Kelly</p>') =>
  new Response(
    JSON.stringify({
      cover_title: 'QUOTATION',
      cover_show_letterhead: true,
      cover_rows: [{ key: 'reference', label: 'Reference No.', text: 'SRT/Q/2026/0141-R1 Menara Test' }],
      cover_intro_html: intro,
      cover_closing_html: '',
      sender_name: 'Sorento Sdn Bhd',
      sender_logo_url: null,
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );

const getQuotationDocument = vi.fn();
const listQuotationIssues = vi.fn();
const getProject = vi.fn();
const listQuotations = vi.fn();
const getQuotationFeedback = vi.fn();
const setQuotationFeedbackHandled = vi.fn();
const push = vi.fn();

// The tab strip reads the pathname to decide what is open, so each test sets the route it is
// making a claim about.
let pathname = BASE;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

// The shell renders the price-floor block, which reads the caller's grants. Answered outright:
// the real hook reaches NextAuth, which throws outside a SessionProvider, and none of the tab
// specs here are about the approval gate (it has its own spec).
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  useHasAnyPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('../../../../_shared/hooks/useQuotationDocuments', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/hooks/useQuotationDocuments')
  >();
  return {
    ...actual,
    useQuotationApprovalGraph: () => ({ data: null, isLoading: false }),
  };
});

vi.mock('../../../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    getQuotationDocument: (...args: unknown[]) => getQuotationDocument(...args),
    listQuotationIssues: (...args: unknown[]) => listQuotationIssues(...args),
    getQuotationFeedback: (...args: unknown[]) => getQuotationFeedback(...args),
    setQuotationFeedbackHandled: (...args: unknown[]) => setQuotationFeedbackHandled(...args),
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

// Stubbed for the same reason the sibling spec stubs it: this file tests where things render, not
// the line editor, which owns its own suite.
vi.mock('../../../components/QuotationVersionEditor', () => ({
  QuotationVersionEditor: () => <div data-testid="line-editor" />,
}));

import { QuotationDocumentClient } from './QuotationDocumentClient';
import { QuotationFeedbackPanel } from './QuotationFeedbackPanel';
import {
  QuotationCoverLetterTab,
  QuotationHeaderTab,
  QuotationSignaturesTab,
  QuotationTermsTab,
} from './QuotationDocumentTabPanels';

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
    grand_total: '235000.00',
    issue_count: 0,
    current_issue_no: null,
    is_issued: false,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function renderTab(route: string, tab: React.ReactNode) {
  pathname = route;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuotationDocumentClient projectId="p1" documentId="d1">
        {tab}
      </QuotationDocumentClient>
    </QueryClientProvider>,
  );
}

/**
 * What stays above the tabs on every tab (#1341, owner: "i need this to be under 'Header' tab"):
 * the title, the status pill, the project title and developer lines, and the header actions.
 * The letterhead card itself (To, Our Ref, Your Ref, Date, Total) lives in the Header tab only.
 */
async function expectIdentityOnScreen() {
  // The Order Inquiry record card (PROPOSAL-HEADER-LAYOUT): number, status, title; no customer
  // line (the letterhead's To carries it).
  const card = await screen.findByTestId('record-header-card');
  expect(within(card).getByRole('heading', { name: 'SRT/Q/2026/0141' })).toBeInTheDocument();
  expect(within(card).getByText('CADANGAN MEMBINA PANGSAPURI')).toBeInTheDocument();
  expect(within(card).queryByText('Nadi Cergas Sdn Bhd')).toBeNull();
  expect(within(card).getByText('Draft')).toBeInTheDocument();
  // E4: an unsigned, unblocked draft leads with Sign and offers no Send to Customer.
  expect(screen.getByRole('button', { name: 'Sign' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Proposal actions' })).toBeInTheDocument();
}

/**
 * A panel's own heading, told apart from the tab of the same name: the tab is a link in the strip,
 * this is the card the tab leads to.
 */
function panelTitle(title: string) {
  return screen.getByText(title, { selector: '[data-slot="card-title"]' });
}

beforeEach(() => {
  vi.clearAllMocks();
  pathname = BASE;
  getProject.mockResolvedValue(project());
  listQuotations.mockResolvedValue([]);
  listQuotationIssues.mockResolvedValue([]);
  getQuotationDocument.mockResolvedValue(quotationDocument());
  coverPreview.mockImplementation(async () => previewOk());
  getQuotationFeedback.mockResolvedValue({ open_count: 0, requests: [] });
  setQuotationFeedbackHandled.mockResolvedValue(undefined);
});

describe('the quotation document tab strip', () => {
  // No Lines tab (PROPOSAL-HEADER-LAYOUT, owner 5 Nov 2026): the lines sit on the Header tab.
  it('AC-QF050/053: reads Header, Cover letter, Terms, Signatures, Spec sheet, each its own route', async () => {
    renderTab(BASE, <QuotationHeaderTab />);

    const tabs = await screen.findAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      'Header',
      'Cover letter',
      'Terms',
      'Signatures',
      'Customer feedback',
      // PS-SPEC-SHEET: the project catalogue, last.
      'Spec sheet',
    ]);
    expect(screen.getByRole('tab', { name: 'Header' })).toHaveAttribute('href', BASE);
    expect(screen.getByRole('tab', { name: 'Cover letter' })).toHaveAttribute(
      'href',
      `${BASE}/cover-letter`,
    );
    expect(screen.getByRole('tab', { name: 'Terms' })).toHaveAttribute('href', `${BASE}/terms`);
    expect(screen.getByRole('tab', { name: 'Signatures' })).toHaveAttribute(
      'href',
      `${BASE}/signatures`,
    );
    expect(screen.getByRole('tab', { name: 'Customer feedback' })).toHaveAttribute(
      'href',
      `${BASE}/feedback`,
    );
    expect(screen.getByRole('tab', { name: 'Spec sheet' })).toHaveAttribute(
      'href',
      `${BASE}/spec-sheet`,
    );
    // The owner struck "Scopes" out and wrote "Lines" over it.
    expect(screen.queryByRole('tab', { name: 'Scopes' })).toBeNull();
  });

  it('takes the open tab from the URL, so a link can point straight at the terms', async () => {
    renderTab(`${BASE}/terms`, <QuotationTermsTab />);

    expect(await screen.findByRole('tab', { name: 'Terms' })).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByRole('tab', { name: 'Header' })).toHaveAttribute('data-state', 'inactive');
  });

  it('AC-QF050: opens on Header, the first tab, on the index route', async () => {
    renderTab(BASE, <QuotationHeaderTab />);

    expect(await screen.findByRole('tab', { name: 'Header' })).toHaveAttribute(
      'data-state',
      'active',
    );
  });

});

describe('what each quotation document tab renders', () => {
  it('AC-QF051: the Header tab holds the letterhead card, below the identity lines', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ your_ref: 'NC/18', recipient_address_snapshot: 'Level 8\nMenara' }),
    );
    renderTab(BASE, <QuotationHeaderTab />);

    const card = await screen.findByTestId('quotation-header-card');
    expect(card).toHaveTextContent('To');
    expect(card).toHaveTextContent('Level 8');
    expect(card).toHaveTextContent('Attn:');
    expect(card).toHaveTextContent('Our Ref');
    expect(card).toHaveTextContent('SRT/Q/2026/0141');
    expect(card).toHaveTextContent('NC/18');
    expect(card).toHaveTextContent('Date');
    expect(card).toHaveTextContent('RM 235,000.00');
    // The lines sit under it on the same tab (PROPOSAL-HEADER-LAYOUT).
    expect(await screen.findByText('No lines on this quotation yet')).toBeInTheDocument();
    await expectIdentityOnScreen();
  });

  it('AC-QF051: the letterhead card is not above the tabs, so another tab does not repeat it', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ terms_html: '<p>30 days</p>' }));
    renderTab(`${BASE}/terms`, <QuotationTermsTab />);

    expect(await screen.findByText('30 days')).toBeInTheDocument();
    expect(screen.queryByTestId('quotation-header-card')).toBeNull();
    expect(screen.queryByText('Our Ref')).toBeNull();
    expect(screen.queryByText('RM 235,000.00')).toBeNull();
    await expectIdentityOnScreen();
  });

  it('renders the cover letter tab as the preview card with the intro, and the identity above it', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ cover_letter_html: '<p>Dear Kelly</p>' }),
    );
    renderTab(`${BASE}/cover-letter`, <QuotationCoverLetterTab />);

    expect(await screen.findByText('Dear Kelly')).toBeInTheDocument();
    expect(screen.getByText('SRT/Q/2026/0141-R1 Menara Test')).toBeInTheDocument();
    expect(screen.queryByText('Cover letter', { selector: '[data-slot="card-title"]' })).toBeNull();
    await expectIdentityOnScreen();
  });

  it('M1: a proposal prints PROPOSAL FROM on the cover letter tab, not QUOTATION FROM', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ kind: 'proposal' }));
    renderTab(`${BASE}/cover-letter`, <QuotationCoverLetterTab />);

    expect(await screen.findByText('Sorento Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Proposal from')).toBeInTheDocument();
    expect(screen.queryByText('Quotation from')).toBeNull();
  });

  it('M1: a quotation prints QUOTATION FROM on the cover letter tab', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ kind: 'quotation' }));
    renderTab(`${BASE}/cover-letter`, <QuotationCoverLetterTab />);

    expect(await screen.findByText('Sorento Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Quotation from')).toBeInTheDocument();
    expect(screen.queryByText('Proposal from')).toBeNull();
  });

  it('renders the terms tab, and the identity above it', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ terms_html: '<p>30 days</p>' }));
    renderTab(`${BASE}/terms`, <QuotationTermsTab />);

    expect(await screen.findByText('30 days')).toBeInTheDocument();
    expect(panelTitle('Terms and conditions')).toBeInTheDocument();
    await expectIdentityOnScreen();
  });

  it('renders the signatures tab, and the identity above it', async () => {
    renderTab(`${BASE}/signatures`, <QuotationSignaturesTab />);

    // Both halves render even with no ink on either, which is AC-H8's whole point.
    expect(
      await screen.findByText(/No signature captured on this quotation yet/i),
    ).toBeInTheDocument();
    expect(panelTitle('Signatures')).toBeInTheDocument();
    expect(
      screen.getByText(/Send this quotation to the customer to give them a link/i),
    ).toBeInTheDocument();
    await expectIdentityOnScreen();
  });

  it('an empty intro still renders the preview card, and the terms tab keeps its empty state', async () => {
    coverPreview.mockImplementation(async () => previewOk(''));
    renderTab(`${BASE}/cover-letter`, <QuotationCoverLetterTab />);
    expect(await screen.findByText('Reference No.')).toBeInTheDocument();
    expect(screen.queryByText('No cover letter on this quotation yet.')).toBeNull();

    renderTab(`${BASE}/terms`, <QuotationTermsTab />);
    expect(await screen.findByText('No terms on this quotation yet.')).toBeInTheDocument();
  });

  it('when the preview call fails the cover letter tab shows an error line, not the old panel', async () => {
    coverPreview.mockImplementation(
      async () => new Response(JSON.stringify({ detail: 'boom' }), { status: 500 }),
    );
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ cover_letter_html: '<p>Dear Kelly</p>' }),
    );
    renderTab(`${BASE}/cover-letter`, <QuotationCoverLetterTab />);

    expect(await screen.findByText(/could not|couldn.t|failed|unable|error/i)).toBeInTheDocument();
    expect(screen.queryByText('Dear Kelly')).toBeNull();
    expect(screen.queryByText('Cover letter', { selector: '[data-slot="card-title"]' })).toBeNull();
  });
});

// PS-QUOTE-MATRIX R20 (mock v3 frame 5): the Customer feedback tab replaces Accept / Reject / Apply.
// Values invented.
const FEEDBACK = {
  open_count: 2,
  requests: [
    {
      id: 'req-2',
      issue_label: 'Rev A',
      submitted_at: '2026-11-02T10:40:00',
      requester_name: 'Buyer A',
      note: 'Please call me about the sinks.',
      rows: [
        {
          id: 'fb-1',
          line_id: 'l5',
          scope_label: 'UNIT',
          line_description: 'KS903 kitchen sink',
          cell_key: 'c-kit',
          cell_label: 'Type C - 3 BH / Kitchen',
          kind: 'quantity',
          value_from: '133.00',
          value_to: '140.00',
          model: null,
          note: 'Type C needs 140.',
          handled_at: null,
          handled_by_name: null,
        },
        {
          id: 'fb-2',
          line_id: 'l3',
          scope_label: 'UNIT',
          line_description: 'Floor trap 100mm',
          cell_key: null,
          cell_label: null,
          kind: 'note',
          value_from: null,
          value_to: null,
          model: null,
          note: 'Balcony traps not needed.',
          handled_at: null,
          handled_by_name: null,
        },
        {
          id: 'fb-3',
          line_id: 'l9',
          scope_label: 'LEVEL 9',
          line_description: 'Urinal c/w flush valve',
          cell_key: null,
          cell_label: null,
          kind: 'unit_price',
          value_from: '420.00',
          value_to: '380.00',
          model: null,
          note: 'Our budget is 380.',
          handled_at: '2026-11-02T13:05:00',
          handled_by_name: 'Sales A',
        },
        {
          id: 'fb-4',
          line_id: 'l9',
          scope_label: 'LEVEL 9',
          line_description: 'Urinal c/w flush valve',
          cell_key: 'gone',
          cell_label: null,
          kind: 'model_swap',
          value_from: null,
          value_to: '300.00',
          model: 'UR-200',
          note: null,
          handled_at: '2026-11-02T13:06:00',
          handled_by_name: 'Sales A',
        },
      ],
    },
  ],
};

describe('the Customer feedback tab (PS-QUOTE-MATRIX)', () => {
  it('badges the tab with the open count', async () => {
    getQuotationFeedback.mockResolvedValue(FEEDBACK);
    renderTab(BASE, <QuotationHeaderTab />);

    const badge = await screen.findByTestId('quotation-feedback-badge');
    expect(badge).toHaveTextContent('2');
    expect(within(screen.getByRole('tab', { name: /Customer feedback/ })).getByTestId('quotation-feedback-badge')).toBe(badge);
  });

  it('shows no badge when nothing is open', async () => {
    renderTab(BASE, <QuotationHeaderTab />);
    await screen.findByRole('tab', { name: 'Customer feedback' });
    expect(screen.queryByTestId('quotation-feedback-badge')).toBeNull();
  });

  it('lists each note with where it points, the hint beside today\'s value, and Handled', async () => {
    getQuotationFeedback.mockResolvedValue(FEEDBACK);
    renderTab(`${BASE}/feedback`, <QuotationFeedbackPanel />);

    const rows = await screen.findAllByTestId('quotation-feedback-row');
    expect(rows).toHaveLength(4);
    expect(within(rows[0]).getByText('UNIT · Type C - 3 BH / Kitchen')).toBeInTheDocument();
    expect(within(rows[0]).getByText('"Type C needs 140."')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Suggested quantity 140 (now 133)')).toBeInTheDocument();
    expect(within(rows[1]).getByText('UNIT · whole item')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Suggested price RM 380.00 (now 420.00)')).toBeInTheDocument();
    expect(within(rows[2]).getByText(/^Handled by Sales A, /)).toBeInTheDocument();
    expect(rows[2]).toHaveAttribute('data-handled', 'true');
    expect(within(rows[3]).getByText('LEVEL 9 · (column removed)')).toBeInTheDocument();
    expect(within(rows[3]).getByText('Another model: UR-200 at RM 300.00')).toBeInTheDocument();
    expect(screen.getByText('Please call me about the sinks.')).toBeInTheDocument();
    expect(screen.getByText(/From Buyer A on Rev A/)).toBeInTheDocument();
    // Nothing to accept, reject or apply, anywhere.
    expect(screen.queryByRole('button', { name: /accept|reject|apply/i })).toBeNull();
  });

  it('ticks a note handled, and the badge moves with it', async () => {
    getQuotationFeedback.mockResolvedValue(FEEDBACK);
    renderTab(`${BASE}/feedback`, <QuotationFeedbackPanel />);

    const rows = await screen.findAllByTestId('quotation-feedback-row');
    // What the server answers once the tick has landed.
    getQuotationFeedback.mockResolvedValue({
      ...FEEDBACK,
      open_count: 1,
      requests: [
        {
          ...FEEDBACK.requests[0],
          rows: FEEDBACK.requests[0].rows.map((row) =>
            row.id === 'fb-1'
              ? { ...row, handled_at: '2026-11-02T14:00:00', handled_by_name: 'Sales A' }
              : row,
          ),
        },
      ],
    });
    fireEvent.click(within(rows[0]).getByRole('checkbox'));
    await waitFor(() =>
      expect(setQuotationFeedbackHandled).toHaveBeenCalledWith('p1', 'd1', 'fb-1', true),
    );
    await waitFor(() => expect(screen.getByTestId('quotation-feedback-badge')).toHaveTextContent('1'));

    fireEvent.click(within(rows[2]).getByRole('checkbox'));
    await waitFor(() =>
      expect(setQuotationFeedbackHandled).toHaveBeenCalledWith('p1', 'd1', 'fb-3', false),
    );
  });

  it('Show in Lines opens the Header tab, where the lines are', async () => {
    getQuotationFeedback.mockResolvedValue(FEEDBACK);
    renderTab(`${BASE}/feedback`, <QuotationFeedbackPanel />);

    const rows = await screen.findAllByTestId('quotation-feedback-row');
    fireEvent.click(within(rows[0]).getByRole('button', { name: 'Show in Lines' }));
    expect(push).toHaveBeenCalledWith(BASE);
  });

  it('renders its empty state when nothing came in', async () => {
    renderTab(`${BASE}/feedback`, <QuotationFeedbackPanel />);
    expect(await screen.findByText('No customer feedback yet')).toBeInTheDocument();
  });
});
