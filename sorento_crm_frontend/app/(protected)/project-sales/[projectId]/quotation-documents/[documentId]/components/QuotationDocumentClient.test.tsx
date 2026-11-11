/**
 * S7 + #1341 - the quotation document shell: the signing gate, and the way into editing.
 *
 * Two things are pinned here.
 *
 * The signing gate is the ONE rule the server enforces with a 422: an unsigned document cannot be
 * issued (AC-H1). The screen has to say so before the click, not after, and the reason has to be
 * readable rather than hidden in a tooltip.
 *
 * The in-place edit session is gone (#1341): "Edit quotation means I edit the whole quotation", so
 * Edit in the gear opens the form page, and this page is a read. The claims here are that the gear
 * leads there (after the existing revise prompt when the customer holds a version), that no
 * Save/Cancel pair or letterhead input appears on this page, and that the per-scope Edit scope
 * button is gone, and so is Record outcome (PROJECT-OUTCOME-SINGLE: one outcome per project).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { StatusGraph } from '@/app/(protected)/system-management/status-graphs/types/statusGraph.types';
import type {
  QuotationDocument,
  QuotationScope,
  QuotationSignatureRecord,
} from '../../../../_shared/services/quotationDocumentService';
import type {
  Project,
  ProjectQuotation,
  QuotationLine,
  QuotationVersion,
} from '../../../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/toast', () => ({
  toast: {
    custom: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    dismiss: vi.fn(),
  },
}));

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

const getQuotationDocument = vi.fn();
const listQuotationIssues = vi.fn();
const updateQuotationDocument = vi.fn();
const queueQuotationIssuePdf = vi.fn();
const queueQuotationIssueXlsx = vi.fn();
const fetchDownloadsForEntity = vi.fn();
const getProject = vi.fn();
const listQuotations = vi.fn();
const listQuotationVersions = vi.fn();
const listQuotationLines = vi.fn();
const replaceQuotationLines = vi.fn();
const createQuotationLine = vi.fn();
const updateQuotationLine = vi.fn();
const deleteQuotationLine = vi.fn();
const reviseQuotation = vi.fn();
const recomputeQuotationVersion = vi.fn();
const push = vi.fn();
const reviseQuotationApproval = vi.fn();
const moveQuotationApproval = vi.fn();
const approveQuotationDocument = vi.fn();
const rejectQuotationDocument = vi.fn();
const issueQuotationDocument = vi.fn();
const createQuotationSignLink = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1',
  useSearchParams: () => new URLSearchParams(),
}));

// The lines are the system DataGrid now (#1341), which holds skeleton rows until the saved
// column order answers; nothing answers that call under jsdom.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// The price-floor block reads the caller's grants to decide whether to offer Approve/Reject.
// Answered outright rather than through a SessionProvider: none of the specs in this file are
// about the approval gate (its own spec covers that), and the real hook reaches NextAuth, which
// throws outside a provider.
// Mutable per test (QUOTE-APPROVAL-UX): empty by default, so every older spec runs as a viewer
// without the approve grant; the approver specs grant `projects.quotations.approve`.
let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({ permissions: [...granted], permissionSet: granted, isLoading: false }),
}));

// The approval graph the header reads its "Send for approval" label from. Null by default.
let graphData: StatusGraph | null = null;

const createPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/pendingActionService')>();
  return {
    ...actual,
    createPendingAction: (...args: unknown[]) => createPendingAction(...args),
    cancelPendingAction: vi.fn(),
    getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
  };
});
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (input: { id?: string }) => input.id ?? 'toast',
  dismissDeferredToast: vi.fn(),
}));

// The approval graph is one install-wide read the block uses to name the salesperson's next
// move. Empty here: with nothing below the floor the block never renders at all.
vi.mock('../../../../_shared/hooks/useQuotationDocuments', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/hooks/useQuotationDocuments')
  >();
  return {
    ...actual,
    useQuotationApprovalGraph: () => ({ data: graphData, isLoading: false }),
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
    updateQuotationDocument: (...args: unknown[]) => updateQuotationDocument(...args),
    reviseQuotationApproval: (...args: unknown[]) => reviseQuotationApproval(...args),
    moveQuotationApproval: (...args: unknown[]) => moveQuotationApproval(...args),
    approveQuotationDocument: (...args: unknown[]) => approveQuotationDocument(...args),
    rejectQuotationDocument: (...args: unknown[]) => rejectQuotationDocument(...args),
    issueQuotationDocument: (...args: unknown[]) => issueQuotationDocument(...args),
    createQuotationSignLink: (...args: unknown[]) => createQuotationSignLink(...args),
    queueQuotationIssuePdf: (...args: unknown[]) => queueQuotationIssuePdf(...args),
    queueQuotationIssueXlsx: (...args: unknown[]) => queueQuotationIssueXlsx(...args),
  };
});

// The printer chip in the header reads the per-entity downloads feed. Answered here so the
// export specs below are about the click and the chip, not about the drawer's polling.
vi.mock('@/services/myDownloadsService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/myDownloadsService')>();
  return {
    ...actual,
    fetchDownloadsForEntity: (...args: unknown[]) => fetchDownloadsForEntity(...args),
    fetchDownloadUrl: vi.fn(),
  };
});

// The download rows inside the chip's modal mount the shared preview modal, whose carousel
// wrapper needs layout APIs jsdom lacks.
vi.mock('@/components/ui/carousel', () => ({
  Carousel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselNext: () => <button type="button">next</button>,
  CarouselPrevious: () => <button type="button">prev</button>,
}));

vi.mock('../../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/projectService')
  >();
  return {
    ...actual,
    getProject: (...args: unknown[]) => getProject(...args),
    listQuotations: (...args: unknown[]) => listQuotations(...args),
    listQuotationVersions: (...args: unknown[]) => listQuotationVersions(...args),
    listQuotationLines: (...args: unknown[]) => listQuotationLines(...args),
    replaceQuotationLines: (...args: unknown[]) => replaceQuotationLines(...args),
    createQuotationLine: (...args: unknown[]) => createQuotationLine(...args),
    updateQuotationLine: (...args: unknown[]) => updateQuotationLine(...args),
    deleteQuotationLine: (...args: unknown[]) => deleteQuotationLine(...args),
    reviseQuotation: (...args: unknown[]) => reviseQuotation(...args),
    recomputeQuotationVersion: (...args: unknown[]) => recomputeQuotationVersion(...args),
  };
});

// Master data the line editor resolves a picked product through. Answered outright so nothing
// in these specs depends on a network shape that is not what they are about.
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForLineSelect: vi.fn(async () => []),
  getProductsForVariantSelect: vi.fn(async () => []),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({ data: [{ id: 'u1', uom_code: 'PCS', uom_name: 'Pieces' }] }),
}));

import { toast } from '@/lib/toast';
import { QuotationDocumentClient } from './QuotationDocumentClient';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationScopesTab } from './QuotationScopesTab';
import {
  QuotationSignaturesTab,
  QuotationCoverLetterTab,
  QuotationTermsTab,
} from './QuotationDocumentTabPanels';
import { QuotationHeaderTab } from './QuotationHeaderTab';

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
// signing gate is identical either way. The edit-view specs below opt into a scope.
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

function scope(overrides: Partial<QuotationScope> = {}): QuotationScope {
  return {
    id: 'q1',
    scope_label: 'Townhouse',
    sort_order: 1,
    outcome: 'open',
    current_version_id: 'v2',
    current_version_no: 2,
    line_count: 1,
    scope_total: '9000.00',
    ...overrides,
  };
}

function quotation(overrides: Partial<ProjectQuotation> = {}): ProjectQuotation {
  return {
    id: 'q1',
    project_id: 'p1',
    scope_label: 'Townhouse',
    outcome: 'open',
    version_count: 1,
    current_version_id: 'v2',
    current_version_no: 2,
    below_floor_count: 0,
    non_standard_count: 0,
    line_count: 1,
    ...overrides,
  };
}

function version(overrides: Partial<QuotationVersion> = {}): QuotationVersion {
  return {
    id: 'v2',
    quotation_id: 'q1',
    version_no: 2,
    is_current: true,
    is_editable: true,
    total_amount: '9000.00',
    ...overrides,
  };
}

function line(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 'l1',
    version_id: 'v2',
    product_code: 'SRT-WC-01',
    description: 'Wall-hung WC',
    unit_price: '900.00',
    quantity: '10.00',
    line_total: '9000.00',
    is_non_standard: false,
    is_below_floor: false,
    sort_order: 0,
    ...overrides,
  };
}

/**
 * The screen is a shell with a routed tab inside it, so a test renders the shell around whichever
 * tab it is making a claim about. The Scopes tab is the default route and therefore the default
 * here too.
 */
function renderScreen(tab: React.ReactNode = <QuotationScopesTab />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (openTab: React.ReactNode) => (
    <QueryClientProvider client={client}>
      <QuotationDocumentClient projectId="p1" documentId="d1">
        {openTab}
      </QuotationDocumentClient>
    </QueryClientProvider>
  );
  const result = render(ui(tab));
  return {
    ...result,
    /** A routed tab switch: the shell stays, the panel inside it unmounts and another mounts. */
    openTab: (next: React.ReactNode) => result.rerender(ui(next)),
  };
}

/** One scope, one line, and everything the edit view needs behind it. */
function seedOneScope(lines: QuotationLine[] = [line()]) {
  getQuotationDocument.mockResolvedValue(
    quotationDocument({ grand_total: '9000.00', scopes: [scope()] }),
  );
  listQuotations.mockResolvedValue([quotation()]);
  listQuotationVersions.mockResolvedValue([version()]);
  listQuotationLines.mockResolvedValue(lines);
  replaceQuotationLines.mockResolvedValue(lines);
}

/** The gear. Radix opens it on pointerDown, not click. */
async function openGear() {
  fireEvent.pointerDown(await screen.findByRole('button', { name: 'Proposal actions' }), {
    button: 0,
    ctrlKey: false,
  });
  return screen.findByRole('menu');
}

/**
 * Start an edit session.
 *
 * Two presses, not one: the client's rule for this header is ONE primary CTA with every other
 * action behind the gear ("edit should be in gear button"), and Issue is the CTA. Only the entry
 * point moved - once a session is open, Cancel and Save are the header's controls.
 */
async function pressEdit() {
  const menu = await openGear();
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit proposal' }));
  // Selecting an item closes the menu, which - like every Radix modal layer -
  // keeps `aria-hidden` over the rest of the page for as long as it stays
  // mounted for its own close animation (S8-01's shared spring, unlike the old
  // CSS transition, actually ticks in jsdom). Without this, every role query
  // right after `pressEdit()` comes back empty.
  await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
}

