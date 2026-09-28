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
 * button is gone while Record outcome stays.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
  },
}));

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
const push = vi.fn();

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
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  useHasAnyPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

// The approval graph is one install-wide read the block uses to name the salesperson's next
// move. Empty here: with nothing below the floor the block never renders at all.
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
    updateQuotationDocument: (...args: unknown[]) => updateQuotationDocument(...args),
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
import { QuotationHeaderTab, QuotationSignaturesTab } from './QuotationDocumentTabPanels';

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
  fireEvent.pointerDown(await screen.findByRole('button', { name: 'Quotation actions' }), {
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
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit quotation' }));
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
  const offered = within(menu).queryByRole('menuitem', { name: 'Edit quotation' }) !== null;
  fireEvent.keyDown(menu, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
  return offered;
}

beforeEach(() => {
  vi.clearAllMocks();
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
    expect(screen.getByLabelText('Subject')).toHaveValue('CADANGAN MEMBINA PANGSAPURI');
  });
});

describe('QuotationDocumentClient signing gate', () => {
  it('refuses to offer Issue until the quotation is signed, and says why', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen();

    const issue = await screen.findByRole('button', { name: 'Send to Customer R1' });
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

    const issue = await screen.findByRole('button', { name: 'Send to Customer R1' });
    expect(issue).toBeEnabled();
    expect(screen.queryByText('Sign it first')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign' })).not.toBeInTheDocument();
  });

  it('holds Issue shut while below-floor pricing is waiting on a manager, and says why', async () => {
    // S15's half of the same gate. Signed is not enough: the server refuses a below-floor
    // quotation with 422 `quotation_below_floor_pending_approval`, so the CTA says so up front
    // rather than letting somebody press it and read an error.
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        signatory_signature: signature(),
        requires_approval: true,
        below_floor_line_count: 2,
        approval_status_key: null,
      }),
    );
    renderScreen();

    const issue = await screen.findByRole('button', { name: 'Send to Customer R1' });
    expect(issue).toBeDisabled();
    expect(issue).toHaveAttribute(
      'title',
      'A manager has to approve the below-floor pricing first',
    );
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

    const issue = await screen.findByRole('button', { name: 'Send to Customer R2' });
    expect(issue).toBeDisabled();
    expect(issue).toHaveAttribute('title', 'Sign it first');
    // And the way out is offered, not just the refusal.
    expect(screen.getByRole('button', { name: 'Sign' })).toBeEnabled();
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

    expect(screen.queryByRole('button', { name: 'Save quotation' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    expect(screen.queryByLabelText('Your Ref')).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Edit line/i })).toBeNull();
  });

  it('keeps Edit out of the header, where the one CTA lives', async () => {
    seedOneScope();
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Send to Customer R1' })).toBeInTheDocument();
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

    expect(
      await screen.findByText(/The customer holds this version\. Edit opens the next one\./i),
    ).toBeInTheDocument();

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
    await screen.findByRole('button', { name: 'Quotation actions' });
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
  it('AC-QF004: offers no per-scope Edit scope; Record outcome stays', async () => {
    // The owner: "editing of scope should be done by 'Edit Quotation', not a separate button".
    seedOneScope();
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Record outcome' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit scope' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a scope' })).toBeNull();
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

  it('says which series the scope is quoted from', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ grand_total: '9000.00', scopes: [scope()] }),
    );
    listQuotations.mockResolvedValue([
      quotation({ series_id: 's1', series_name: 'Sanitaryware template' }),
    ]);
    listQuotationVersions.mockResolvedValue([version()]);
    listQuotationLines.mockResolvedValue([line()]);
    renderScreen();

    expect(await screen.findByText('Sanitaryware template')).toBeInTheDocument();
  });

  it('says NO series when none is bound, rather than looking identically clean', async () => {
    // The state the whole database was in. A scope checking nothing and a scope whose lines
    // are all standard render the same lines; only this tells them apart.
    seedOneScope();
    renderScreen();

    expect(await screen.findByText('No series')).toBeInTheDocument();
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

  it('groups them by scope when the scopes were opened by different people', async () => {
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
          ? [version({ id: 'v9', quotation_id: 'q2', version_no: 1, issued_by_name: 'Kelly Tan' })]
          : [version({ issued_by_name: 'Baser Ramli' })],
      ),
    );
    renderScreen(<QuotationHeaderTab />);

    const card = await screen.findByTestId('quotation-header-card');
    await waitFor(() => expect(card).toHaveTextContent('Kelly Tan'));
    const townhouse = within(card).getByRole('group', { name: 'Townhouse v2' });
    const guard = within(card).getByRole('group', { name: 'Guard House v1' });
    expect(townhouse).toHaveTextContent('Baser Ramli');
    expect(guard).toHaveTextContent('Kelly Tan');
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
  it('does not repeat the document number under the breadcrumb', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument({ our_ref: 'NCSB-OURS-1' }));
    renderScreen(<QuotationHeaderTab />);

    expect(await screen.findByText('NCSB-OURS-1')).toBeInTheDocument();
    expect(screen.queryByText('SRT/Q/2026/0141')).toBeNull();
    expect(
      screen.getByRole('heading', { level: 2, name: 'CADANGAN MEMBINA PANGSAPURI' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Draft')).toBeInTheDocument();
  });

  it('says the project title once, in the record header, not again in the Header tab card', async () => {
    getQuotationDocument.mockResolvedValue(quotationDocument());
    renderScreen(<QuotationHeaderTab />);

    expect(
      await screen.findByRole('heading', { level: 2, name: 'CADANGAN MEMBINA PANGSAPURI' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('CADANGAN MEMBINA PANGSAPURI')).toHaveLength(1);
  });
});
