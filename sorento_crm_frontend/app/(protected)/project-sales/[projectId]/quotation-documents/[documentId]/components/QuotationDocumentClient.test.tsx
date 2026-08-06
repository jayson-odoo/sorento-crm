/**
 * S7 + S11 - the quotation document shell: the signing gate, and the edit view.
 *
 * Two things are pinned here.
 *
 * The signing gate is the ONE rule the server enforces with a 422: an unsigned document cannot be
 * issued (AC-H1). The screen has to say so before the click, not after, and the reason has to be
 * readable rather than hidden in a tooltip.
 *
 * The edit view is S11, and it is the client's complaint answered: "every addition of line doesn't
 * trigger a save, cause now i delete each line, then you ask me to confirm, then when i add line,
 * you also trigger save, very annoying". So the claims are that a whole session of edits is ONE
 * write, that Cancel puts everything back, that a tab switch loses nothing, that the confirmation
 * happens once at Save and names the count, and that Edit on a version the customer holds reaches
 * a revision only after being asked.
 *
 * The line editor is NOT stubbed for those: the whole point is the chain from a keystroke in a
 * cell to a single request, and a stub in the middle would prove none of it.
 *
 * The last block is the letterhead becoming editable, which is the client's next sentence: "when we
 * are in edit view right, we need to be able to edit these also, like the header details, your ref,
 * date, to, attn". Its claims are that the block is a read until Edit, that what is typed there
 * rides the SAME one Save as the lines, that Cancel puts the letterhead back too, and that the
 * address survives being multi-line.
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

vi.mock('sonner', () => ({
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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1',
  useSearchParams: () => new URLSearchParams(),
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

import { toast } from 'sonner';
import { QuotationDocumentClient } from './QuotationDocumentClient';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationScopesTab } from './QuotationScopesTab';
import {
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

async function startEditing() {
  await pressEdit();
  return screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' });
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

  it('sums the staged lines itself and keeps the other scopes saved', async () => {
    // Two scopes, only one of them edited. The shell derives the figure from the STAGED drafts
    // rather than being told one by whichever editor is mounted, which is what let a tab switch
    // snap the header back to a number the screen no longer agreed with.
    getQuotationDocument.mockResolvedValue(
      quotationDocument({
        grand_total: '253420.50',
        scopes: [
          scope({ id: 'q1', scope_label: 'Townhouse', scope_total: '235000.00' }),
          scope({
            id: 'q2',
            scope_label: 'Guard house',
            sort_order: 2,
            current_version_id: 'v9',
            scope_total: '18420.50',
          }),
        ],
      }),
    );
    listQuotations.mockResolvedValue([quotation()]);
    listQuotationVersions.mockResolvedValue([version()]);
    listQuotationLines.mockResolvedValue([line()]);
    renderScreen();

    // The server's own total until anything moves.
    expect(await screen.findByText('RM 253,420.50')).toBeInTheDocument();

    const qty = await startEditing();
    fireEvent.change(qty, { target: { value: '3' } });

    // 3 x 900.00 on the edited scope, plus the guard house's saved 18,420.50, to the cent.
    await waitFor(() => expect(screen.getByText('RM 21,120.50')).toBeInTheDocument());
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

    const issue = await screen.findByRole('button', { name: 'Issue R1' });
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

    expect(await screen.findByRole('button', { name: 'Issue R1' })).toBeEnabled();
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
      screen.getByText(/Issue this quotation to send the customer a link/i),
    ).toBeInTheDocument();
  });
});

describe('QuotationDocumentClient edit view', () => {
  it('reads as a document until Edit is pressed', async () => {
    seedOneScope();
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(await gearOffersEdit()).toBe(true);
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
  });

  it('keeps Edit out of the header, where the one CTA lives', async () => {
    // The client, with the header buttons circled: "edit should be in gear button". Issue is
    // the move that changes what the customer holds; Edit is a thing you can also do.
    seedOneScope();
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Issue R1' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it(
    'turns a whole session of changes into ONE write carrying the full set',
    async () => {
      // The client's complaint, measured: ten changes used to be ten requests and a dialog per
      // deletion. The DoD says building a scope performs one write, so that is what is counted.
      seedOneScope([
        line({ id: 'l1', product_code: 'SRT-WC-01', sort_order: 0 }),
        line({ id: 'l2', product_code: 'SRT-BASIN-02', description: 'Basin', sort_order: 10 }),
      ]);
      renderScreen();
      await startEditing();

      const edits: [string, string][] = [
        ['Qty on SRT-WC-01', '11'],
        ['Unit price on SRT-WC-01', '910.00'],
        ['Description on SRT-WC-01', 'Rimless wall-hung WC'],
        ['Tech spec on SRT-WC-01', 'Rimless'],
        ['Brand on SRT-WC-01', 'SORENTO'],
        ['Qty on SRT-BASIN-02', '12'],
        ['Unit price on SRT-BASIN-02', '560.00'],
        ['Description on SRT-BASIN-02', 'Counter basin'],
        ['Tech spec on SRT-BASIN-02', 'Vitreous china'],
        ['Complete set on SRT-BASIN-02', 'c/w waste'],
      ];
      for (const [label, value] of edits) {
        fireEvent.change(screen.getByRole('textbox', { name: label }), { target: { value } });
      }
      // And one line that did not exist before, so "the full set" means something.
      fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
      fireEvent.change(await screen.findByRole('textbox', { name: 'Description on line 3' }), {
        target: { value: 'Bespoke vanity top' },
      });

      // Nothing has left the browser yet. That is the whole feature.
      expect(replaceQuotationLines).not.toHaveBeenCalled();
      expect(updateQuotationLine).not.toHaveBeenCalled();
      expect(createQuotationLine).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(replaceQuotationLines).toHaveBeenCalledTimes(1));
      const [versionId, body] = replaceQuotationLines.mock.calls[0] as [
        string,
        { id?: string; description_snapshot: string | null; quantity: string }[],
      ];
      expect(versionId).toBe('v2');
      // Everything on screen, in display order, ids and all: a line the body omits is DELETED.
      expect(body).toHaveLength(3);
      expect(body.map((item) => item.id)).toEqual(['l1', 'l2', undefined]);
      expect(body[0]).toMatchObject({
        description_snapshot: 'Rimless wall-hung WC',
        quantity: '11',
        unit_price: '910.00',
      });
      expect(body[2]).toMatchObject({ description_snapshot: 'Bespoke vanity top' });
      expect(updateQuotationLine).not.toHaveBeenCalled();
      expect(createQuotationLine).not.toHaveBeenCalled();
      // Saved, and back to a document you can read.
      await waitFor(() => expect(screen.queryByRole('button', { name: 'Save' })).toBeNull());
    },
    // Eleven edits through the real editor is a lot of rendering for one claim, and the claim is
    // worth the cost: a stub in the middle would prove nothing about a keystroke reaching a
    // request. The generous budget is so a loaded CI box does not report it as a failure.
    20000,
  );

  it('puts everything back on Cancel, and writes nothing', async () => {
    seedOneScope();
    renderScreen();
    const qty = await startEditing();

    fireEvent.change(qty, { target: { value: '3' } });
    // In the header AND the table's footer, which is the pair that used to be able to disagree.
    await waitFor(() => expect(screen.getAllByText('RM 2,700.00').length).toBeGreaterThan(1));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // The server's rows, exactly as they were before Edit, and no request on the way past.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save' })).toBeNull());
    expect(await gearOffersEdit()).toBe(true);
    expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
    expect(screen.getAllByText('RM 9,000.00').length).toBeGreaterThan(0);
    expect(screen.queryByText('RM 2,700.00')).toBeNull();
    expect(replaceQuotationLines).not.toHaveBeenCalled();
  });

  it(
    'keeps staged edits across a tab switch, which routed tabs would otherwise throw away',
    async () => {
      // The tabs are ROUTES, so the scopes panel really does unmount on the way to the terms. The
      // session lives in the shell for exactly this reason, and it is the work somebody would be
      // most annoyed to lose.
      seedOneScope();
      const { openTab } = renderScreen();
      const qty = await startEditing();

      fireEvent.change(qty, { target: { value: '7' } });
      await waitFor(() => expect(screen.getAllByText('RM 6,300.00').length).toBeGreaterThan(0));

      openTab(<QuotationSignaturesTab />);
      expect(
        await screen.findByText('Signatures', { selector: '[data-slot="card-title"]' }),
      ).toBeInTheDocument();
      expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
      // Still counted while the panel that produced it is not even mounted.
      expect(screen.getByText('RM 6,300.00')).toBeInTheDocument();

      openTab(<QuotationScopesTab />);

      expect(await screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' })).toHaveValue('7');
      expect(replaceQuotationLines).not.toHaveBeenCalled();
    },
    20000,
  );

  it(
    'opens the terms for editing in the same session, and stages them for the same Save',
    async () => {
      seedOneScope();
      const { openTab } = renderScreen();
      await startEditing();

      openTab(<QuotationTermsTab />);

      // The prose tabs are part of the one Save too. Leaving them read-only would put two
      // different saving behaviours on one screen, which is the surprise being removed.
      expect(
        await screen.findByText('Terms and conditions', {
          selector: '[data-slot="card-title"]',
        }),
      ).toBeInTheDocument();
      // The empty state belongs to the READ. In a session the writing surface takes its place.
      expect(screen.queryByText(/No terms on this quotation yet/i)).toBeNull();
      expect(document.querySelector('.ProseMirror')).not.toBeNull();
      expect(updateQuotationDocument).not.toHaveBeenCalled();
    },
    20000,
  );

  it('asks once, at Save, and names how many lines are going', async () => {
    seedOneScope([
      line({ id: 'l1', product_code: 'SRT-WC-01' }),
      line({ id: 'l2', product_code: 'SRT-BASIN-02', description: 'Basin', sort_order: 10 }),
    ]);
    renderScreen();
    await startEditing();

    fireEvent.click(screen.getByRole('button', { name: 'Remove SRT-WC-01' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove SRT-BASIN-02' }));

    // Staging destroyed nothing, so nothing was asked. The rows are still there, struck through.
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(await screen.findAllByText('Removed on save')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(/Saving removes 2 lines/)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    expect(replaceQuotationLines).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save and remove 2 lines' }));

    await waitFor(() => expect(replaceQuotationLines).toHaveBeenCalledTimes(1));
    // An empty array is how the whole-set write clears a version, and it is what "remove both"
    // actually means.
    expect(replaceQuotationLines.mock.calls[0][1]).toEqual([]);
  });

  it('opens a revision before editing a version the customer holds, and only on a yes', async () => {
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

    // The reason and the move, in the header, before anything is pressed.
    expect(
      await screen.findByText(/The customer holds this version\. Edit opens the next one\./i),
    ).toBeInTheDocument();

    await pressEdit();

    // Never a silent branch: a revision that appeared without being asked for is a document the
    // customer was never told about.
    expect(await screen.findByText(/This version is with the customer/i)).toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Open a new version and edit' }));

    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledWith('q1'));
    // And it lands in edit mode rather than making somebody press Edit a second time.
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('does not offer a revision because ANOTHER document in the project is locked', async () => {
    // `listQuotations` answers every scope in the PROJECT, across every quotation document. Read
    // without filtering, a clean single-scope draft was told "This version is with the customer"
    // and offered a revision of four scopes it does not own, because some OTHER document in the
    // same project had been issued. The document on screen is the only one Edit may act on.
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ grand_total: '9000.00', scopes: [scope()] }),
    );
    listQuotations.mockResolvedValue([
      quotation(),
      quotation({ id: 'other-doc-scope', current_version_id: 'other-v1' }),
    ]);
    // Keyed by scope, the way the hook really queries: the other document's scope is the frozen
    // one, and this document's is not. A single shared answer would hide the very bug under test.
    listQuotationVersions.mockImplementation((quotationId: string) =>
      Promise.resolve(
        quotationId === 'other-doc-scope'
          ? [version({ id: 'other-v1', is_issued: true, is_editable: false })]
          : [version()],
      ),
    );
    listQuotationLines.mockResolvedValue([line()]);
    renderScreen();

    await pressEdit();

    // Straight into edit mode: no prompt, and nothing revised.
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(screen.queryByText(/This version is with the customer/i)).not.toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();
  });

  it('offers no Edit to a reader', async () => {
    seedOneScope();
    getProject.mockResolvedValue(project({ can_edit: false }));
    renderScreen();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    // Not in the header, and not in the gear it moved into either.
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(await gearOffersEdit()).toBe(false);
    expect(
      screen.getByText('You can read this quotation but not change it.'),
    ).toBeInTheDocument();
  });
});

/**
 * The letterhead in an edit session.
 *
 * No scope is seeded for most of these: the letterhead is the shell's own block, and a spec that
 * needed the line editor running to make a claim about the Attn field would be pinning the wrong
 * thing (and paying eleven renders for it).
 */