/**
 * True when the gear currently offers a way into an edit session.
 *
 * Closes the menu again before returning: Radix's dropdown is modal, so an open one puts
 * `aria-hidden` over the rest of the page and every later role query would come back empty.
 */
async function gearOffersEdit() {
  const menu = await openGear();
  const offered = within(menu).queryByRole('menuitem', { name: 'Edit proposal' }) !== null;
  fireEvent.keyDown(menu, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
  return offered;
}

beforeEach(() => {
  vi.clearAllMocks();
  granted = new Set();
  graphData = null;
  getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
  createPendingAction.mockImplementation(async (input: { entityId: string }) => ({
    id: `pa-${input.entityId}`,
    action_key: 'quotation_document.delete',
    entity_type: 'quotation_document',
    entity_id: input.entityId,
    commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''),
    window_seconds: 10,
  }));
  reviseQuotationApproval.mockResolvedValue(quotationDocument());
  moveQuotationApproval.mockResolvedValue(quotationDocument());
  approveQuotationDocument.mockResolvedValue(quotationDocument());
  rejectQuotationDocument.mockResolvedValue(quotationDocument());
  getProject.mockResolvedValue(project());
  listQuotations.mockResolvedValue([]);
  listQuotationIssues.mockResolvedValue([]);
  listQuotationVersions.mockResolvedValue([]);
  listQuotationLines.mockResolvedValue([]);
  updateQuotationDocument.mockResolvedValue(quotationDocument());
  reviseQuotation.mockResolvedValue(
    version({ id: 'v3', version_no: 3, is_current: true, is_editable: true }),
  );
  fetchDownloadsForEntity.mockResolvedValue({ downloads: [] });
  queueQuotationIssuePdf.mockResolvedValue({
    id: 'dl-pdf',
    kind: 'quotation_pdf',
    status: 'pending',
    filename: 'quotation-SRT-Q-2026-0141-R1.pdf',
    source_entity_type: 'quotation_issue',
    source_entity_id: 'i1',
  });
  queueQuotationIssueXlsx.mockResolvedValue({
    id: 'dl-xlsx',
    kind: 'quotation_xlsx',
    status: 'pending',
    filename: 'quotation-SRT-Q-2026-0141-R1.xlsx',
    source_entity_type: 'quotation_issue',
    source_entity_id: 'i1',
  });
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

/**
 * No repeated information under a page title (#1335). The page title is the document number and
 * the record header names the project, so neither is said a second time on the screen.
 */
describe('QuotationDocumentClient header dedupe', () => {
  // The number and project title specs live on the Header tab below ("#1336 kept, AC-QF054").
  it('leaves no subject read in the card, but keeps the Subject input in an edit session', () => {
    const { rerender } = render(<QuotationDocumentHeader document={quotationDocument()} />);
    expect(screen.queryByText('CADANGAN MEMBINA PANGSAPURI')).toBeNull();

    rerender(<QuotationDocumentHeader document={quotationDocument()} onChange={() => {}} />);
    expect(screen.getByLabelText('Project title')).toHaveValue('CADANGAN MEMBINA PANGSAPURI');
  });

  // PROPOSAL-FORM-COLLAPSE (owner, 10 Nov): a long Malay title overflowed the one-line input, so
  // the field is a wrapping textarea named for what it holds.
  it('edits the project title in a wrapping textarea, labelled Project title', () => {
    const onChange = vi.fn();
    render(<QuotationDocumentHeader document={quotationDocument()} onChange={onChange} />);
    const field = screen.getByLabelText('Project title');
    expect(field.tagName).toBe('TEXTAREA');
    expect(screen.queryByLabelText('Subject')).toBeNull();
    fireEvent.change(field, { target: { value: 'CADANGAN PEMBANGUNAN BERSTRATA 2 BLOK' } });
    expect(onChange).toHaveBeenCalledWith({ subject_title: 'CADANGAN PEMBANGUNAN BERSTRATA 2 BLOK' });
  });
});

describe('QuotationDocumentClient signing gate', () => {
  it('E4: offers Sign, not Send to Customer, until the quotation is signed', async () => {
    // Replaces "a disabled Send to Customer with a Sign it first title": the one primary button
    // is now the NEXT action, so an unsigned quotation leads with Sign.
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const sign = await screen.findByRole('button', { name: 'Sign' });
    expect(sign).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it('opens Issue once a signature is on the draft', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ signatory_signature: signature() }),
    );
    renderScreen();

    const issue = await screen.findByRole('button', { name: 'Send to Customer R1' });
    expect(issue).toBeEnabled();
    expect(screen.queryByText('Sign it first')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign' })).not.toBeInTheDocument();
  });

  it('PS-PROPOSAL-QUOTATION: the Send button names the next revision the server will stamp (C, not R3)', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        signatory_signature: signature(),
        current_issue_no: 2,
        next_revision_label: 'C',
      }),
    );
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Send to Customer C' })).toBeEnabled();
  });

  it('E1: below-floor pricing nobody has asked a manager about leads with Send for approval, never Send to Customer', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        signatory_signature: signature(),
        requires_approval: true,
        below_floor_line_count: 2,
        approval_status_key: null,
      }),
    );
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Send for approval' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it('leaves Issue alone once a manager has approved', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        signatory_signature: signature(),
        requires_approval: true,
        below_floor_line_count: 2,
        approval_status_key: 'approved',
      }),
    );
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Send to Customer R1' })).toBeEnabled();
  });

  it('E4: an issued document that carries no signature leads with Sign, not Send to Customer', async () => {
    // "It is issued, so it must have been signed" is wrong on every document issued before the
    // signature gate existed. Signed-ness is read off the signature and nothing else.
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

    expect(await screen.findByRole('button', { name: 'Sign' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it('shows the captured signature read-only in the signatures panel', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ signatory_signature: signature() }),
    );
    // The panel is the Signatures tab's now, so that is the tab this claim is made on. What it
    // asserts is unchanged: the ink, its metadata, and the customer half stating its own state.
    renderScreen(<QuotationSignaturesTab />);

    await waitFor(() => expect(screen.getByTestId('signature-pad-readonly')).toBeInTheDocument());
    // The pad labels the image from its heading, and the heading is who signed.
    expect(screen.getByRole('img', { name: 'Ahmad Faizal image' })).toHaveAttribute(
      'src',
      'data:image/png;base64,STUB',
    );
    expect(screen.getByText('203.0.113.9')).toBeInTheDocument();
    // The customer half still renders, stating its own resting state rather than vanishing.
    expect(
      screen.getByText(/Send this quotation to the customer to give them a link/i),
    ).toBeInTheDocument();
  });
});

describe('QuotationDocumentClient Edit quotation (#1341)', () => {
  it('AC-QF002: the gear offers Edit quotation, and it opens the form page', async () => {
    seedOneScope();
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    await pressEdit();

    expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/edit');
  });

  it('AC-QF004: the page is a read - no Save/Cancel pair, no letterhead inputs, no line editor', async () => {
    seedOneScope();
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    await pressEdit();

    expect(screen.queryByRole('button', { name: 'Save proposal' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    expect(screen.queryByLabelText('Your Ref')).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Edit line/i })).toBeNull();
  });

  it('keeps Edit out of the header, where the one CTA lives', async () => {
    seedOneScope();
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Sign' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it('AC-QF003: asks before revising a version the customer holds, then opens the form', async () => {
    seedOneScope();
    listQuotationVersions.mockResolvedValue([
      version({ is_issued: true, is_editable: false }),
    ]);
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '9000.00',
        scopes: [scope()],
        is_issued: true,
        issue_count: 1,
        current_issue_no: 1,
      }),
    );
    renderScreen();

    // The hint that used to say this is gone (owner, 5 Nov 2026); the prompt below says it.
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByText(/The customer holds/i)).toBeNull();

    await pressEdit();

    expect(await screen.findByText(/This version is with the customer/i)).toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Open a new version and edit' }));

    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledWith('q1'));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/edit'),
    );
  });

  it('does not offer a revision because ANOTHER document in the project is locked', async () => {
    // `listQuotations` answers every scope in the PROJECT. The document on screen is the only one
    // Edit may act on, so a clean draft goes straight to the form.
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ grand_total: '9000.00', scopes: [scope()] }),
    );
    listQuotations.mockResolvedValue([
      quotation(),
      quotation({ id: 'other-doc-scope', current_version_id: 'other-v1' }),
    ]);
    listQuotationVersions.mockImplementation((quotationId: string) =>
      Promise.resolve(
        quotationId === 'other-doc-scope'
          ? [version({ id: 'other-v1', is_issued: true, is_editable: false })]
          : [version()],
      ),
    );
    listQuotationLines.mockResolvedValue([line()]);
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    await pressEdit();

    expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/edit');
    expect(screen.queryByText(/This version is with the customer/i)).not.toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();
  });

  it('offers no Edit to a reader', async () => {
    seedOneScope();
    getProject.mockResolvedValue(project({ can_edit: false }));
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(await gearOffersEdit()).toBe(false);
    expect(
      screen.getByText('You can read this quotation but not change it.'),
    ).toBeInTheDocument();
  });
});

/** The letterhead on the read page. Its editing moved to the form page (#1341). */
describe('QuotationDocumentClient letterhead', () => {
  it('shows the values and nowhere to type, even after Edit is pressed', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ your_ref: 'NCSB/2026/117' }),
    );
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('NCSB/2026/117')).toBeInTheDocument();
    await pressEdit();
    expect(screen.queryByLabelText('Your Ref')).toBeNull();
    expect(screen.queryByLabelText('Attn')).toBeNull();
    expect(screen.queryByLabelText('Address')).toBeNull();
    expect(updateQuotationDocument).not.toHaveBeenCalled();
  });

  it('reads a multi-line address back a line at a time', async () => {
    // The display half of the same round trip, made on the header alone: one stored string, one
    // paragraph per line, which is what the printed letterhead does with it.
    render(
      <QuotationDocumentHeader
        document={quotationDocument({
          recipient_address_snapshot: 'Level 12, Menara Nadi\nJalan Ampang\n50450 Kuala Lumpur',
        })}
      />,
    );

    expect(screen.getByText('Level 12, Menara Nadi')).toBeInTheDocument();
    expect(screen.getByText('Jalan Ampang')).toBeInTheDocument();
    expect(screen.getByText('50450 Kuala Lumpur')).toBeInTheDocument();
  });

  it('offers a reader no letterhead inputs', async () => {
    getProject.mockResolvedValue(project({ can_edit: false }));
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen(<QuotationHeaderTab />);

    // The record's own subtitle and the letterhead both name the recipient, so both answer here.
    await waitFor(() =>
      expect(screen.getAllByText('Nadi Cergas Sdn Bhd').length).toBeGreaterThan(0),
    );
    expect(await gearOffersEdit()).toBe(false);
    expect(screen.queryByLabelText('Your Ref')).toBeNull();
  });
});

/**
 * The two exports going asynchronous, which is the client's complaint answered: pressing Download
 * PDF used to hold the browser for as long as WeasyPrint took on a fifty-page quotation, and a
 * dead-looking button is what they reported.
 *
 * So the claims are that the gear now QUEUES and says where the file will be, that it fetches no
 * bytes and creates no blob on the way past, and that the header carries the printer chip the file
 * is actually collected from - keyed to the revision, not to some invented id.
 */
describe('QuotationDocumentClient queued exports', () => {
  const issue = {
    id: 'i1',
    document_id: 'd1',
    issue_no: 1,
    our_ref_text: 'SRT/Q/2026/0141 (R1)',
    issued_at: '2026-08-04T02:00:00',
    issued_by: 'u1',
    issued_by_name: 'Ahmad',
    grand_total: '9000.00',
    scope_count: 1,
  };

  /** An issued, signed document, which is the only state the exports are offered in. */
  function seedIssued() {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        is_issued: true,
        issue_count: 1,
        current_issue_no: 1,
        signatory_signature: signature(),
      }),
    );
    listQuotationIssues.mockResolvedValue([issue]);
  }

  it('queues the PDF and names where it will land, fetching no bytes', async () => {
    seedIssued();
    renderScreen();
    const menu = await openGear();

    // The menu itself sets the expectation before the click, because the click no longer produces
    // a file in front of the user.
    // Once per export, PDF and Excel, because each one lands somewhere the click does not show.
    expect(within(menu).getAllByText('Prepared in My Downloads')).toHaveLength(2);

    fireEvent.click(within(menu).getByText('Download PDF'));

    await waitFor(() =>
      expect(queueQuotationIssuePdf).toHaveBeenCalledWith('p1', 'd1', 'i1'),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'Preparing the PDF. It will appear in My Downloads.',
      ),
    );
    // No blob dance: nothing was saved to disk and no tab was opened behind the user's back.
    expect(queueQuotationIssueXlsx).not.toHaveBeenCalled();
  });

  it('queues the Excel file the same way, as its own row', async () => {
    seedIssued();
    renderScreen();
    const menu = await openGear();

    fireEvent.click(within(menu).getByText('Download Excel'));

    await waitFor(() =>
      expect(queueQuotationIssueXlsx).toHaveBeenCalledWith('p1', 'd1', 'i1'),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'Preparing the Excel file. It will appear in My Downloads.',
      ),
    );
    expect(queueQuotationIssuePdf).not.toHaveBeenCalled();
  });

  it('reports the server refusal rather than a silent nothing', async () => {
    // The failure the user will actually meet is a queue that cannot be reached. Swallowed, the
    // click looks exactly like a successful one, which is the worst of both designs.
    seedIssued();
    queueQuotationIssuePdf.mockRejectedValue(
      new Error('Could not queue the export. Please try again.'),
    );
    renderScreen();
    const menu = await openGear();

    fireEvent.click(within(menu).getByText('Download PDF'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Could not queue the export. Please try again.',
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('offers no export on a draft, and says why', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();
    const menu = await openGear();

    expect(within(menu).getAllByText('Send it to the customer first').length).toBeGreaterThan(0);
    fireEvent.click(within(menu).getByText('Download PDF'));
    expect(queueQuotationIssuePdf).not.toHaveBeenCalled();
  });

  it('carries the printer chip for the issued revision, and only once issued', async () => {
    // The chip IS the collection point, keyed to the revision the exports belong to. A draft has
    // no revision, so there is nothing for it to count and it is not rendered.
    getQuotationDocument.mockResolvedValue(quotationDocument());
    const { unmount } = renderScreen();
    await screen.findByRole('button', { name: 'Proposal actions' });
    expect(fetchDownloadsForEntity).not.toHaveBeenCalled();
    unmount();

    seedIssued();
    fetchDownloadsForEntity.mockResolvedValue({
      downloads: [
        {
          id: 'dl-pdf',
          kind: 'quotation_pdf',
          status: 'ready',
          filename: 'quotation-SRT-Q-2026-0141-R1.pdf',
          created_at: '2026-08-05T02:00:00Z',
        },
      ],
    });
    renderScreen();

    await waitFor(() =>
      expect(fetchDownloadsForEntity).toHaveBeenCalledWith('quotation_issue', 'i1', 100),
    );
    // Named after the revision, never after a raw id: the chip's tooltip is read by a person.
    const chip = await screen.findByTitle('View downloads for SRT/Q/2026/0141 (R1)');
    fireEvent.click(chip);

    expect(
      await screen.findByText('quotation-SRT-Q-2026-0141-R1.pdf'),
    ).toBeInTheDocument();
    // And it is previewable from there, which is the other half of what the client asked for.
    expect(screen.getByRole('button', { name: /^Preview/ })).toBeInTheDocument();
  });

  it('borders the chip exactly the way the complaint header does', async () => {
    // The client: "the download should have border just like complaint, we should use the same
    // exact element". It always WAS the same component - the complaint header passes
    // `h-8 border border-border` and this one passed nothing, so it read as unclickable beside
    // the bordered buttons next to it. Same three classes, same call site shape.
    seedIssued();
    renderScreen();

    const chip = await screen.findByTitle('View downloads for SRT/Q/2026/0141 (R1)');
    expect(chip).toHaveClass('h-8');
    expect(chip).toHaveClass('border');
    expect(chip).toHaveClass('border-border');
  });
});

/**
 * S17's other half: the salesperson finding out.
 *
 * The client sent a screenshot of their own request on the counter-sign page and asked "when i
 * request changes, how can i see it from the system?" - which is the question of somebody who
 * went looking and could not find it. It was on the Signatures tab, and a tab the salesperson has
 * no reason to open is not where "the customer has asked for something" belongs.
 *
 * So the claims are: it is on the document without opening anything, it carries the customer's
 * OWN WORDS (the words are the whole point), it offers the next move as a click into the EXISTING
 * revise flow rather than a second one, and acceptance beats it on this surface exactly as it
 * already does on the counter-sign page and the Signatures badge.
 */
describe('QuotationDocumentClient change request', () => {
  const NOTE = 'can you provide me more discount';

  /** An issued quotation, frozen with the customer, that they have answered. */
  function seedAnswered(overrides: Partial<QuotationDocument> = {}) {
    seedOneScope();
    listQuotationVersions.mockResolvedValue([version({ is_editable: false })]);
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '9000.00',
        scopes: [scope()],
        is_issued: true,
        issue_count: 1,
        current_issue_no: 1,
        signatory_signature: signature(),
        customer_decision: 'changes_requested',
        changes_requested_at: '2026-08-06T02:15:00',
        changes_requested_note: NOTE,
        changes_requested_by_name: 'Kelly',
        ...overrides,
      }),
    );
  }

  it('says so on the document itself, in the customer own words', async () => {
    seedAnswered();
    renderScreen();

    // No tab opened, no gear pressed: it is on the page the salesperson already landed on.
    expect(await screen.findByText(NOTE)).toBeInTheDocument();
    // Who said it and when, because "somebody asked for something" is not actionable.
    expect(screen.getByText(/Kelly asked for changes/i)).toBeInTheDocument();
    expect(screen.getByText(/06\/08\/2026/)).toBeInTheDocument();
  });

  it('renders nothing at all on a quotation nobody has answered', async () => {
    // The ordinary quotation gains no chrome, the same way the price-floor panel behaves.
    seedAnswered({
      customer_decision: null,
      changes_requested_at: null,
      changes_requested_note: null,
      changes_requested_by_name: null,
    });
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByText(NOTE)).toBeNull();
    expect(screen.queryByText(/asked for changes/i)).toBeNull();
  });

  it('stands down once the customer signed, even with the words still on record', async () => {
    // Acceptance wins on EVERY surface. A banner nagging somebody to revise a quotation that is
    // already won contradicts the counter-sign page the customer is looking at.
    seedAnswered({ customer_decision: 'accepted', accepted_at: '2026-08-06T04:00:00' });
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByText(NOTE)).toBeNull();
    expect(screen.queryByText(/asked for changes/i)).toBeNull();
  });

  it('leads into the EXISTING revise prompt rather than dead-ending', async () => {
    // Not a second revise control: the button is the same entry point Edit uses, so a revision
    // is still something the salesperson is asked about rather than something that appears.
    //
    // And deliberately not labelled "Revise to v3" - the Scopes tab already carries a per-scope
    // button by that name, and two identically-worded controls acting on different things is
    // exactly the confusion the header rules exist to prevent.
    seedAnswered();
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Revise this quotation' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Revise this quotation' }));

    expect(await screen.findByText(/This version is with the customer/i)).toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Open a new version and edit' }));

    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledWith('q1'));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/edit'),
    );
  });

  it('gives a reader the words but no way to act on them', async () => {
    seedAnswered();
    getProject.mockResolvedValue(project({ can_edit: false }));
    renderScreen();

    expect(await screen.findByText(NOTE)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Revise/ })).toBeNull();
  });
});

/**
 * The badge beside the reference, which has to agree with the project's quotation list.
 *
 * Reported from the running system: the list said "Accepted" and the document said "Issued" for
 * the same record. `quotationStanding` was written precisely so those two surfaces could not
 * disagree, and the header simply never used it - it kept its own `is_issued ? Issued : Draft`.
 * These pin the header to the shared reading.
 */
describe('QuotationDocumentClient standing badge', () => {
  function seedWithDecision(overrides: Partial<QuotationDocument>) {
    seedOneScope();
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '9000.00',
        scopes: [scope()],
        is_issued: true,
        issue_count: 1,
        current_issue_no: 1,
        signatory_signature: signature(),
        ...overrides,
      }),
    );
  }

  it('reads Accepted, not Issued, once the customer has signed', async () => {
    seedWithDecision({ customer_decision: 'accepted', accepted_at: '2026-08-06T02:15:00' });
    renderScreen();

    expect(await screen.findByText('Accepted')).toBeInTheDocument();
    // The bug in one line: both words on screen at once is the disagreement, not a richer label.
    expect(screen.queryByText('Issued')).toBeNull();
  });

  it('reads Changes requested while the customer is waiting on a revision', async () => {
    seedWithDecision({
      customer_decision: 'changes_requested',
      changes_requested_at: '2026-08-06T02:15:00',
      changes_requested_note: 'cheaper please',
    });
    renderScreen();

    expect(await screen.findByText('Changes requested')).toBeInTheDocument();
    expect(screen.queryByText('Issued')).toBeNull();
  });

  it('still reads Issued when the customer has not answered', async () => {
    seedWithDecision({ customer_decision: null });
    renderScreen();

    expect(await screen.findByText('Issued')).toBeInTheDocument();
  });

  it('reads Draft before anything has been issued', async () => {
    seedWithDecision({ is_issued: false, issue_count: 0, current_issue_no: null });
    renderScreen();

    expect(await screen.findByText('Draft')).toBeInTheDocument();
  });
});