describe('QuotationDocumentClient letterhead editing', () => {
  /** Straight into a session, without the line editor in the way. */
  async function editLetterhead(overrides: Partial<QuotationDocument> = {}) {
    getQuotationDocument.mockResolvedValue(quotationDocument(overrides));
    const rendered = renderScreen();
    await pressEdit();
    return rendered;
  }

  it('is a read until Edit, and only then an input', async () => {
    getQuotationDocument.mockResolvedValue(
      quotationDocument({ your_ref: 'NCSB/2026/117' }),
    );
    renderScreen();

    // The values are on screen from the start, because the whole point of the block is that the
    // system already knows them. What is absent is anywhere to type.
    expect(await screen.findByText('NCSB/2026/117')).toBeInTheDocument();
    expect(screen.queryByLabelText('Your Ref')).toBeNull();
    expect(screen.queryByLabelText('Attn')).toBeNull();
    expect(screen.queryByLabelText('Address')).toBeNull();
    expect(screen.queryByLabelText('Date')).toBeNull();

    await pressEdit();

    expect(await screen.findByLabelText('Your Ref')).toHaveValue('NCSB/2026/117');
    expect(screen.getByLabelText('Attn')).toHaveValue('Kelly');
    expect(screen.getByLabelText('Name')).toHaveValue('Nadi Cergas Sdn Bhd');
    expect(screen.getByLabelText('Date')).toHaveValue('2026-02-26');
    // Our Ref is the number the customer already has, minted by the numbering rule, and the
    // backend refuses to change it. So it stays a read even here.
    expect(screen.queryByLabelText('Our Ref')).toBeNull();
    expect(screen.getByText('Our Ref')).toBeInTheDocument();
    // Twice on screen on purpose: the record's identity line at the top, and the letterhead.
    expect(screen.getAllByText('SRT/Q/2026/0141').length).toBeGreaterThan(0);
  });

  it('sends the staged letterhead in the ONE document PATCH', async () => {
    await editLetterhead();

    fireEvent.change(await screen.findByLabelText('Your Ref'), {
      target: { value: 'NCSB/PO/2026/551' },
    });
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-03-02' } });
    fireEvent.change(screen.getByLabelText('Attn'), { target: { value: 'Ms Tan' } });
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Nadi Cergas Sdn Bhd (Finance)' },
    });
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '03-1234 5678' } });

    // Nothing has left the browser, exactly as for a line edit.
    expect(updateQuotationDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    const [projectArg, documentArg, body] = updateQuotationDocument.mock.calls[0] as [
      string,
      string,
      Record<string, unknown>,
    ];
    expect(projectArg).toBe('p1');
    expect(documentArg).toBe('d1');
    expect(body).toEqual({
      your_ref: 'NCSB/PO/2026/551',
      doc_date: '2026-03-02',
      attn_name: 'Ms Tan',
      recipient_name_snapshot: 'Nadi Cergas Sdn Bhd (Finance)',
      recipient_phone_snapshot: '03-1234 5678',
    });
    // Saved, and back to a document you can read.
    await waitFor(() => expect(screen.queryByLabelText('Your Ref')).toBeNull());
  });

  it('keeps a staged letterhead edit across a tab switch', async () => {
    // The same claim the lines make, and it has to be made separately: the letterhead reads its
    // value out of `documentDraft`, so a session that reset the draft on the way to the terms
    // would silently put the server's recipient back while the user was reading the clauses.
    const { openTab } = await editLetterhead();

    fireEvent.change(await screen.findByLabelText('Attn'), { target: { value: 'Ms Tan' } });

    openTab(<QuotationTermsTab />);
    expect(
      await screen.findByText('Terms and conditions', { selector: '[data-slot="card-title"]' }),
    ).toBeInTheDocument();

    openTab(<QuotationScopesTab />);

    expect(await screen.findByLabelText('Attn')).toHaveValue('Ms Tan');
    expect(updateQuotationDocument).not.toHaveBeenCalled();
  });

  it('puts the letterhead back on Cancel, and writes nothing', async () => {
    await editLetterhead({ your_ref: 'NCSB/2026/117' });

    fireEvent.change(await screen.findByLabelText('Your Ref'), {
      target: { value: 'WRONG-REF' },
    });
    fireEvent.change(screen.getByLabelText('Attn'), { target: { value: 'Nobody' } });
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Wrong subject' } });
    // The heading follows the staged copy too, or the card and the title two centimetres above
    // it would disagree about the same document.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Wrong subject' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save' })).toBeNull());
    expect(await gearOffersEdit()).toBe(true);
    expect(screen.queryByLabelText('Your Ref')).toBeNull();
    expect(screen.getByText('NCSB/2026/117')).toBeInTheDocument();
    expect(screen.getByText('Kelly')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'CADANGAN MEMBINA PANGSAPURI' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('WRONG-REF')).toBeNull();
    expect(updateQuotationDocument).not.toHaveBeenCalled();
  });

  it('round-trips a multi-line address through the textarea', async () => {
    const address = 'Level 12, Menara Nadi\nJalan Ampang\n50450 Kuala Lumpur';
    await editLetterhead();

    // A single-line input would flatten this on the way in, and the PDF prints a line per
    // newline, so the newlines ARE the address.
    fireEvent.change(await screen.findByLabelText('Address'), { target: { value: address } });
    expect(screen.getByLabelText('Address')).toHaveValue(address);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    expect(updateQuotationDocument.mock.calls[0][2]).toEqual({
      recipient_address_snapshot: address,
    });
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
    renderScreen();

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

    expect(within(menu).getAllByText('Issue it first').length).toBeGreaterThan(0);
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
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
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