/**
 * The series a scope is quoted from has to be REACHABLE, and visible.
 *
 * This is the defect these tests exist for. The picker was only ever on the per-scope page,
 * and once this document screen replaced that page as the way in, nothing linked to it: the
 * one control deciding whether a line counts as standard could not be reached by clicking.
 * The result was measurable - `series_id` was NULL on every quotation in the database, so
 * nothing was checked and every Non-standard flag on screen was a stale leftover.
 *
 * A dead link cannot be caught by a test of the dialog, only by a test that starts where the
 * user starts.
 */
describe('QuotationDocumentClient scope series', () => {
  it('AC-QF004: offers no per-scope Edit scope, and no Record outcome (owner, 5 Nov 2026)', async () => {
    // The owner: "editing of scope should be done by 'Edit Quotation', not a separate button".
    // Record outcome left the page too: "we only need per project outcome" (its own lane).
    seedOneScope();
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Record outcome' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit scope' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a scope' })).toBeNull();
    expect(
      screen
        .queryAllByText(/^(Won|Lost|Open|Still open)$/)
        .filter((el) => el.className.includes('rounded-full')),
    ).toHaveLength(0);
    expect(screen.queryByRole('dialog', { name: /Outcome of/ })).toBeNull();
  });

  it('AC-QF036: an empty scope reads as an empty grid, with no Press Edit hint', async () => {
    seedOneScope([]);
    renderScreen();

    expect(await screen.findByText(/No lines yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Press Edit/i)).toBeNull();
  });

  it('a quotation with no scopes offers Edit quotation as its next step', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ scopes: [] }));
    renderScreen();

    const link = await screen.findByRole('link', { name: 'Edit quotation' });
    expect(link).toHaveAttribute('href', '/project-sales/p1/quotation-documents/d1/edit');
    expect(screen.queryByRole('button', { name: 'Add a scope' })).toBeNull();
  });

  // The area header row that named the series is gone in view (owner, 5 Nov 2026: "in view i
  // don't even need this"); the series still shows on the form page.
  it('names no series above the lines in view, even when one is bound', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ grand_total: '9000.00', scopes: [scope()] }),
    );
    listQuotations.mockResolvedValue([
      quotation({ series_id: 's1', series_name: 'Sanitaryware template' }),
    ]);
    listQuotationVersions.mockResolvedValue([version()]);
    listQuotationLines.mockResolvedValue([line()]);
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByText('Sanitaryware template')).toBeNull();
    expect(screen.queryByText('No series')).toBeNull();
  });
});

/**
 * Fix round 2 (#1341, owner addenda 2 to 4 and the 11:33Z alignment notes).
 */
describe('QuotationDocumentClient Send to Customer (AC-QF057)', () => {
  it('names the primary CTA Send to Customer, with the revision it will send', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ signatory_signature: signature() }),
    );
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Send to Customer R1' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^Issue/ })).toBeNull();
  });

  it('says Send it to the customer first on the exports of a draft, never Issue it first', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const menu = await openGear();
    expect(within(menu).getAllByText('Send it to the customer first').length).toBeGreaterThan(0);
    expect(within(menu).queryByText('Issue it first')).toBeNull();
  });
});

describe('QuotationDocumentClient Header details (AC-QF052)', () => {
  it('puts Issued by and Opened in the Header tab, once, for a one-scope quotation', async () => {
    seedOneScope();
    listQuotationVersions.mockResolvedValue([
      version({ issued_by_name: 'Baser Ramli', created_at: '2026-09-28T02:30:00' }),
    ]);
    renderScreen(<QuotationHeaderTab />);

    const card = await screen.findByTestId('quotation-header-card');
    await waitFor(() => expect(card).toHaveTextContent('Issued by'));
    expect(card).toHaveTextContent('Baser Ramli');
    expect(card).toHaveTextContent('Opened');
    expect(within(card).getAllByText('Issued by')).toHaveLength(1);
  });

  // QUOTE-HEADER-TIDY (owner, 11 Nov 2026: "don't need to be by unit here"): one pair for the
  // document, the most recently opened ISSUED area version's, never one group per area.
  it('shows one Issued by and Opened for the document, not one per area', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        scopes: [
          scope(),
          scope({ id: 'q2', scope_label: 'Guard House', current_version_id: 'v9' }),
          scope({ id: 'q3', scope_label: 'Level 9', current_version_id: 'v10' }),
        ],
      }),
    );
    listQuotations.mockResolvedValue([
      quotation(),
      quotation({ id: 'q2', scope_label: 'Guard House', current_version_id: 'v9' }),
      quotation({ id: 'q3', scope_label: 'Level 9', current_version_id: 'v10' }),
    ]);
    listQuotationVersions.mockImplementation((quotationId: string) =>
      Promise.resolve(
        quotationId === 'q2'
          ? [
              version({
                id: 'v9',
                quotation_id: 'q2',
                version_no: 1,
                is_issued: true,
                issued_by_name: 'Kelly Tan',
                created_at: '2026-11-03T02:00:00',
              }),
            ]
          : quotationId === 'q3'
            ? [
                // Opened most recently, but never issued: an issued version wins over it.
                version({
                  id: 'v10',
                  quotation_id: 'q3',
                  version_no: 1,
                  is_issued: false,
                  issued_by_name: 'Siti Aminah',
                  created_at: '2026-11-09T02:00:00',
                }),
              ]
            : [
                version({
                  is_issued: true,
                  issued_by_name: 'Baser Ramli',
                  created_at: '2026-11-01T02:00:00',
                }),
              ],
      ),
    );
    renderScreen(<QuotationHeaderTab />);

    const card = await screen.findByTestId('quotation-header-card');
    await waitFor(() => expect(card).toHaveTextContent('Kelly Tan'));
    expect(within(card).getAllByText('Issued by')).toHaveLength(1);
    expect(within(card).getAllByText('Opened')).toHaveLength(1);
    expect(card).not.toHaveTextContent('Baser Ramli');
    expect(card).not.toHaveTextContent('Siti Aminah');
    expect(within(card).queryByRole('group')).toBeNull();
    expect(card).not.toHaveTextContent('Guard House v1');
    expect(card).not.toHaveTextContent('Townhouse v2');
  });

  it('falls back to the most recently opened area when none is issued', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        scopes: [scope(), scope({ id: 'q2', scope_label: 'Guard House', current_version_id: 'v9' })],
      }),
    );
    listQuotations.mockResolvedValue([
      quotation(),
      quotation({ id: 'q2', scope_label: 'Guard House', current_version_id: 'v9' }),
    ]);
    listQuotationVersions.mockImplementation((quotationId: string) =>
      Promise.resolve(
        quotationId === 'q2'
          ? [
              version({
                id: 'v9',
                quotation_id: 'q2',
                version_no: 1,
                issued_by_name: 'Kelly Tan',
                created_at: '2026-11-05T02:00:00',
              }),
            ]
          : [version({ issued_by_name: 'Baser Ramli', created_at: '2026-11-01T02:00:00' })],
      ),
    );
    renderScreen(<QuotationHeaderTab />);

    const card = await screen.findByTestId('quotation-header-card');
    await waitFor(() => expect(card).toHaveTextContent('Kelly Tan'));
    expect(within(card).getAllByText('Issued by')).toHaveLength(1);
    expect(card).not.toHaveTextContent('Baser Ramli');
  });

  it('leaves no Issued by / Opened strip above the lines table', async () => {
    seedOneScope();
    listQuotationVersions.mockResolvedValue([
      version({ issued_by_name: 'Baser Ramli', created_at: '2026-09-28T02:30:00' }),
    ]);
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByText(/Issued by/)).toBeNull();
    expect(screen.queryByText(/^Opened/)).toBeNull();
  });
});

describe('QuotationDocumentClient header dedupe (#1336 kept, AC-QF054)', () => {
  // Superseded by PROPOSAL-HEADER-LAYOUT (owner, 5 Nov 2026: "it should be like order
  // inquiry"): the record card leads with the number, as Order Inquiry does, and the title is
  // its subtitle line.
  // QUOTE-HEADER-TIDY (owner, 11 Nov 2026): the record card names the project by its short
  // name (PROJECT-NAME, `projects.name`); the full title moves into the Header section.
  it('leads the record card with the document number, the project name under it', async () => {
    getProject.mockResolvedValue(project({ name: 'Menara Ujian' }));
    getQuotationDocument.mockResolvedValue(quotationDocument({ our_ref: 'NCSB-OURS-1' }));
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('NCSB-OURS-1')).toBeInTheDocument();
    const card = screen.getByTestId('record-header-card');
    expect(within(card).getByRole('heading', { name: 'SRT/Q/2026/0141' })).toBeInTheDocument();
    expect(within(card).getByText('Menara Ujian')).toBeInTheDocument();
    expect(within(card).queryByText('CADANGAN MEMBINA PANGSAPURI')).toBeNull();
    expect(within(card).getByText('Draft')).toBeInTheDocument();
  });

  it('falls back to the project title in the record card when the project has no name', async () => {
    getProject.mockResolvedValue(project({ name: null }));
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen(<QuotationHeaderTab />);

    const card = await screen.findByTestId('record-header-card');
    expect(within(card).getByText('Menara Test')).toBeInTheDocument();
  });

  it('shows the full project title as a Project row in the Header section', async () => {
    getProject.mockResolvedValue(project({ name: 'Menara Ujian' }));
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen(<QuotationHeaderTab />);

    const header = await screen.findByTestId('quotation-header-card');
    expect(within(header).getByText('Project')).toBeInTheDocument();
    expect(within(header).getByText('CADANGAN MEMBINA PANGSAPURI')).toBeInTheDocument();
    expect(screen.getAllByText('CADANGAN MEMBINA PANGSAPURI')).toHaveLength(1);
  });
});

// QUOTE-HEADER-TIDY (owner, 11 Nov 2026: "even in view the header and line should be
// collapsible"): the same fold the edit form uses, open on arrival.
describe('QuotationDocumentClient view folds (QUOTE-HEADER-TIDY)', () => {
  it('folds and unfolds the Header and the Lines in view mode', async () => {
    seedOneScope();
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.getByTestId('quotation-header-card')).toBeInTheDocument();

    const headerToggle = screen.getByRole('button', { name: /^Header/ });
    const linesToggle = screen.getByRole('button', { name: /^Lines/ });
    expect(headerToggle).toHaveAttribute('aria-expanded', 'true');
    expect(linesToggle).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(headerToggle);
    await waitFor(() => expect(screen.queryByTestId('quotation-header-card')).toBeNull());
    // Folded, the one-line summary stands in: To, title, date, total.
    expect(headerToggle).toHaveTextContent('Nadi Cergas Sdn Bhd');
    expect(headerToggle).toHaveTextContent('RM');

    fireEvent.click(linesToggle);
    await waitFor(() => expect(screen.queryByText('Wall-hung WC')).toBeNull());
    expect(linesToggle).toHaveTextContent('1 scope');

    fireEvent.click(headerToggle);
    fireEvent.click(linesToggle);
    expect(await screen.findByTestId('quotation-header-card')).toBeInTheDocument();
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
  });
});


// ---------------------------------------------------------------------------------------------
// QUOTE-APPROVAL-UX (15 Oct 2026): one primary CTA = the next action; locked while Pending or
// Approved with an explicit Revise; the page leads back to the Quotations tab.
// ---------------------------------------------------------------------------------------------

/** The seeded `quotation` graph: Send for approval is the draft -> pending_approval edge. */
function approvalGraph(sendLabel = 'Send for approval'): StatusGraph {
  const rungs = [
    { key: 'draft', label: 'Draft', sort_order: 0, is_initial: true },
    { key: 'rejected', label: 'Rejected', sort_order: 1, is_initial: false },
    { key: 'pending_approval', label: 'Pending Approval', sort_order: 2, is_initial: false },
    { key: 'resubmitted', label: 'Appealed', sort_order: 2, is_initial: false },
    { key: 'approved', label: 'Approved', sort_order: 3, is_initial: false },
    { key: 'issued', label: 'Issued', sort_order: 4, is_initial: false },
  ];
  const statuses = rungs.map((rung) => ({
    id: `s-${rung.key}`,
    entity_type: 'quotation',
    scope_id: null,
    key: rung.key,
    label: rung.label,
    category: null,
    color_hex: null,
    description: null,
    sort_order: rung.sort_order,
    is_initial: rung.is_initial,
    is_terminal: false,
    is_active: true,
    is_archived: false,
    is_default: rung.is_initial,
    is_system: false,
  }));
  const edges = [
    ['draft', 'pending_approval', sendLabel, 0],
    ['pending_approval', 'approved', 'Approve', 0],
    ['pending_approval', 'rejected', 'Reject', 1],
    ['rejected', 'draft', 'Back to draft', 0],
    ['approved', 'issued', 'Issued to the customer', 0],
    ['issued', 'pending_approval', 'Send for approval', 0],
    ['draft', 'resubmitted', 'Appeal', 1],
    ['resubmitted', 'approved', 'Approve', 0],
    ['resubmitted', 'rejected', 'Reject', 1],
  ] as const;
  return {
    entity_type: 'quotation',
    requested_scope_id: null,
    resolved_scope_id: null,
    is_fork: false,
    statuses,
    transitions: edges.map(([from, to, label, sort_order], index) => ({
      id: `t${index}`,
      entity_type: 'quotation',
      scope_id: null,
      from_status_id: `s-${from}`,
      to_status_id: `s-${to}`,
      label,
      sort_order,
      trigger_mode: 'manual' as const,
      conditions_json: null,
    })),
  };
}

/** A quotation with lines below the floor, standing on the given approval rung. */
function belowFloor(
  rung: string | null,
  overrides: Partial<QuotationDocument> = {},
): QuotationDocument {
  return quotationDocument({
    requires_approval: true,
    below_floor_line_count: 2,
    approval_status_key: rung,
    approval_status_id: rung ? `s-${rung}` : null,
    ...overrides,
  });
}

/** Every button whose variant is `primary` (the filled one); Reject and the rest are outline. */
function primaryButtons() {
  return screen.getAllByRole('button').filter((button) => button.classList.contains('bg-primary'));
}

async function screenReady() {
  await screen.findByRole('button', { name: 'Proposal actions' });
}

describe('QuotationDocumentClient: one primary CTA (E1-E9)', () => {
  it.each([
    ['no rung', null, false],
    ['draft', 'draft', false],
    ['issued', 'issued', true],
  ])('E1: below floor on %s leads with Send for approval and renders no Send to Customer', async (_name, rung, issued) => {
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(
      belowFloor(rung, {
        signatory_signature: signature(),
        is_issued: issued,
        current_issue_no: issued ? 1 : null,
        issue_count: issued ? 1 : 0,
      }),
    );
    renderScreen();

    const send = await screen.findByRole('button', { name: 'Send for approval' });
    expect(send).toBeEnabled();
    expect(primaryButtons()).toEqual([send]);
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it('E1: an UNSIGNED below-floor draft leads with Send for approval; Sign is not a primary button', async () => {
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('draft'));
    renderScreen();

    const send = await screen.findByRole('button', { name: 'Send for approval' });
    expect(primaryButtons()).toEqual([send]);
    expect(
      screen.queryAllByRole('button', { name: 'Sign' }).filter((b) => b.classList.contains('bg-primary')),
    ).toHaveLength(0);
    const menu = await openGear();
    expect(within(menu).getByRole('menuitem', { name: /Sign proposal/ })).toBeInTheDocument();
  });

  it('E1: the label comes off the graph edge, and falls back to Send for approval with no graph', async () => {
    graphData = approvalGraph('Ask a manager');
    getQuotationDocument.mockResolvedValue(belowFloor('draft', { signatory_signature: signature() }));
    const { unmount } = renderScreen();

    expect(await screen.findByRole('button', { name: 'Ask a manager' })).toBeInTheDocument();
    unmount();

    graphData = null;
    renderScreen();
    expect(await screen.findByRole('button', { name: 'Send for approval' })).toBeInTheDocument();
  });

  it('E1: pressing it moves the quotation along the draft to pending edge', async () => {
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('draft', { signatory_signature: signature() }));
    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: 'Send for approval' }));

    await waitFor(() =>
      expect(moveQuotationApproval).toHaveBeenCalledWith('p1', 'd1', 's-pending_approval'),
    );
  });

  it('C3: a rejected quotation shows the reason and leads with Appeal, with no Back to draft anywhere', async () => {
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(
      belowFloor('rejected', {
        signatory_signature: signature(),
        approval_rejected_reason: 'Bring the WC suite back to RM 240.',
      }),
    );
    renderScreen();

    // RESUBMITTED-STATUS: the label comes off the draft -> resubmitted edge.
    const send = await screen.findByRole('button', { name: 'Appeal' });
    expect(screen.getByText(/Bring the WC suite back to RM 240\./)).toBeInTheDocument();
    expect(screen.queryByText(/Back to draft/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /Back to draft/i })).toBeNull();

    // Straight from Rejected: the press targets the pending rung (the server walks the graph).
    fireEvent.click(send);
    await waitFor(() =>
      expect(moveQuotationApproval).toHaveBeenCalledWith('p1', 'd1', 's-pending_approval'),
    );
  });

  it('a manager on a resubmitted quotation decides it like a pending one (RESUBMITTED-STATUS)', async () => {
    granted = new Set(['projects.quotations.approve']);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('resubmitted'));
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
  });

  it('E2: a manager on a pending quotation gets Approve (primary) and Reject (outline) in the header only', async () => {
    granted = new Set(['projects.quotations.approve']);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('pending_approval'));
    renderScreen();

    const approve = await screen.findByRole('button', { name: 'Approve' });
    const reject = screen.getByRole('button', { name: 'Reject' });
    expect(primaryButtons()).toEqual([approve]);
    expect(reject.classList.contains('bg-primary')).toBe(false);
    // Not repeated in the banner.
    expect(screen.getAllByRole('button', { name: 'Approve' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Reject' })).toHaveLength(1);

    fireEvent.click(approve);
    await waitFor(() => expect(approveQuotationDocument).toHaveBeenCalledWith('p1', 'd1'));
  });

  it('PS-QUOTE-RULES: a grant holder the request is NOT routed to is not offered Approve or Reject', async () => {
    granted = new Set(['projects.quotations.approve']);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(
      belowFloor('pending_approval', { viewer_may_decide: false }),
    );
    renderScreen();

    expect((await screen.findAllByText(/for approval/i)).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('E2: Reject asks for a reason before it can be sent', async () => {
    granted = new Set(['projects.quotations.approve']);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('pending_approval'));
    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    expect(screen.getByRole('button', { name: 'Send it back' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Why/i), { target: { value: '  Bring it back.  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send it back' }));

    await waitFor(() =>
      expect(rejectQuotationDocument).toHaveBeenCalledWith('p1', 'd1', 'Bring it back.'),
    );
  });

  it('E3: a salesperson on a pending quotation who has not signed gets Sign', async () => {
    getQuotationDocument.mockResolvedValue(belowFloor('pending_approval'));
    renderScreen();

    const sign = await screen.findByRole('button', { name: 'Sign' });
    expect(primaryButtons()).toEqual([sign]);
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it('E3: once signed there is no primary button, only "With a manager for approval"', async () => {
    getQuotationDocument.mockResolvedValue(
      belowFloor('pending_approval', { signatory_signature: signature() }),
    );
    renderScreen();

    await screenReady();
    expect(await screen.findByText('With a manager for approval')).toBeInTheDocument();
    expect(primaryButtons()).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it.each([
    ['nothing below the floor', () => quotationDocument()],
    ['approved', () => belowFloor('approved')],
  ])('E4: %s and unsigned leads with Sign and renders no Send to Customer', async (_name, make) => {
    getQuotationDocument.mockResolvedValue(make());
    renderScreen();

    const sign = await screen.findByRole('button', { name: 'Sign' });
    expect(primaryButtons()).toEqual([sign]);
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
  });

  it.each([
    ['nothing below the floor', () => quotationDocument({ signatory_signature: signature() }), 'R1'],
    ['approved', () => belowFloor('approved', { signatory_signature: signature() }), 'R1'],
    [
      'approved on an issued document',
      () =>
        belowFloor('approved', {
          signatory_signature: signature(),
          is_issued: true,
          current_issue_no: 2,
          issue_count: 2,
        }),
      'R3',
    ],
  ])('E5: %s and signed leads with an enabled Send to Customer %s', async (_name, make, revision) => {
    getQuotationDocument.mockResolvedValue(make());
    renderScreen();

    const send = await screen.findByRole('button', { name: `Send to Customer ${revision}` });
    expect(send).toBeEnabled();
    expect(primaryButtons()).toEqual([send]);
  });

  it.each([
    ['draft below floor, unsigned', () => belowFloor('draft'), []],
    ['pending, unsigned, as manager', () => belowFloor('pending_approval'), ['projects.quotations.approve']],
    ['pending, signed, as manager', () => belowFloor('pending_approval', { signatory_signature: signature() }), ['projects.quotations.approve']],
    ['rejected, unsigned', () => belowFloor('rejected'), []],
    ['approved, unsigned', () => belowFloor('approved'), []],
    ['approved, signed', () => belowFloor('approved', { signatory_signature: signature() }), []],
  ])('E6: at most one primary button in %s', async (_name, make, grants) => {
    granted = new Set(grants);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(make());
    renderScreen();

    await screenReady();
    await waitFor(() => expect(primaryButtons().length).toBeGreaterThan(0));
    expect(primaryButtons()).toHaveLength(1);
  });

  it('E7: the gear keeps Sign again, Edit, both downloads, the counter-sign link and Delete', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ signatory_signature: signature() }));
    renderScreen();

    const menu = await openGear();
    for (const name of [
      'Sign again',
      'Edit proposal',
      'Download PDF',
      'Download Excel',
      'Copy counter-sign link',
      'Delete proposal',
    ]) {
      expect(within(menu).getByRole('menuitem', { name: new RegExp(name) })).toBeInTheDocument();
    }
  });

  it('E7: an unsigned quotation reads Sign quotation in the gear', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const menu = await openGear();
    expect(within(menu).getByRole('menuitem', { name: /Sign proposal/ })).toBeInTheDocument();
  });

  it('E8: the approval banner states the situation and holds no buttons', async () => {
    granted = new Set(['projects.quotations.approve']);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('pending_approval'));
    renderScreen();

    const sentence = await screen.findByText(/2 lines are priced below minimum price/i);
    const banner = sentence.closest('div.rounded-lg') as HTMLElement;
    expect(banner).not.toBeNull();
    expect(within(banner).queryByRole('button')).toBeNull();
  });

  it.each([
    ['pending below floor', () => belowFloor('pending_approval', { signatory_signature: signature() })],
    ['draft below floor', () => belowFloor('draft', { signatory_signature: signature() })],
    ['draft, nothing below floor, signed', () => quotationDocument({ signatory_signature: signature() })],
  ])('E9: a reader without edit rights and without the grant sees no primary button (%s)', async (_name, make) => {
    getProject.mockResolvedValue(project({ can_edit: false }));
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(make());
    renderScreen();

    expect(
      await screen.findByText('You can read this quotation but not change it.'),
    ).toBeInTheDocument();
    expect(primaryButtons()).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /^Send to Customer/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Send for approval' })).toBeNull();
  });
});

/** The header chip: the PR/SF pill (rounded-full, font-semibold) carrying the given words. */
async function headerPill(label: string) {
  await screenReady();
  return await waitFor(() => {
    const hit = screen
      .getAllByText(label)
      .find((el) => el.classList.contains('rounded-full') && el.classList.contains('font-semibold'));
    if (!hit) throw new Error(`no pill reading ${label}`);
    return hit;
  });
}

describe('QuotationDocumentClient: status chip is the shared PR/SF pill (A1-A5)', () => {
  it.each([
    ['pending_approval', 'Pending approval', ['bg-amber-100', 'text-amber-800']],
    ['approved', 'Approved', ['bg-blue-100', 'text-blue-800']],
    ['rejected', 'Rejected', ['bg-red-100', 'text-red-800']],
    ['draft', 'Draft', ['bg-muted', 'text-muted-foreground']],
  ])('chip: the %s rung reads "%s" on the pill palette', async (rung, label, classes) => {
    getQuotationDocument.mockResolvedValue(belowFloor(rung));
    renderScreen();

    const pill = await headerPill(label);
    for (const cls of classes) expect(pill.classList.contains(cls)).toBe(true);
  });

  it.each([
    ['Issued', { is_issued: true, current_issue_no: 1, issue_count: 1 }, 'bg-emerald-100', 'text-emerald-800'],
    ['Accepted', { is_issued: true, current_issue_no: 1, issue_count: 1, customer_decision: 'accepted' as const }, 'bg-emerald-100', 'text-emerald-800'],
    ['Changes requested', { is_issued: true, current_issue_no: 1, issue_count: 1, customer_decision: 'changes_requested' as const }, 'bg-amber-100', 'text-amber-800'],
  ])('chip: %s uses the shared pill colours', async (label, overrides, bg, text) => {
    getQuotationDocument.mockResolvedValue(quotationDocument(overrides));
    renderScreen();

    const pill = await headerPill(label);
    expect(pill.classList.contains(bg)).toBe(true);
    expect(pill.classList.contains(text)).toBe(true);
  });
});

describe('QuotationDocumentClient: locked while Pending or Approved, explicit Revise (D6-D7)', () => {
  it.each(['pending_approval', 'approved'])(
    'D6: Edit quotation on a %s quotation asks for a reason and calls Revise before opening the form',
    async (rung) => {
      seedOneScope();
      getQuotationDocument.mockResolvedValue(
        belowFloor(rung, { grand_total: '9000.00', scopes: [scope()] }),
      );
      renderScreen();

      expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
      await pressEdit();

      // The prompt, not the form.
      expect(push).not.toHaveBeenCalled();
      const reason = await screen.findByLabelText('What changed, and why?');
      const revise = screen.getByRole('button', { name: 'Revise' });
      expect(revise).toBeDisabled();

      fireEvent.change(reason, { target: { value: '   ' } });
      expect(screen.getByRole('button', { name: 'Revise' })).toBeDisabled();

      fireEvent.change(reason, { target: { value: 'Customer re-scoped the towers' } });
      expect(screen.getByRole('button', { name: 'Revise' })).toBeEnabled();
      fireEvent.click(screen.getByRole('button', { name: 'Revise' }));

      await waitFor(() =>
        expect(reviseQuotationApproval).toHaveBeenCalledWith(
          'p1',
          'd1',
          'Customer re-scoped the towers',
        ),
      );
      await waitFor(() =>
        expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/edit'),
      );
    },
  );

  it('D6: a draft quotation still goes straight to the form, with no prompt', async () => {
    seedOneScope();
    getQuotationDocument.mockResolvedValue(
      belowFloor('draft', { grand_total: '9000.00', scopes: [scope()] }),
    );
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    await pressEdit();

    expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/edit');
    expect(screen.queryByLabelText('What changed, and why?')).toBeNull();
    expect(reviseQuotationApproval).not.toHaveBeenCalled();
  });

  // Revise to vN moved into the gear (PROPOSAL-HEADER-LAYOUT); the locked half is H10.
  it('D6: the gear offers Revise to vN on a draft', async () => {
    seedOneScope();
    getQuotationDocument.mockResolvedValue(
      belowFloor('draft', { grand_total: '9000.00', scopes: [scope()] }),
    );
    renderScreen();
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Revise to v3' })).toBeInTheDocument(),
    );
  });

  it('D7: after Revise the chip reads Draft and the primary button reads Send for approval', async () => {
    graphData = approvalGraph();
    seedOneScope();
    const pending = belowFloor('pending_approval', {
      grand_total: '9000.00',
      scopes: [scope()],
      signatory_signature: signature(),
    });
    getQuotationDocument.mockResolvedValue(pending);
    reviseQuotationApproval.mockImplementation(async () => {
      const revised = belowFloor('draft', {
        grand_total: '9000.00',
        scopes: [scope()],
        signatory_signature: signature(),
      });
      getQuotationDocument.mockResolvedValue(revised);
      return revised;
    });
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    await pressEdit();
    fireEvent.change(await screen.findByLabelText('What changed, and why?'), {
      target: { value: 'Re-priced the WC suite' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Revise' }));

    await waitFor(() => expect(reviseQuotationApproval).toHaveBeenCalled());
    await waitFor(async () => expect(await headerPill('Draft')).toBeInTheDocument());
    expect(await screen.findByRole('button', { name: 'Send for approval' })).toBeEnabled();
  });
});

describe('QuotationDocumentClient: Delete is the deferred countdown (F7)', () => {
  it('F7: the record gear Delete parks quotation_document.delete and opens no confirmation dialog', async () => {
    granted = new Set(['projects.projects.delete']);
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const menu = await openGear();
    fireEvent.click(within(menu).getByRole('menuitem', { name: /Delete proposal/ }));

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'quotation_document.delete',
        entityType: 'quotation_document',
        entityId: 'd1',
      }),
    );
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByText('Confirm delete')).toBeNull();
  });

  it('F7: neither the quotation page nor the panel imports ConfirmDeleteDialog any more', () => {
    const here = __dirname;
    const page = readFileSync(resolve(here, 'QuotationDocumentClient.tsx'), 'utf8');
    const panel = readFileSync(resolve(here, '../../../components/QuotationsPanel.tsx'), 'utf8');
    expect(page).not.toContain('ConfirmDeleteDialog');
    expect(panel).not.toContain('ConfirmDeleteDialog');
  });
});


describe('QuotationDocumentClient: fix round 2', () => {
  it('2: a failed Reject keeps the dialog open, the reason typed, and shows the error in the dialog', async () => {
    granted = new Set(['projects.quotations.approve']);
    graphData = approvalGraph();
    getQuotationDocument.mockResolvedValue(belowFloor('pending_approval'));
    rejectQuotationDocument.mockRejectedValue(new Error('Server says no'));
    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    fireEvent.change(screen.getByLabelText(/Why/i), { target: { value: 'Bring it back.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send it back' }));

    await waitFor(() => expect(rejectQuotationDocument).toHaveBeenCalled());
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText(/Why/i)).toHaveValue('Bring it back.');
    expect(await within(dialog).findByText(/Server says no/)).toBeInTheDocument();
  });

  it.each(['pending_approval', 'approved'])(
    '3: no Recheck alerts button on the Lines tab while %s',
    async (rung) => {
      seedOneScope();
      getQuotationDocument.mockResolvedValue(
        belowFloor(rung, { grand_total: '9000.00', scopes: [scope()] }),
      );
      renderScreen();

      expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Recheck alerts/i })).toBeNull();
    },
  );

  it('3: a draft still offers Recheck alerts', async () => {
    seedOneScope();
    getQuotationDocument.mockResolvedValue(
      belowFloor('draft', { grand_total: '9000.00', scopes: [scope()] }),
    );
    renderScreen();

    // A gear item now (PROPOSAL-HEADER-LAYOUT), no longer a button above the lines.
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Recheck alerts' })).toBeInTheDocument(),
    );
  });

  it('6: gear Delete shows the countdown INLINE in the header, not only a toast', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const menu = await openGear();
    fireEvent.click(within(menu).getByRole('menuitem', { name: /Delete proposal/ }));

    expect(await screen.findByTestId('deferred-countdown')).toBeInTheDocument();
  });

  it('6: a delete already running for this document shows its countdown on mount', async () => {
    getCurrentPendingAction.mockResolvedValue({
      pending: {
        id: 'pa-running',
        action_key: 'quotation_document.delete',
        entity_type: 'quotation_document',
        entity_id: 'd1',
        commit_at: new Date(Date.now() + 8_000).toISOString().replace(/\.\d+Z$/, ''),
        window_seconds: 10,
      },
      last_outcome: null,
    });
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    expect(await screen.findByTestId('deferred-countdown')).toBeInTheDocument();
    expect(createPendingAction).not.toHaveBeenCalled();
  });
});


// ---------------------------------------------------------------------------------------------
// QUOTE-SEND-WHATSAPP (UAC section E): Send to Customer offers Email or WhatsApp.
// ---------------------------------------------------------------------------------------------

describe('QuotationDocumentClient Send to Customer channel menu (QUOTE-SEND-WHATSAPP)', () => {
  const sentIssue = {
    id: 'i1',
    document_id: 'd1',
    issue_no: 1,
    our_ref_text: 'SRT/Q/2026/0141 (R1)',
    issued_at: '2026-10-30T02:00:00',
    issued_by: 'u1',
    issued_by_name: 'SALES REP A',
    grand_total: '0.00',
    scope_count: 0,
  };

  async function openSendMenu() {
    const user = userEvent.setup();
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ signatory_signature: signature() }),
    );
    issueQuotationDocument.mockResolvedValue(sentIssue);
    createQuotationSignLink.mockResolvedValue({
      token: 'tok',
      path: '/quotation-sign/tok',
      expires_at: null,
    });
    renderScreen();
    await user.click(await screen.findByRole('button', { name: 'Send to Customer R1' }));
    return user;
  }

  it('E1: pressing the button sends nothing yet and offers Email and WhatsApp', async () => {
    await openSendMenu();
    expect(await screen.findByRole('menuitem', { name: 'Email' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'WhatsApp' })).toBeInTheDocument();
    expect(issueQuotationDocument).not.toHaveBeenCalled();
  });

  it('E1: closing the menu with Escape sends nothing', async () => {
    const user = await openSendMenu();
    await screen.findByRole('menu');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    expect(issueQuotationDocument).not.toHaveBeenCalled();
  });

  it('E2: Email sends once and opens no WhatsApp prompt', async () => {
    const user = await openSendMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Email' }));
    await waitFor(() => expect(issueQuotationDocument).toHaveBeenCalledTimes(1));
    expect(issueQuotationDocument).toHaveBeenCalledWith('p1', 'd1');
    expect(screen.queryByText('Send R1 via WhatsApp')).toBeNull();
  });

  it('E2: Email confirms with the sent-to-customer toast', async () => {
    const user = await openSendMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Email' }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Sent to the customer as SRT/Q/2026/0141 (R1)'),
    );
  });

  it('E3: WhatsApp sends once, then opens the prompt for the returned revision', async () => {
    const user = await openSendMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'WhatsApp' }));
    await waitFor(() => expect(issueQuotationDocument).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Send R1 via WhatsApp')).toBeInTheDocument();
  });

  it('E4: a failed send opens no prompt', async () => {
    const user = await openSendMenu();
    issueQuotationDocument.mockRejectedValue(new Error('refused'));
    await user.click(await screen.findByRole('menuitem', { name: 'WhatsApp' }));
    await waitFor(() => expect(issueQuotationDocument).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByText('Send R1 via WhatsApp')).toBeNull();
  });
});

/**
 * QUOTE-COVER-PAGE (UAC B1): the view page shows the four new fields where the edit form has them.
 * Header tab: Email, Quotation Purpose, Prepared By (the project salesperson). Terms tab: Payment
 * Terms and Validity above the terms.
 */
describe('QuotationDocumentClient cover page fields', () => {
  const coverDocument = () =>
    quotationDocument({
      terms_html: '<p>CLAUSE A</p>',
      ...({
        recipient_email_snapshot: 'kelly@example.test',
        quotation_purpose: 'Supply of sanitary ware',
        payment_terms: '30 days net',
        validity: '60 days',
        prepared_by: 'Ahmad Faizal',
      } as unknown as Partial<QuotationDocument>),
    });

  it('the Header tab shows Email and Prepared By, and no Quotation Purpose', async () => {
    getQuotationDocument.mockResolvedValue(coverDocument());
    getProject.mockResolvedValue(project({ owner_name: 'Wrong Project Owner' }));
    renderScreen(<QuotationHeaderTab />);

    const card = await screen.findByTestId('quotation-header-card');
    await waitFor(() => expect(card).toHaveTextContent('kelly@example.test'));
    expect(card).toHaveTextContent('Email');
    // Removed (owner, 10 Nov 2026): a stored value no longer shows.
    expect(card).not.toHaveTextContent('Quotation Purpose');
    expect(card).not.toHaveTextContent('Supply of sanitary ware');
    expect(card).toHaveTextContent('Prepared By');
    expect(card).toHaveTextContent('Ahmad Faizal');
    expect(card).not.toHaveTextContent('Wrong Project Owner');
  });

  it('the Terms tab shows Payment Terms and Validity with the terms', async () => {
    getQuotationDocument.mockResolvedValue(coverDocument());
    renderScreen(<QuotationTermsTab />);

    expect(await screen.findByText('Payment Terms')).toBeInTheDocument();
    expect(screen.getByText('30 days net')).toBeInTheDocument();
    expect(screen.getByText('Validity')).toBeInTheDocument();
    expect(screen.getByText('60 days')).toBeInTheDocument();
    expect(screen.getByText('CLAUSE A')).toBeInTheDocument();
  });

  it('an old quotation with none of the fields shows no empty Email or Validity row', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ terms_html: '<p>CLAUSE A</p>' }));
    renderScreen(<QuotationTermsTab />);

    expect(await screen.findByText('CLAUSE A')).toBeInTheDocument();
    expect(screen.queryByText('Validity')).toBeNull();
    expect(screen.queryByText('Payment Terms')).toBeNull();
  });

  it('polish: the read Terms panel carries every TERMS_HTML_CLASS token and no prose', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        terms_html: '<p>CLAUSE A</p><p></p><ul><li>OUTER ITEM<ul><li>INNER ITEM</li></ul></li></ul>',
      }),
    );
    renderScreen(<QuotationTermsTab />);

    const inner = await screen.findByText('INNER ITEM');
    await expectTermsClass(inner);
  });

  it('the Cover letter read tab shows the preview card with the intro and no separate letter panel', async () => {
    coverPreview.mockReset();
    coverPreview.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            cover_title: 'QUOTATION',
            cover_show_letterhead: true,
            cover_rows: [{ key: 'reference', label: 'Reference No.', text: 'SRT/Q/2026/0141-R1 Menara Test' }],
            cover_intro_html: '<p>LETTER ONE</p><p>LETTER TWO</p>',
            cover_closing_html: '',
            sender_name: 'Sorento Sdn Bhd',
            sender_logo_url: null,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
    );
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ cover_letter_html: '<p>LETTER ONE</p><p>LETTER TWO</p>' }),
    );
    renderScreen(<QuotationCoverLetterTab />);

    expect(await screen.findByText('LETTER ONE')).toBeInTheDocument();
    expect(screen.getByText('LETTER TWO')).toBeInTheDocument();
    expect(screen.getAllByText('LETTER ONE')).toHaveLength(1);
    expect(screen.queryByText('Cover letter', { selector: '[data-slot="card-title"]' })).toBeNull();
  });

  it('polish 2: the Email line comes before the Attn line in the To block', async () => {
    getQuotationDocument.mockResolvedValue(coverDocument());
    renderScreen(<QuotationHeaderTab />);

    const email = await screen.findByText('Email:');
    const attn = screen.getByText('Attn:');
    expect(
      email.compareDocumentPosition(attn) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('polish: Email shows inline in the To block as "Email:" then the address, like Attn', async () => {
    getQuotationDocument.mockResolvedValue(coverDocument());
    renderScreen(<QuotationHeaderTab />);

    const label = await screen.findByText('Email:');
    expect(label.parentElement).toHaveTextContent('Email: kelly@example.test');
    expect(screen.queryByText('Email')).toBeNull();
  });
});

/** The countersign terms row and the read view share one class constant (QUOTE-COVER-PAGE polish). */
async function expectTermsClass(inner: HTMLElement) {
  const loaders = import.meta.glob('/lib/terms-html.ts') as Record<string, () => Promise<{ TERMS_HTML_CLASS: string }>>;
  const load = loaders['/lib/terms-html.ts'];
  expect(load, 'lib/terms-html.ts must export TERMS_HTML_CLASS').toBeDefined();
  const { TERMS_HTML_CLASS } = await load();
  const tokens = String(TERMS_HTML_CLASS).split(/\s+/).filter(Boolean);
  expect(tokens.length).toBeGreaterThan(0);
  const chain: HTMLElement[] = [];
  for (let el = inner.parentElement; el && el !== document.body && chain.length < 6; el = el.parentElement) {
    chain.push(el);
  }
  expect(
    chain.some((el) => tokens.every((token) => el.classList.contains(token))),
  ).toBe(true);
  expect(chain.some((el) => el.classList.contains('prose'))).toBe(false);
}


/** QUOTE-COVER-DESIGN (UAC B2, B3): the read Cover letter tab is the preview card, no editors. */
describe('Cover letter tab preview (read)', () => {
  it('renders the design title and rows from the preview endpoint and no editors', async () => {
    coverPreview.mockReset();
    coverPreview.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            cover_title: 'OFFER SHEET',
            cover_show_letterhead: false,
            cover_rows: [{ key: 'reference', label: 'Offer Number', text: 'SRT/Q/2026/0141-R1 Menara Test' }],
            cover_intro_html: '<p>LETTER AS INTRO</p>',
            cover_closing_html: '',
            sender_name: 'Sorento Sdn Bhd',
            sender_logo_url: null,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
    );
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ cover_letter_html: '<p>LETTER AS INTRO</p>' }),
    );
    renderScreen(<QuotationCoverLetterTab />);

    expect(await screen.findByText('OFFER SHEET')).toBeInTheDocument();
    expect(screen.getByText('Offer Number')).toBeInTheDocument();
    expect(screen.getByText('LETTER AS INTRO')).toBeInTheDocument();
    expect(screen.queryByText('Quotation from')).toBeNull();
    expect(screen.queryByLabelText('Intro text')).toBeNull();
    expect(screen.queryByLabelText('Closing text')).toBeNull();
    const body = JSON.parse(String((coverPreview.mock.calls[0][1] as RequestInit).body));
    expect(body).toMatchObject({ document_id: 'd1' });
  });
});

// ---------------------------------------------------------------------------------------------
// PROPOSAL-HEADER-LAYOUT (owner, 5 Nov 2026; mock documentation/plans/project-sales/mockups/
// proposal-header-layout-05nov.html v4): the record header is the Order Inquiry card, the lines
// sit on the Header tab, and the per-area / per-version rows above the lines are gone.
// ---------------------------------------------------------------------------------------------
describe('QuotationDocumentClient: header like Order Inquiry (PROPOSAL-HEADER-LAYOUT)', () => {
  const issuedOneScope = () => {
    seedOneScope();
    listQuotationVersions.mockResolvedValue([version({ is_issued: true, is_editable: false })]);
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '9000.00',
        scopes: [scope()],
        is_issued: true,
        issue_count: 2,
        current_issue_no: 2,
        customer_decision: 'accepted',
        signatory_signature: signature(),
      }),
    );
    listQuotationIssues.mockResolvedValue([
      {
        id: 'i2',
        document_id: 'd1',
        issue_no: 2,
        our_ref_text: 'SRT/Q/2026/0141-R2',
        issued_at: '2026-11-05T02:00:00',
        issued_by: 'u1',
        issued_by_name: 'Ahmad',
        grand_total: '9000.00',
        scope_count: 1,
      },
    ]);
  };

  async function headerCard() {
    return screen.findByTestId('record-header-card');
  }

  it('H1: the document number and the status pill share the card title row', async () => {
    issuedOneScope();
    renderScreen(<QuotationHeaderTab />);

    const row = within(await headerCard()).getByTestId('record-header-title-row');
    expect(within(row).getByText('SRT/Q/2026/0141')).toBeInTheDocument();
    expect(within(row).getByText('Accepted')).toBeInTheDocument();
  });

  it('H2: no customer line in the header card (the letterhead To says it)', async () => {
    issuedOneScope();
    renderScreen(<QuotationHeaderTab />);

    const card = await headerCard();
    expect(within(card).getByText('CADANGAN MEMBINA PANGSAPURI')).toBeInTheDocument();
    expect(within(card).queryByText('Nadi Cergas Sdn Bhd')).toBeNull();
  });

  it('H3: neither copy of "the customer holds this version" hint is shown', async () => {
    issuedOneScope();
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByText(/The customer holds/i)).toBeNull();
    expect(screen.queryByText(/Edit opens the next/i)).toBeNull();
  });

  it('H4: actions read gear, printer, primary, left to right', async () => {
    issuedOneScope();
    renderScreen(<QuotationHeaderTab />);

    const gear = await screen.findByRole('button', { name: 'Proposal actions' });
    const printer = await screen.findByTitle('View downloads for SRT/Q/2026/0141-R2');
    const send = await screen.findByRole('button', { name: /^Send to Customer/ });
    expect(gear.compareDocumentPosition(printer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(printer.compareDocumentPosition(send) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('H5: the Header tab carries the letterhead AND the lines; there is no Lines tab', async () => {
    seedOneScope();
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.getByText('Our Ref')).toBeInTheDocument();
    const strip = screen.getByTestId('quotation-document-tab-strip');
    expect(within(strip).getByRole('tab', { name: /Header/ })).toBeInTheDocument();
    expect(within(strip).queryByRole('tab', { name: /^Lines$/ })).toBeNull();
  });

  it('H6: no area header row and no Record outcome anywhere on the page (owner 12:20, 12:28)', async () => {
    seedOneScope();
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Record outcome/ })).toBeNull();
    expect(screen.queryByText('No series')).toBeNull();
    const menu = await openGear();
    expect(within(menu).queryByRole('menuitem', { name: /outcome/i })).toBeNull();
  });

  it('H7: the version is a chip in the header card, and the version row above the lines is gone', async () => {
    seedOneScope();
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    const row = within(await headerCard()).getByTestId('record-header-title-row');
    expect(await within(row).findByText('v2')).toBeInTheDocument();
    // The old pills were buttons carrying aria-current; none remain below the card.
    expect(screen.queryAllByRole('button', { name: /^v\d/ }).filter((b) => b.hasAttribute('aria-current'))).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /Recheck alerts/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Revise to v/ })).toBeNull();
  });

  it('H8: with two versions the chip switches the lines to the frozen one', async () => {
    seedOneScope();
    listQuotationVersions.mockResolvedValue([
      version(),
      version({ id: 'v1', version_no: 1, is_current: false, is_editable: false }),
    ]);
    listQuotationLines.mockImplementation(async (versionId: string) =>
      versionId === 'v1'
        ? [line({ id: 'l0', version_id: 'v1', description: 'Old WC' })]
        : [line()],
    );
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    const chip = await screen.findByRole('button', { name: /^Version v2/ });
    fireEvent.pointerDown(chip, { button: 0, ctrlKey: false });
    const menu = await screen.findByRole('menu');
    fireEvent.click(within(menu).getByRole('menuitem', { name: /v1 \(frozen\)/ }));

    expect(await screen.findByText('Old WC')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /^Version v1 \(frozen\)/ })).toBeInTheDocument();
  });

  it('H9: Recheck alerts and Revise to vN are gear items; Revise asks first, then revises every area', async () => {
    seedOneScope();
    renderScreen(<QuotationHeaderTab />);
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();

    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Recheck alerts' })).toBeInTheDocument(),
    );
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revise to v3' }));

    expect(await screen.findByRole('heading', { name: 'Revise to v3' })).toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Freeze v2 and continue' }));
    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledWith('q1'));
  });

  it('H10: while locked for approval the gear offers no Revise to vN and no Recheck alerts', async () => {
    seedOneScope();
    getQuotationDocument.mockResolvedValue(
      belowFloor('pending_approval', { grand_total: '9000.00', scopes: [scope()] }),
    );
    renderScreen(<QuotationHeaderTab />);
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();

    const menu = await openGear();
    expect(within(menu).queryByRole('menuitem', { name: /Revise to v/ })).toBeNull();
    expect(within(menu).queryByRole('menuitem', { name: 'Recheck alerts' })).toBeNull();
  });

  it('H11: two hints are two lines in the card, never joined with a middle dot', async () => {
    // A reader (no edit right) on a quotation waiting for a manager: both hints apply.
    getProject.mockResolvedValue(project({ can_edit: false }));
    getQuotationDocument.mockResolvedValue(
      belowFloor('pending_approval', { signatory_signature: signature() }),
    );
    renderScreen(<QuotationHeaderTab />);

    const card = await headerCard();
    await within(card).findByText('With a manager for approval');
    const lines = within(card)
      .getAllByTestId('record-header-subtitle')
      .map((el) => el.textContent);
    expect(lines).toContain('You can read this quotation but not change it.');
    expect(lines).toContain('With a manager for approval');
    expect(card.textContent).not.toContain('·');
  });

  /** Two areas, Townhouse (q1) and Semi-D (q2), each at the given current version. */
  function seedTwoAreas(townhouseNo = 2, semiNo = 2) {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '18000.00',
        scopes: [
          scope({ current_version_id: 'v2', current_version_no: townhouseNo }),
          scope({
            id: 'q2',
            scope_label: 'Semi-D',
            sort_order: 2,
            current_version_id: 'w2',
            current_version_no: semiNo,
          }),
        ],
      }),
    );
    listQuotations.mockResolvedValue([
      quotation({ current_version_no: townhouseNo }),
      quotation({
        id: 'q2',
        scope_label: 'Semi-D',
        current_version_id: 'w2',
        current_version_no: semiNo,
      }),
    ]);
    listQuotationVersions.mockImplementation(async (quotationId: string) =>
      quotationId === 'q2'
        ? [version({ id: 'w2', quotation_id: 'q2', version_no: semiNo })]
        : [version({ version_no: townhouseNo })],
    );
    listQuotationLines.mockResolvedValue([line()]);
  }

  it('H12: Revise to vN revises EVERY area, one after the other', async () => {
    seedTwoAreas();
    renderScreen(<QuotationHeaderTab />);
    expect((await screen.findAllByText('Wall-hung WC')).length).toBeGreaterThan(0);

    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Revise to v3' })).toBeInTheDocument(),
    );
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revise to v3' }));
    expect(await screen.findByText(/v2 of all 2 areas is frozen for good/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Freeze v2 and continue' }));

    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledTimes(2));
    expect(reviseQuotation.mock.calls.map((call) => call[0])).toEqual(['q1', 'q2']);
  });

  it('H13: a retry after one area failed does not revise the area that already moved', async () => {
    seedTwoAreas();
    reviseQuotation
      .mockResolvedValueOnce(version({ id: 'v3', version_no: 3 }))
      .mockRejectedValueOnce(new Error('Conflict'))
      .mockResolvedValueOnce(version({ id: 'w3', quotation_id: 'q2', version_no: 3 }));
    renderScreen(<QuotationHeaderTab />);
    expect((await screen.findAllByText('Wall-hung WC')).length).toBeGreaterThan(0);

    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Revise to v3' })).toBeInTheDocument(),
    );
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revise to v3' }));
    const freeze = await screen.findByRole('button', { name: /Freeze .*and continue/ });
    fireEvent.click(freeze);
    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledTimes(2));
    // Still open after the failure; try again.
    fireEvent.click(await screen.findByRole('button', { name: /Freeze .*and continue/ }));
    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledTimes(3));
    expect(reviseQuotation.mock.calls.map((call) => call[0])).toEqual(['q1', 'q2', 'q2']);
  });

  it('H14: areas on different versions: the dialog says what happens to each one', async () => {
    seedTwoAreas(2, 1);
    renderScreen(<QuotationHeaderTab />);
    expect((await screen.findAllByText('Wall-hung WC')).length).toBeGreaterThan(0);

    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Revise every area' })).toBeInTheDocument(),
    );
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Revise every area' }));
    expect(
      await screen.findByText(/Townhouse v2 to v3, Semi-D v1 to v2/),
    ).toBeInTheDocument();
  });

  it('H15: Recheck alerts rechecks every open area, once each', async () => {
    seedTwoAreas();
    recomputeQuotationVersion.mockImplementation(async (versionId: string) => ({
      version_id: versionId,
      version_no: 2,
      quotation_id: versionId === 'w2' ? 'q2' : 'q1',
      line_count: 1,
      changed_count: 0,
      now_non_standard: 0,
      no_longer_non_standard: 0,
      now_below_floor: 0,
      no_longer_below_floor: 0,
      floor_changed: 0,
      unresolved_products: 0,
      changed_lines: [],
    }));
    renderScreen(<QuotationHeaderTab />);
    expect((await screen.findAllByText('Wall-hung WC')).length).toBeGreaterThan(0);

    const menu = await openGear();
    await waitFor(() =>
      expect(within(menu).getByRole('menuitem', { name: 'Recheck alerts' })).toBeInTheDocument(),
    );
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Recheck alerts' }));
    await waitFor(() => expect(recomputeQuotationVersion).toHaveBeenCalledTimes(2));
    expect(recomputeQuotationVersion.mock.calls.map((call) => call[0]).sort()).toEqual(['v2', 'w2']);
  });
});
