/**
 * #1341 - the quotation form page, create and edit (AC-QF010 to AC-QF024, AC-QF040/041,
 * AC-QF070 to AC-QF073).
 *
 * The owner: "I should be able to add product straight away and save when I am satisfied, if I
 * want to edit I can click on the gear button to edit". So create is a page that writes nothing
 * until Save, and Save is ONE request; edit is the same page, filled, and its Save is ONE PATCH.
 *
 * Round 3, the owner: "we shouldn't revamp the Lines tab, it was good, we should reuse that". So
 * the Lines tab is the quotation page's lines editing from origin/main: `QuotationVersionEditor`
 * (the `InlineLineTable` cells, Add a line, Add a section, strike-through Remove) driven by the
 * same `useQuotationEditSession` handlers, with the same scope strip and scope dialogs.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
  cleanup,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../../_shared/services/quotationDocumentService';
import type {
  Project,
  ProjectQuotation,
  QuotationLine,
  QuotationVersion,
} from '../../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

// Removing a saved scope is a hard delete, gated on projects.projects.delete like the scope
// DELETE route. Granted by default; a spec below takes it away.
let granted = new Set(['projects.projects.view', 'projects.projects.edit', 'projects.projects.delete']);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({ permissions: [...granted], permissionSet: granted, isLoading: false }),
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/new',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));

const createQuotationDocument = vi.fn();
const updateQuotationDocument = vi.fn();
const getQuotationDocument = vi.fn();
const getQuotationLetterTemplates = vi.fn();
const getQuotationFeedback = vi.fn();
// QUOTE-AUTOSAVE: the form's draft and History calls.
const openQuotationFormDraft = vi.fn();
const getQuotationDraftHolder = vi.fn();
const saveQuotationFormDraft = vi.fn();
const restoreQuotationHistoryEntry = vi.fn();
const listQuotationHistory = vi.fn();
vi.mock(
  '../../../_shared/services/quotationDocumentService',
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import('../../../_shared/services/quotationDocumentService')
      >();
    return {
      ...actual,
      createQuotationDocument: (...args: unknown[]) =>
        createQuotationDocument(...args),
      updateQuotationDocument: (...args: unknown[]) =>
        updateQuotationDocument(...args),
      getQuotationDocument: (...args: unknown[]) =>
        getQuotationDocument(...args),
      getQuotationLetterTemplates: (...args: unknown[]) =>
        getQuotationLetterTemplates(...args),
      getQuotationFeedback: (...args: unknown[]) => getQuotationFeedback(...args),
      openQuotationFormDraft: (...args: unknown[]) => openQuotationFormDraft(...args),
      getQuotationDraftHolder: (...args: unknown[]) => getQuotationDraftHolder(...args),
      saveQuotationFormDraft: (...args: unknown[]) => saveQuotationFormDraft(...args),
      restoreQuotationHistoryEntry: (...args: unknown[]) => restoreQuotationHistoryEntry(...args),
      listQuotationHistory: (...args: unknown[]) => listQuotationHistory(...args),
    };
  },
);

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

const getProject = vi.fn();
const listQuotations = vi.fn();
const listQuotationVersions = vi.fn();
const listQuotationLines = vi.fn();
const listSeries = vi.fn();
const replaceQuotationLines = vi.fn();
const recomputeQuotationVersion = vi.fn();
vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import('../../../_shared/services/projectService')
    >();
  return {
    ...actual,
    getProject: (...args: unknown[]) => getProject(...args),
    listQuotations: (...args: unknown[]) => listQuotations(...args),
    listQuotationVersions: (...args: unknown[]) =>
      listQuotationVersions(...args),
    listQuotationLines: (...args: unknown[]) => listQuotationLines(...args),
    listSeries: (...args: unknown[]) => listSeries(...args),
    replaceQuotationLines: (...args: unknown[]) =>
      replaceQuotationLines(...args),
    recomputeQuotationVersion: (...args: unknown[]) => recomputeQuotationVersion(...args),
    judgeQuotationLine: vi.fn(async () => ({
      is_non_standard: false,
      is_below_floor: false,
      floor_value: null,
      floor_level: null,
    })),
  };
});

vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({
    getProductsForLineSelect: vi.fn(async () => [
      {
        id: 'p9',
        product_code: 'SRT-BASIN-02',
        product_name: 'Counter basin',
        description: 'Vitreous china counter basin',
        brand_id: 'b1',
        base_uom_id: 'u1',
        list_price: '560.00',
      },
    ]),
    getProductsForVariantSelect: vi.fn(async () => []),
  }),
);
vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query',
  () => ({
    useBrandSelectQuery: () => ({
      data: [{ id: 'b1', brand_name: 'SORENTO' }],
    }),
  }),
);
vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query',
  () => ({
    useUOMSelectQuery: () => ({
      data: [{ id: 'u1', uom_code: 'PCS', uom_name: 'Pieces' }],
    }),
  }),
);

// The repo's rich-text editor needs layout APIs jsdom lacks; a textarea stands in so the value
// the tab holds can be read and typed.
vi.mock('@/components/ui/rich-text-editor', () => ({
  RichTextEditor: ({
    value,
    onChange,
    placeholder,
    id,
    'aria-labelledby': labelledBy,
  }: {
    value: string;
    onChange: (html: string) => void;
    placeholder?: string;
    id?: string;
    'aria-labelledby'?: string;
  }) => (
    <textarea
      id={id}
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

// QUOTE-TERMS-SELECT: the terms fields have their own spec (QuoteTermsFields.test.tsx); here a
// stub shows what the form hands them and emits the patches the real one would.
vi.mock('../../../_shared/components/QuoteTermsFields', () => ({
  QuoteTermsFields: ({
    values,
    onChange,
    onValidityChange,
    projectId,
  }: {
    values: Record<string, unknown>;
    onChange: (patch: Record<string, unknown>) => void;
    onValidityChange?: (valid: boolean) => void;
    projectId?: string;
  }) => (
    <div>
      <output aria-label="Terms values">{JSON.stringify(values)}</output>
      <output aria-label="Terms project">{projectId ?? ''}</output>
      <button
        type="button"
        onClick={() => onChange({ payment_term_id: 'pt-cbd', payment_terms: 'CASH BEFORE DELIVERY' })}
      >
        Pick CBD
      </button>
      <button
        type="button"
        onClick={() => onChange({ validity_value: 90, validity_unit: 'day', validity: '90 DAYS' })}
      >
        Pick 90 days
      </button>
      <button type="button" onClick={() => onValidityChange?.(false)}>
        Type an invalid validity
      </button>
    </div>
  ),
}));

/**
 * The quotation page's own editor and edit session, spied rather than replaced: the real ones
 * render, and the specs can prove the form's lines go through them and nowhere else.
 */
const editorProps = vi.fn();
vi.mock('../../components/QuotationVersionEditor', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../components/QuotationVersionEditor')>();
  const Real = actual.QuotationVersionEditor;
  return {
    ...actual,
    QuotationVersionEditor: (props: Parameters<typeof Real>[0]) => {
      editorProps(props);
      return <Real {...props} />;
    },
  };
});

const stageScopeSpy = vi.fn();
const toggleRemovedSpy = vi.fn();
vi.mock('../[documentId]/components/useQuotationEditSession', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../[documentId]/components/useQuotationEditSession')>();
  const ReactModule = await import('react');
  return {
    ...actual,
    useQuotationEditSession: () => {
      const session = actual.useQuotationEditSession();
      const { stageScope, toggleRemoved } = session;
      const stage = ReactModule.useCallback(
        (...args: Parameters<typeof stageScope>) => {
          stageScopeSpy(...args);
          stageScope(...args);
        },
        [stageScope],
      );
      const toggle = ReactModule.useCallback(
        (...args: Parameters<typeof toggleRemoved>) => {
          toggleRemovedSpy(...args);
          toggleRemoved(...args);
        },
        [toggleRemoved],
      );
      return { ...session, stageScope: stage, toggleRemoved: toggle };
    },
  };
});

// QUOTE-AUTOSAVE crew pass: Discard draft's options are read back (what it refreshes on commit).
const deferredOptions = vi.fn();
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (options: unknown) => {
    deferredOptions(options);
    return {
      pending: null,
      isPending: false,
      isBlocked: false,
      start: vi.fn(),
      cancel: vi.fn(),
      countdown: null,
    };
  },
}));

import { QuotationFormClient } from './QuotationFormClient';
import { quotationDocumentKey } from '../../../_shared/hooks/useQuotationDocuments';
import { QuotationScopeTabs } from '../[documentId]/components/QuotationScopeTabs';

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
    developer_name: 'Nadi Cergas Sdn Bhd',
    ...overrides,
  };
}

function document(
  overrides: Partial<QuotationDocument> = {},
): QuotationDocument {
  return {
    id: 'd1',
    project_id: 'p1',
    document_no: 'PRJQ-2026-0002',
    our_ref: 'PRJQ-2026-0002',
    your_ref: 'NC/18',
    doc_date: '2026-09-28',
    recipient_party_id: null,
    recipient_name_snapshot: 'Nadi Cergas Sdn Bhd',
    recipient_address_snapshot: 'Level 8',
    recipient_phone_snapshot: null,
    attn_name: 'Kelly',
    subject_title: 'Menara Test',
    cover_letter_html: '<p>Dear Sir</p>',
    terms_html: '<p>Terms</p>',
    signatory_name: null,
    signatory_phone: null,
    scopes: [
      {
        id: 'q1',
        scope_label: 'Townhouse',
        sort_order: 0,
        outcome: 'open',
        current_version_id: 'v1',
        current_version_no: 1,
        line_count: 1,
        scope_total: '9000.00',
      },
    ],
    grand_total: '9000.00',
    issue_count: 0,
    current_issue_no: null,
    is_issued: false,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

const SCOPE: ProjectQuotation = {
  id: 'q1',
  project_id: 'p1',
  scope_label: 'Townhouse',
  outcome: 'open',
  version_count: 1,
  current_version_id: 'v1',
  current_version_no: 1,
  current_total: '9000.00',
  below_floor_count: 0,
  non_standard_count: 0,
  line_count: 1,
  series_id: null,
};

function version(overrides: Partial<QuotationVersion> = {}): QuotationVersion {
  return {
    id: 'v1',
    quotation_id: 'q1',
    version_no: 1,
    is_current: true,
    is_editable: true,
    total_amount: '9000.00',
    ...overrides,
  };
}

const LINE: QuotationLine = {
  id: 'l1',
  version_id: 'v1',
  product_id: 'p1',
  product_code: 'SRT-WC-01',
  description: 'Wall-hung WC',
  unit_price: '900.00',
  quantity: '10.00',
  line_total: '9000.00',
  is_non_standard: false,
  is_below_floor: false,
  sort_order: 0,
};

function renderForm(documentId?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationFormClient projectId="p1" documentId={documentId} />
    </QueryClientProvider>,
  );
}

/** The form's own tabs (#1341, owner: "header stays in header tab"). */
async function openTab(name: 'Header' | 'Cover letter' | 'Terms') {
  fireEvent.mouseDown(await screen.findByRole('tab', { name }), { button: 0 });
  await waitFor(() =>
    expect(screen.getByRole('tab', { name })).toHaveAttribute('data-state', 'active'),
  );
}

/** The form's own tabs (Header, Cover letter, Terms); the area strip below is its own tablist. */
async function formTabNames() {
  const strips = await screen.findAllByRole('tablist');
  return within(strips[0]).getAllByRole('tab').map((tab) => tab.textContent);
}

/** The open scope's card, by the name its strip tab carries. */
function scopeCard(name: string) {
  return screen.getByRole('region', { name });
}

/**
 * The lines, open, with the scope's line table drawn and ready to type into. They sit on the
 * Header tab under the letterhead (PROPOSAL-HEADER-LAYOUT); there is no Lines tab.
 */
async function openLines(scope = 'Scope 1') {
  await openTab('Header');
  const card = await waitFor(() => scopeCard(scope));
  await within(card).findByRole('button', { name: 'Add a line' });
  return card;
}

/**
 * A scope action from the open tab's own "Scope actions" trigger (QUOTE-SCOPE-COMPACT, owner
 * 4 Nov: the tabs ARE the scope header, so Rename and Remove scope live on the tab).
 */
async function scopeAction(scope: string, item: 'Rename' | 'Remove scope') {
  fireEvent.click(screen.getByRole('button', { name: `Scope actions on ${scope}` }));
  fireEvent.click(await screen.findByRole('menuitem', { name: item }));
}

/** The Remove scope item in the open tab's menu, opened and returned (to read its state). */
async function removeItemOf(scope: string) {
  fireEvent.click(screen.getByRole('button', { name: `Scope actions on ${scope}` }));
  return screen.findByRole('menuitem', { name: 'Remove scope' });
}

/** The quotation page's Edit scope dialog: name (and series, notes), staged by the form. */
async function nameScope(card: HTMLElement, label: string) {
  await scopeAction(card.getAttribute('aria-label') ?? '', 'Rename');
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByRole('textbox', { name: /^Scope/ }), {
    target: { value: label },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
}

/** The quotation page's Add a scope: the + at the end of the scope strip, then its name dialog. */
async function addScope(label: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Add a scope' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Scope name'), { target: { value: label } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  const card = await waitFor(() => scopeCard(label));
  await within(card).findByRole('button', { name: 'Add a line' });
  return card;
}

/** Add a line on the open scope and wait for its cells. */
async function addLine(card: HTMLElement, lineNo: number) {
  fireEvent.click(within(card).getByRole('button', { name: 'Add a line' }));
  return within(card).findByRole('button', { name: `Description on line ${lineNo}` });
}

/** Opens a line's Description cell (a popover holding the shared editor, QUOTE-DESC-RICHTEXT)
 * and hands back the editor's stand-in textarea. */
async function openDescription(card: HTMLElement, label: string) {
  fireEvent.click(within(card).getByRole('button', { name: `Description on ${label}` }));
  return screen.findByRole('textbox', { name: `Description text on ${label}` });
}

/** Picks the catalogue product fixture on a line; the row's labels then name it by its code. */
async function pickProduct(card: HTMLElement, lineNo: number) {
  fireEvent.click(within(card).getByRole('combobox', { name: `Product on line ${lineNo}` }));
  fireEvent.click(await screen.findByRole('option', { name: /SRT-BASIN-02/ }));
  await within(card).findByRole('textbox', { name: 'Unit price on SRT-BASIN-02' });
}

beforeEach(() => {
  vi.clearAllMocks();
  granted = new Set(['projects.projects.view', 'projects.projects.edit', 'projects.projects.delete']);
  getProject.mockResolvedValue(project());
  listSeries.mockResolvedValue([
    {
      id: 's1',
      name: 'Premium Series',
      is_active: true,
      category_ids: [],
      category_names: [],
    },
  ]);
  listQuotations.mockResolvedValue([SCOPE]);
  listQuotationVersions.mockResolvedValue([version()]);
  listQuotationLines.mockResolvedValue([LINE]);
  getQuotationDocument.mockResolvedValue(document());
  createQuotationDocument.mockResolvedValue(document({ id: 'd-new' }));
  updateQuotationDocument.mockResolvedValue(document());
  openQuotationFormDraft.mockResolvedValue({
    draft_id: 'draft-1',
    token: 'tok-1',
    doc: null,
    updated_at: null,
    updated_by_name: null,
  });
  getQuotationDraftHolder.mockResolvedValue({ is_holder: true });
  saveQuotationFormDraft.mockResolvedValue({ updated_at: '2026-11-10T06:14:00' });
  listQuotationHistory.mockResolvedValue([]);
  window.localStorage.clear();
  getQuotationLetterTemplates.mockResolvedValue({
    cover_letter_html: '<p>Dear {{attn_name}}</p>',
    terms_html: '<p>Valid 30 days</p>',
  });
});

describe('QuotationFormClient create', () => {
  it('defaults Name, Phone and Attn from the project customer (owner, 13 Oct)', async () => {
    getProject.mockResolvedValue(
      project({
        customer_id: 'cust-1',
        customer_name: 'Gamuda Builders Sdn Bhd',
        customer_phone: '012-345 6789',
        customer_attn: 'Lim Wei Ming',
      }),
    );
    renderForm();

    await waitFor(() =>
      expect(screen.getByLabelText('Name')).toHaveValue('Gamuda Builders Sdn Bhd'),
    );
    expect(screen.getByLabelText('Phone')).toHaveValue('012-345 6789');
    expect(screen.getByLabelText('Attn')).toHaveValue('Lim Wei Ming');
  });

  it('falls back to the developer when the project has no customer', async () => {
    renderForm();
    await waitFor(() =>
      expect(screen.getByLabelText('Name')).toHaveValue('Nadi Cergas Sdn Bhd'),
    );
    expect(screen.getByLabelText('Attn')).toHaveValue('');
  });

  it('PROJECT-PARTY-ROLES: Save addresses a new proposal to the developer party, as its To', async () => {
    getProject.mockResolvedValue(project({ developer_party_id: 'dev-1' }));
    renderForm();
    await nameScope(await openLines(), 'Townhouse');
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    const [, body] = createQuotationDocument.mock.calls[0];
    expect(body.recipient_party_id).toBe('dev-1');
    // Blanks the screen could not fill are left to the server, not sent as null.
    expect('recipient_address_snapshot' in body).toBe(false);
  });

  it('QUOTE-SCOPE-COMPACT: no scope header repeats the tab; Rename opens Edit scope from the tab', async () => {
    renderForm();
    const card = await openLines();

    // The tabs are the header: no title, pen or Remove scope button under them (owner, 4 Nov).
    expect(within(card).queryByRole('button', { name: 'Edit scope' })).toBeNull();
    expect(within(card).queryByRole('button', { name: 'Remove scope' })).toBeNull();
    expect(within(card).queryByText('Scope 1')).toBeNull();
    expect(within(card).queryByText('No series')).toBeNull();
    // One container: the old Card wrapper is gone, the editor sits straight in the region.
    expect(card.querySelector('[data-slot="card"]')).toBeNull();

    await scopeAction('Scope 1', 'Rename');
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('textbox', { name: /^Scope/ })).toBeInTheDocument();
    expect(within(dialog).getByText('Series')).toBeInTheDocument();
  });

  it('AC-QF011/012: opens with the letterhead and one empty scope ready for products', async () => {
    renderForm();

    expect(await screen.findByLabelText('Your Ref')).toBeInTheDocument();
    expect(screen.getByLabelText('Attn')).toBeInTheDocument();
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    expect(screen.getByLabelText('Date')).toHaveValue(today);
    // The subject arrives as the project's title, the same default the server would use.
    await waitFor(() =>
      expect(screen.getByLabelText('Project title')).toHaveValue('Menara Test'),
    );
    const card = await openLines();
    expect(screen.getByRole('button', { name: 'Scope actions on Scope 1' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Add a section' })).toBeInTheDocument();
  });

  it('AC-QF070: the Lines tab is the quotation page\'s own lines editor, not a new one', async () => {
    renderForm();
    const card = await openLines();

    // The same component the quotation page renders, in its staged edit mode.
    expect(editorProps).toHaveBeenCalled();
    const props = editorProps.mock.calls.at(-1)![0];
    expect(props.edit).toEqual(
      expect.objectContaining({
        seed: expect.any(Function),
        stage: expect.any(Function),
        toggleRemoved: expect.any(Function),
      }),
    );
    // A scope added here has no saved record yet.
    expect(props.quotation).toBeNull();

    // Its line table, whose lines ARE rows of cells, and the scope strip with Add a scope at its end.
    expect(within(card).getByRole('table')).toBeInTheDocument();
    expect(screen.getByTestId('quotation-scope-strip')).toBeInTheDocument();
    await addLine(card, 1);
    expect(within(card).getByRole('textbox', { name: 'Unit price on line 1' })).toBeInTheDocument();

    // And not the round 2 inline editor: no per-line panel under the grid, no Edit line, no Done.
    expect(screen.queryByRole('group', { name: 'Line 1' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit line 1' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Done' })).toBeNull();
  });

  it('AC-QF071: Add a line, Add a section and Remove go through the quotation page\'s session handlers', async () => {
    renderForm();
    const card = await openLines();

    await addLine(card, 1);
    fireEvent.change(await openDescription(card, 'line 1'), { target: { value: 'Grab bar' } });
    await waitFor(() =>
      expect(stageScopeSpy).toHaveBeenCalledWith(
        expect.stringMatching(/^new-scope:/),
        [expect.objectContaining({ id: null, draft: expect.objectContaining({ description: 'Grab bar' }) })],
      ),
    );

    fireEvent.click(within(card).getByRole('button', { name: 'Add a section' }));
    // A heading row of its own, then a line under it (PROPOSAL-FORM-COLLAPSE).
    const heading = await within(card).findByRole('textbox', { name: 'Section heading above line 2' });
    fireEvent.change(heading, { target: { value: 'OPTIONAL ITEMS' } });
    await waitFor(() =>
      expect(stageScopeSpy).toHaveBeenLastCalledWith(
        expect.stringMatching(/^new-scope:/),
        [
          expect.anything(),
          expect.objectContaining({
            draft: expect.objectContaining({ is_section: expect.any(String), band_label: 'OPTIONAL ITEMS' }),
          }),
          expect.objectContaining({ id: null }),
        ],
      ),
    );

    // Remove takes the line out at once through the same stage handler (owner hand test 11 Nov:
    // no struck-through row; Undo is the way back).
    fireEvent.click(within(card).getByRole('button', { name: 'Remove line 1' }));
    await waitFor(() =>
      expect(stageScopeSpy).toHaveBeenLastCalledWith(
        expect.stringMatching(/^new-scope:/),
        [
          expect.objectContaining({
            draft: expect.objectContaining({ band_label: 'OPTIONAL ITEMS' }),
          }),
          expect.objectContaining({ id: null }),
        ],
      ),
    );
    expect(within(card).queryByText('Removed on save')).toBeNull();
    expect(createQuotationDocument).not.toHaveBeenCalled();
    expect(replaceQuotationLines).not.toHaveBeenCalled();
  });

  it('AC-QF010: writes nothing while the form is being filled', async () => {
    renderForm();
    const card = await openLines();

    await nameScope(card, 'Townhouse');
    await addLine(scopeCard('Townhouse'), 1);
    await addScope('Guard House');

    expect(createQuotationDocument).not.toHaveBeenCalled();
    expect(updateQuotationDocument).not.toHaveBeenCalled();
    expect(replaceQuotationLines).not.toHaveBeenCalled();
  });

  it('AC-QF014: Save sends ONE request with the header, every scope and every line', async () => {
    renderForm();
    fireEvent.change(await screen.findByLabelText('Your Ref'), {
      target: { value: 'NC/19' },
    });
    await nameScope(await openLines(), 'Townhouse');
    const first = scopeCard('Townhouse');

    await addLine(first, 1);
    await pickProduct(first, 1);
    fireEvent.change(within(first).getByRole('textbox', { name: 'Unit price on SRT-BASIN-02' }), {
      target: { value: '120.00' },
    });

    await addScope('Guard House');

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    await waitFor(() =>
      expect(createQuotationDocument).toHaveBeenCalledTimes(1),
    );
    const [projectId, body] = createQuotationDocument.mock.calls[0];
    expect(projectId).toBe('p1');
    expect(body).toMatchObject({
      your_ref: 'NC/19',
      subject_title: 'Menara Test',
      scopes: [
        {
          scope_label: 'Townhouse',
          lines: [
            expect.objectContaining({
              product_id: 'p9',
              unit_price: '120.00',
              quantity: '1',
            }),
          ],
        },
        { scope_label: 'Guard House', lines: [] },
      ],
    });
    // Lands on the quotation the server just created.
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        '/project-sales/p1/quotation-documents/d-new',
      ),
    );
  });

  it('AC-QF018: refuses a scope with no name and a line with nothing on it, before any request', async () => {
    renderForm();
    const card = await openLines();
    await addLine(card, 1);

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    expect(
      await screen.findByText(/Every scope needs a name/i),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();

    await nameScope(card, 'Townhouse');
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    expect(
      await screen.findByText(
        /One line still needs a catalogue product or set\./i,
      ),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });

  it('AC-19: a line with only a description is refused on Save, and nothing is sent', async () => {
    renderForm();
    const card = await openLines();
    await nameScope(card, 'Townhouse');
    const named = scopeCard('Townhouse');
    await addLine(named, 1);
    fireEvent.change(await openDescription(named, 'line 1'), {
      target: { value: 'Bespoke vanity top' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    expect(
      await screen.findByText('One line still needs a catalogue product or set.'),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });

  it('AC-QF013: a scope added on the form can be removed before Save', async () => {
    renderForm();
    await openLines();

    await addScope('Guard House');
    // No confirm (staged until Save; PRINCIPLES.md forbids confirm dialogs on a destructive
    // action): the menu item removes it at once, in its destructive styling.
    const remove = await removeItemOf('Guard House');
    expect(remove.className).toMatch(/text-destructive/);
    fireEvent.click(remove);
    expect(screen.queryByRole('alertdialog')).toBeNull();

    await waitFor(() => expect(screen.queryByRole('region', { name: 'Guard House' })).toBeNull());
    expect(screen.getByRole('region', { name: 'Scope 1' })).toBeInTheDocument();
  });

  it('QUOTE-AUTOSAVE Q5: no Cancel, and an untouched New proposal writes nothing at all', async () => {
    renderForm();
    await openLines();

    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    // No draft yet, so nothing to discard.
    expect(screen.queryByRole('button', { name: 'Discard draft' })).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(saveQuotationFormDraft).not.toHaveBeenCalled();
    expect(createQuotationDocument).not.toHaveBeenCalled();
    // The person's own private draft was opened: no document, nothing numbered.
    expect(openQuotationFormDraft).toHaveBeenCalledWith('p1', null);
  });

  it('AC-QF040: one primary CTA and no subtitle under the title', async () => {
    renderForm();
    await openLines();

    expect(
      screen.getByRole('heading', { level: 1, name: 'New proposal' }),
    ).toBeInTheDocument();
    // Save is the only filled button.
    const save = screen.getByRole('button', { name: 'Save proposal' });
    expect(save.className).toMatch(/bg-primary/);
    expect(
      screen
        .getAllByRole('button')
        .filter((b) => /bg-primary /.test(b.className)),
    ).toHaveLength(1);
  });
});

describe('QuotationFormClient edit', () => {
  /** A saved scope's lines, seeded into the session and drawn as cells. */
  async function openSavedLines() {
    const card = await openLines('Townhouse');
    await within(card).findByRole('textbox', { name: 'Qty on SRT-WC-01' });
    return card;
  }

  it('AC-QF020: opens filled from the saved quotation, with the same sections plus the letter', async () => {
    renderForm('d1');

    await waitFor(() =>
      expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'),
    );
    expect(screen.getByLabelText('Attn')).toHaveValue('Kelly');
    const card = await openSavedLines();
    expect(within(card).getByRole('button', { name: 'Description on SRT-WC-01' }).textContent).toBe(
      'Wall-hung WC',
    );
    // The saved scope's own record reaches the editor, as on the quotation page.
    expect(editorProps.mock.calls.at(-1)![0].quotation).toMatchObject({ id: 'q1' });
    expect(
      screen.getByRole('heading', { level: 1, name: 'PRJQ-2026-0002' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cover letter' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Terms' })).toBeInTheDocument();
  });

  it('FE4: the saved-scope strip carries no outcome pill (one outcome per project)', async () => {
    renderForm('d1');
    await openSavedLines();

    const pills = screen
      .queryAllByText(/^(Won|Lost|Open|Still open)$/)
      .filter((el) => el.className.includes('rounded-full'));
    expect(pills).toHaveLength(0);
  });

  it('AC-QF021: Save sends ONE PATCH with the header and every scope, lines included', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), {
      target: { value: 'NC/20' },
    });
    const card = await openSavedLines();
    fireEvent.change(within(card).getByRole('textbox', { name: 'Qty on SRT-WC-01' }), {
      target: { value: '12' },
    });
    await nameScope(card, 'Townhouse Block A');

    await addScope('Reception');

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    await waitFor(() =>
      expect(updateQuotationDocument).toHaveBeenCalledTimes(1),
    );
    const [projectId, documentId, body] = updateQuotationDocument.mock.calls[0];
    expect([projectId, documentId]).toEqual(['p1', 'd1']);
    expect(body).toMatchObject({
      your_ref: 'NC/20',
      scopes: [
        {
          id: 'q1',
          scope_label: 'Townhouse Block A',
          lines: [expect.objectContaining({ id: 'l1', quantity: '12' })],
        },
        { scope_label: 'Reception', lines: [] },
      ],
    });
    expect(replaceQuotationLines).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        '/project-sales/p1/quotation-documents/d1',
      ),
    );
  });

  it('AC-QF071: a line removed on the form leaves at once and is left out of the PATCH', async () => {
    renderForm('d1');
    const card = await openSavedLines();

    fireEvent.click(within(card).getByRole('button', { name: 'Remove SRT-WC-01' }));
    await waitFor(() => expect(stageScopeSpy).toHaveBeenLastCalledWith('q1', []));
    expect(within(card).queryByText('Removed on save')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    expect(updateQuotationDocument.mock.calls[0][2].scopes[0]).toMatchObject({
      id: 'q1',
      lines: [],
    });
  });

  it('QUOTE-AUTOSAVE Q1: typing autosaves to the DRAFT with this tab\'s claim, never the record', async () => {
    renderForm('d1');
    await waitFor(() =>
      expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'),
    );
    expect(openQuotationFormDraft).toHaveBeenCalledWith('p1', 'd1');

    fireEvent.change(screen.getByLabelText('Your Ref'), {
      target: { value: 'changed' },
    });
    await waitFor(() => expect(saveQuotationFormDraft).toHaveBeenCalled(), { timeout: 3000 });
    const [projectId, documentId, state, token] = saveQuotationFormDraft.mock.calls.at(-1)!;
    expect([projectId, documentId, token]).toEqual(['p1', 'd1', 'tok-1']);
    expect(state.header.your_ref).toBe('changed');
    expect(updateQuotationDocument).not.toHaveBeenCalled();
    expect(await screen.findByText(/^Saved/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Discard draft' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
  });

  it('crew pass step 9: leaving the form refreshes the proposal record, so its page shows the draft', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const view = render(
      <QueryClientProvider client={client}>
        <QuotationFormClient projectId="p1" documentId="d1" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'left via Back' } });
    invalidate.mockClear();
    view.unmount();
    // After the leave flush has landed, so the re-read sees the draft.
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: quotationDocumentKey('p1', 'd1') }),
      ),
    );
    expect(saveQuotationFormDraft.mock.invocationCallOrder.at(-1)!).toBeLessThan(
      invalidate.mock.invocationCallOrder.at(-1)!,
    );
  });

  it('crew pass step 14: Discard draft refreshes the proposal record when it commits', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    const options = deferredOptions.mock.calls.at(-1)![0] as {
      actionKey: string;
      invalidateKeys?: unknown[][];
    };
    expect(options.actionKey).toBe('quotation_form_draft.discard');
    expect(options.invalidateKeys).toEqual(
      expect.arrayContaining([quotationDocumentKey('p1', 'd1')]),
    );
  });

  it('QUOTE-AUTOSAVE: opens on the draft when there is one, not on the record', async () => {
    openQuotationFormDraft.mockResolvedValue({
      draft_id: 'draft-1',
      token: 'tok-1',
      doc: {
        v: 1,
        header: { your_ref: 'FROM-DRAFT', subject_title: 'Draft subject' },
        letter: {},
        scopes: [{ key: 'q1', id: 'q1', scope_label: 'Townhouse', series_id: '' }],
        staged: {},
        removedIds: [],
        total: '0',
      },
      updated_at: '2026-11-10T06:14:00',
      updated_by_name: 'Aina',
    });
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('FROM-DRAFT'));
    // Opening on a draft is not an edit: nothing is written back.
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(saveQuotationFormDraft).not.toHaveBeenCalled();
  });

  it('QUOTE-AUTOSAVE: Save carries the form state and this tab\'s claim', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'NC/99' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    const body = updateQuotationDocument.mock.calls[0][2];
    expect(body.your_ref).toBe('NC/99');
    expect(body.form_token).toBe('tok-1');
    expect(body.form_state.header.your_ref).toBe('NC/99');
    // The autosave was flushed first, so the two cannot land out of order.
    expect(saveQuotationFormDraft).toHaveBeenCalled();
    expect(saveQuotationFormDraft.mock.invocationCallOrder[0]).toBeLessThan(
      updateQuotationDocument.mock.invocationCallOrder[0],
    );
  });

  // INSERT-SECTION-FIX B1: Save clears the server draft but this tab keeps its claim, so a change
  // landing after Save (a refetch re-seeding the form while the page navigates away) must not
  // write the draft back: the read page would then show an unsaved draft nobody made.
  it('after a successful Save, a later change writes no draft', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'NC/99' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1'));
    const draftsBefore = saveQuotationFormDraft.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'NC/100' } });
    await new Promise((resolve) => setTimeout(resolve, 1500));
    expect(saveQuotationFormDraft).toHaveBeenCalledTimes(draftsBefore);
  });

  // INSERT-SECTION-FIX B1 (review): with saving paused after Save, anything typed while the next
  // page loads would be lost silently, and a second click would send a second PATCH. The form stays
  // locked from a successful Save until the page has left.
  it('after a successful Save, the form stays locked while the page leaves', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'NC/99' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1'));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
    expect(screen.getByLabelText('Your Ref').closest('[inert]')).not.toBeNull();
    expect(updateQuotationDocument).toHaveBeenCalledTimes(1);
  });

  it('QUOTE-AUTOSAVE Q4: the older tab goes view-only, naming who opened it, and cannot Save', async () => {
    const { DraftNotHolderError } = await vi.importActual<
      typeof import('../../../_shared/services/quotationDocumentService')
    >('../../../_shared/services/quotationDocumentService');
    saveQuotationFormDraft.mockRejectedValue(
      new DraftNotHolderError('opened elsewhere', { holder_name: 'Ben', holder_at: null }),
    );
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'older tab' } });

    expect(
      await screen.findByText(/Opened in another tab \/ by Ben/, undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save proposal' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Discard draft' })).toBeNull();
    // The fields are locked: the whole form body is inert.
    expect(screen.getByLabelText('Your Ref').closest('[inert]')).not.toBeNull();
  });

  it('AC-QF023: a scope the customer holds shows its lines read-only and never sends them', async () => {
    listQuotationVersions.mockResolvedValue([version({ is_editable: false })]);
    renderForm('d1');
    await openTab('Header');
    const card = await waitFor(() => scopeCard('Townhouse'));
    await within(card).findByText('Wall-hung WC');

    expect(within(card).queryByRole('button', { name: 'Add a line' })).toBeNull();
    expect(within(card).queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() =>
      expect(updateQuotationDocument).toHaveBeenCalledTimes(1),
    );
    const body = updateQuotationDocument.mock.calls[0][2];
    expect(body.scopes[0]).not.toHaveProperty('lines');
  });

  it('AC-QF072: a saved scope nobody opened on the Lines tab is saved without its lines', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    const body = updateQuotationDocument.mock.calls[0][2];
    // The write replaces the WHOLE set, so a scope nobody touched is never re-sent.
    expect(body.scopes).toEqual([{ id: 'q1', scope_label: 'Townhouse', series_id: null }]);
  });

  it('AC-QF058: a saved scope nothing in which was sent can be removed, in the ONE PATCH', async () => {
    renderForm('d1');
    await openSavedLines();

    // Offered once the scope's versions are known (nothing in it was sent).
    await waitFor(async () => {
      const item = await removeItemOf('Townhouse');
      expect(item).not.toHaveAttribute('data-disabled');
    });
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove scope' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Townhouse' })).toBeNull());
    expect(updateQuotationDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    const body = updateQuotationDocument.mock.calls[0][2];
    expect(body.remove_scope_ids).toEqual(['q1']);
    expect(body.scopes).toEqual([]);
  });

  it('AC-QF058: a scope any version of which was sent to the customer offers no Remove', async () => {
    listQuotationVersions.mockResolvedValue([
      version({ id: 'v2', version_no: 2, is_current: true, is_editable: true }),
      version({ id: 'v1', version_no: 1, is_current: false, is_editable: false, is_issued: true }),
    ]);
    renderForm('d1');
    await openSavedLines();

    expect(await removeItemOf('Townhouse')).toHaveAttribute('data-disabled');
  });

  it('AC-QF060: a header-only edit saves the letterhead with no scope change', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Attn'), { target: { value: 'Mr Tan' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    expect(updateQuotationDocument.mock.calls[0][2]).toMatchObject({ attn_name: 'Mr Tan' });
    expect(updateQuotationDocument.mock.calls[0][2]).not.toHaveProperty('remove_scope_ids');
  });
});

describe('QuotationFormClient guards', () => {
  it('refuses a quantity that is not a number before any request', async () => {
    renderForm();
    const card = await openLines();
    await nameScope(card, 'Townhouse');
    const named = scopeCard('Townhouse');
    await addLine(named, 1);
    await pickProduct(named, 1);
    fireEvent.change(within(named).getByRole('textbox', { name: 'Qty on SRT-BASIN-02' }), {
      target: { value: 'two' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    expect(
      await screen.findByText(
        /One line has a quantity or unit price that is not a number/i,
      ),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });

  it('QUOTE-AUTOSAVE: no leave-the-page prompt; closing the tab sends the draft instead', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'NC/21' } });

    const leaving = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(leaving);
    expect(leaving.defaultPrevented).toBe(false);

    window.dispatchEvent(new Event('pagehide'));
    await waitFor(() => expect(saveQuotationFormDraft).toHaveBeenCalled());
    const call = saveQuotationFormDraft.mock.calls.at(-1)!;
    expect(call[2].header.your_ref).toBe('NC/21');
    expect(call[4]).toEqual({ keepalive: true });
  });
});

/**
 * Fix round 2 (#1341, owner alignment notes 11:33Z): "header stays in header tab", "show them on
 * create as well", "yes can, header only is fine".
 */
describe('QuotationFormClient tabs (AC-QF055)', () => {
  // No Lines tab since PROPOSAL-HEADER-LAYOUT: the lines sit under the letterhead on Header.
  it('create reads Header, Cover letter, Terms as tabs; Header holds the letterhead and the lines', async () => {
    renderForm();

    expect(await formTabNames()).toEqual(['Header', 'Cover letter', 'Terms']);
    expect(screen.getByRole('tab', { name: 'Header' })).toHaveAttribute('data-state', 'active');
    expect(await screen.findByRole('textbox', { name: 'Your Ref' })).toBeInTheDocument();
    await openLines();
    expect(scopeCard('Scope 1')).toBeInTheDocument();

    await openTab('Terms');
    expect(screen.queryByRole('textbox', { name: 'Your Ref' })).toBeNull();
  });

  it('holds recipient, attention, your ref, date, subject and address in the Header tab', async () => {
    renderForm();

    for (const label of ['Name', 'Address', 'Attn', 'Your Ref', 'Date', 'Project title']) {
      expect(await screen.findByLabelText(label)).toBeInTheDocument();
    }
  });

  it('edit uses the same three tabs in the same order', async () => {
    renderForm('d1');

    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    expect(await formTabNames()).toEqual(['Header', 'Cover letter', 'Terms']);
  });
});

describe('QuotationFormClient letter on create (AC-QF056)', () => {
  it('prefills Cover letter and Terms from the company templates, editable before Save', async () => {
    renderForm();

    await openTab('Cover letter');
    const letter = await screen.findByRole('textbox', {
      name: 'Intro text',
    });
    expect(letter).toHaveValue('<p>Dear {{attn_name}}</p>');
    fireEvent.change(letter, { target: { value: '<p>Dear {{attn_name}}, edited</p>' } });

    await openTab('Terms');
    expect(
      await screen.findByRole('textbox', { name: 'The clauses the customer holds us to' }),
    ).toHaveValue('<p>Valid 30 days</p>');

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1]).toMatchObject({
      cover_letter_html: '<p>Dear {{attn_name}}, edited</p>',
      terms_html: '<p>Valid 30 days</p>',
    });
  });

  it('opens with empty letter tabs when the company has no template, and still saves', async () => {
    getQuotationLetterTemplates.mockResolvedValue({ cover_letter_html: null, terms_html: null });
    renderForm();

    await openTab('Cover letter');
    expect(
      await screen.findByRole('textbox', {
        name: 'Intro text',
      }),
    ).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1]).not.toHaveProperty('cover_letter_html');
  });
});

describe('QuotationFormClient header-only save (AC-QF060)', () => {
  it('saves a create that touched only the Header, sending no empty scope', async () => {
    renderForm();
    fireEvent.change(await screen.findByLabelText('Your Ref'), { target: { value: 'NC/30' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    const body = createQuotationDocument.mock.calls[0][1];
    expect(body).toMatchObject({ your_ref: 'NC/30', scopes: [] });
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d-new'),
    );
  });

  it('still refuses a scope that has lines but no name, and opens Header (where the lines are) to show it', async () => {
    renderForm();
    const card = await openLines();
    await addLine(card, 1);
    fireEvent.change(await openDescription(card, 'line 1'), { target: { value: 'Grab bar' } });
    await openTab('Terms');

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));

    expect(await screen.findByText(/Every scope needs a name/i)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Header' })).toHaveAttribute('data-state', 'active');
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });
});

describe('QuotationFormClient from the Overview (AC-QF061)', () => {
  it('opens cleanly for a project with no quotation, with no Cancel (leaving keeps the draft)', async () => {
    listQuotations.mockResolvedValue([]);
    renderForm();

    expect(await screen.findByRole('heading', { level: 1, name: 'New proposal' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Your Ref')).toHaveValue('');
    expect(getQuotationDocument).not.toHaveBeenCalled();
    expect(screen.queryByText(/could not be loaded/i)).toBeNull();

    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });
});

describe('QuotationFormClient review round (fix round 2)', () => {
  it('AC-QF058: without the delete grant a saved scope offers no Remove; a new one still does', async () => {
    granted = new Set(['projects.projects.view', 'projects.projects.edit']);
    renderForm('d1');
    const card = await openLines('Townhouse');
    await within(card).findByRole('textbox', { name: 'Qty on SRT-WC-01' });

    expect(await removeItemOf('Townhouse')).toHaveAttribute('data-disabled');
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menuitem')).toBeNull());
    await addScope('Reception');
    expect(await removeItemOf('Reception')).not.toHaveAttribute('data-disabled');
  });

  it('AC-QF052: a scope removed on the form leaves the Header details too', async () => {
    listQuotationVersions.mockResolvedValue([version({ issued_by_name: 'Baser Ramli' })]);
    renderForm('d1');
    await openTab('Header');
    expect(await screen.findByText('Baser Ramli')).toBeInTheDocument();

    await openLines('Townhouse');
    await waitFor(async () => {
      const item = await removeItemOf('Townhouse');
      expect(item).not.toHaveAttribute('data-disabled');
    });
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove scope' }));
    await openTab('Header');
    expect(screen.queryByText('Baser Ramli')).toBeNull();
  });

  it('AC-QF056: keeps Save off on create until the letter templates have answered', async () => {
    let answer: (value: { cover_letter_html: string | null; terms_html: string | null }) => void =
      () => {};
    getQuotationLetterTemplates.mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    renderForm();
    await screen.findByLabelText('Your Ref');

    expect(screen.getByRole('button', { name: 'Save proposal' })).toBeDisabled();
    answer({ cover_letter_html: '<p>Hi</p>', terms_html: null });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save proposal' })).toBeEnabled(),
    );
  });
});

describe('QuotationFormClient scope tab context menu (owner hand test)', () => {
  const tabOf = (name: string) => screen.getByRole('tab', { name });

  it('right-clicking a scope tab opens Rename and Remove scope', async () => {
    renderForm();
    await openLines();
    fireEvent.contextMenu(tabOf('Scope 1'));
    expect(await screen.findByRole('menuitem', { name: 'Rename' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Remove scope' })).toBeInTheDocument();
  });

  it('Rename opens the Edit scope dialog for that scope', async () => {
    renderForm();
    await openLines();
    fireEvent.contextMenu(tabOf('Scope 1'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('textbox', { name: /^Scope/ })).toHaveValue('Scope 1');
    expect(within(dialog).getByText('Series')).toBeInTheDocument();
  });

  it('Remove scope from the menu has the same staged result as the button: gone now, one PATCH on Save', async () => {
    renderForm('d1');
    const card = await waitFor(() => scopeCard('Townhouse'), { timeout: 3000 }).catch(async () => {
      await openTab('Header');
      return waitFor(() => scopeCard('Townhouse'));
    });
    expect(card).toBeInTheDocument();
    fireEvent.contextMenu(tabOf('Townhouse'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove scope' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Townhouse' })).toBeNull());
    expect(updateQuotationDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    const body = updateQuotationDocument.mock.calls[0][2];
    expect(body.remove_scope_ids).toEqual(['q1']);
    expect(body.scopes).toEqual([]);
  });

  it('QUOTE-SCOPE-COMPACT: only the open tab carries the Scope actions trigger (touch / 375 px)', async () => {
    renderForm();
    await openLines();
    await addScope('Guard House');
    expect(screen.getByRole('button', { name: 'Scope actions on Guard House' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Scope actions on Scope 1' })).toBeNull();
  });

  it('QUOTE-SCOPE-COMPACT: the trigger opens the same Rename and Remove scope as the right-click', async () => {
    renderForm();
    await openLines();
    await addScope('Guard House');
    await scopeAction('Guard House', 'Remove scope');
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'Guard House' })).toBeNull());
    expect(screen.getByRole('region', { name: 'Scope 1' })).toBeInTheDocument();
  });

  it('the read page strip (no form handlers) has no context menu', async () => {
    render(
      <QuotationScopeTabs
        scopes={[{ id: 'q1', scope_label: 'Scope 1', scope_total: '9000.00' } as never]}
        activeScopeId="q1"
        onSelect={() => {}}
        canEdit
      />,
    );
    fireEvent.contextMenu(screen.getByRole('tab', { name: 'Scope 1' }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole('menuitem')).toBeNull();    // Nor the touch trigger: the read page has no scope actions at all.
    expect(screen.queryByRole('button', { name: 'Scope actions on Scope 1' })).toBeNull();
  });

  it('right-clicking a scope tab that is not the active one selects it before the menu opens', async () => {
    renderForm();
    await openLines();
    await addScope('Guard House');
    // Guard House is now active; right-click the other one.
    expect(screen.getByRole('tab', { name: 'Guard House' })).toHaveAttribute('data-state', 'active');
    fireEvent.contextMenu(screen.getByRole('tab', { name: 'Scope 1' }));
    await screen.findByRole('menuitem', { name: 'Rename' });
    expect(screen.getByRole('tab', { name: 'Scope 1' })).toHaveAttribute('data-state', 'active');
  });
});

describe('QuotationFormClient sole series default (QUOTE-UI-POLISH)', () => {
  /** The series the open scope's line table judges against, as the form hands it in. */
  function editorSeries() {
    return editorProps.mock.calls.at(-1)?.[0]?.seriesId ?? null;
  }

  it('AC-QUP-5: with one active series, every new scope carries it and Save writes it', async () => {
    renderForm();
    const card = await openLines();
    // The scope itself carries it, before anybody opens the Edit scope dialog.
    await waitFor(() => expect(editorSeries()).toBe('s1'));
    await nameScope(card, 'Townhouse');

    // Add a scope asks for a name only; the new scope still starts on the one series.
    await addScope('Guard House');
    await waitFor(() => expect(editorSeries()).toBe('s1'));

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1].scopes).toEqual([
      expect.objectContaining({ scope_label: 'Townhouse', series_id: 's1' }),
      expect.objectContaining({ scope_label: 'Guard House', series_id: 's1' }),
    ]);
  });

  it('AC-QUP-5: with two active series, a new scope starts with none', async () => {
    listSeries.mockResolvedValue([
      { id: 's1', name: 'Premium Series', is_active: true, category_ids: [], category_names: [] },
      { id: 's2', name: 'Retail', is_active: true, category_ids: [], category_names: [] },
    ]);
    renderForm();
    const card = await openLines();
    await nameScope(card, 'Townhouse');
    await addScope('Guard House');

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1].scopes).toEqual([
      expect.objectContaining({ scope_label: 'Townhouse', series_id: null }),
      expect.objectContaining({ scope_label: 'Guard House', series_id: null }),
    ]);
  });

  it('AC-QUP-6: the defaulted series does not make the blank first scope count as touched', async () => {
    renderForm();
    await openLines();
    await waitFor(() => expect(editorSeries()).toBe('s1'));
    await openTab('Header');
    fireEvent.change(screen.getByLabelText('Your Ref'), { target: { value: 'NC/31' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1]).toMatchObject({ your_ref: 'NC/31', scopes: [] });
  });

  it('AC-QUP-4: a new scope whose series was cleared stays cleared, reopened and saved', async () => {
    renderForm();
    await openLines();
    await addScope('Guard House');
    await waitFor(() => expect(editorSeries()).toBe('s1'));

    await scopeAction('Guard House', 'Rename');
    let dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Series' })).toHaveTextContent('Premium Series'),
    );
    fireEvent.pointerDown(within(dialog).getByRole('button', { name: 'Clear selection' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    // Reopened (a rename, say): the cleared series is not put back.
    await scopeAction('Guard House', 'Rename');
    dialog = await screen.findByRole('dialog');
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(dialog).getByRole('combobox', { name: 'Series' })).toHaveTextContent('No series');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1].scopes).toEqual([
      expect.objectContaining({ scope_label: 'Guard House', series_id: null }),
    ]);
  });

  it('AC-QUP-5: the series list arriving after the first scope is seeded still defaults it', async () => {
    let answer: (rows: unknown[]) => void = () => undefined;
    listSeries.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderForm();
    await openLines();
    expect(editorSeries()).toBeNull();

    answer([{ id: 's1', name: 'Premium Series', is_active: true, category_ids: [], category_names: [] }]);
    await waitFor(() => expect(editorSeries()).toBe('s1'));
  });

  it('AC-QUP-1: a saved scope with no series opens Edit scope on the one series', async () => {
    renderForm('d1');
    await openLines('Townhouse');
    await scopeAction('Townhouse', 'Rename');
    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Series' })).toHaveTextContent(
        'Premium Series',
      ),
    );
  });
});

/**
 * QUOTE-COVER-PAGE (UAC B1, B2): Email and Quotation Purpose on the Header tab, Payment Terms and
 * Validity on the Terms tab, Prepared By read-only under the header. On create they prefill from
 * the project's main contact email and the active terms template; Save carries all four.
 */
describe('QuotationFormClient cover page fields', () => {
  const withEmail = (extra: Partial<Project> = {}) =>
    project({
      customer_id: 'cust-1',
      customer_name: 'Gamuda Builders Sdn Bhd',
      customer_attn: 'Lim Wei Ming',
      owner_name: 'Ahmad Faizal',
      ...({ customer_email: 'lim.weiming@example.test' } as unknown as Partial<Project>),
      ...extra,
    });
  const templates = {
    cover_letter_html: '<p>Dear {{attn_name}}</p>',
    terms_html: '<p>Valid 30 days</p>',
    payment_terms: '30 days net',
    validity: '60 days',
    payment_term_id: 'pt-cbd',
    validity_value: 2,
    validity_unit: 'week',
  };

  it('create prefills Email from the project customer email', async () => {
    getProject.mockResolvedValue(withEmail());
    getQuotationLetterTemplates.mockResolvedValue(templates);
    renderForm();

    await waitFor(() =>
      expect(screen.getByLabelText('Email')).toHaveValue('lim.weiming@example.test'),
    );
    // Quotation Purpose is gone from the form (owner, 10 Nov 2026).
    expect(screen.queryByLabelText('Quotation Purpose')).toBeNull();
  });

  it('create prefills Payment Terms and Validity from the letter templates', async () => {
    getProject.mockResolvedValue(withEmail());
    getQuotationLetterTemplates.mockResolvedValue(templates);
    renderForm();

    await openTab('Terms');
    await waitFor(() =>
      expect(JSON.parse(screen.getByLabelText('Terms values').textContent ?? '{}')).toMatchObject({
        payment_term_id: 'pt-cbd',
        payment_terms: '30 days net',
        validity_value: 2,
        validity_unit: 'week',
        validity: '60 days',
      }),
    );
    expect(screen.getByLabelText('Terms project')).toHaveTextContent('p1');
  });

  it('shows Prepared By read-only as whoever creates the quotation, not the project owner (owner, 11 Nov)', async () => {
    // The creator here is the effective user of a view-as: the backend saves created_by as them.
    const { impersonationStore } = await import('@/lib/impersonation-store');
    impersonationStore.setSession({
      sessionId: 'imp-1',
      startedAt: '2026-11-11T00:00:00Z',
      targetUser: { id: 'u-9', name: 'Test Creator B', email: 'b@x.test', avatar: null, role_name: null },
    });
    try {
      getProject.mockResolvedValue(withEmail());
      getQuotationLetterTemplates.mockResolvedValue(templates);
      renderForm();

      expect(await screen.findByText('Prepared By')).toBeInTheDocument();
      expect(screen.getByText('Test Creator B')).toBeInTheDocument();
      expect(screen.queryByText('Ahmad Faizal')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Prepared By')).not.toBeInTheDocument();
    } finally {
      impersonationStore.setSession(null);
    }
  });

  it('Save sends recipient_email_snapshot, the terms and their picks, and no quotation_purpose', async () => {
    getProject.mockResolvedValue(withEmail());
    getQuotationLetterTemplates.mockResolvedValue(templates);
    renderForm();

    await waitFor(() =>
      expect(screen.getByLabelText('Email')).toHaveValue('lim.weiming@example.test'),
    );
    await openTab('Terms');
    fireEvent.click(await screen.findByRole('button', { name: 'Pick 90 days' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1]).toMatchObject({
      recipient_email_snapshot: 'lim.weiming@example.test',
      payment_terms: '30 days net',
      // The template's pick rides with the create.
      payment_term_id: 'pt-cbd',
      validity: '90 DAYS',
      validity_value: 90,
      validity_unit: 'day',
    });
    expect(createQuotationDocument.mock.calls[0][1]).not.toHaveProperty('quotation_purpose');
  });

  it('an invalid validity on screen blocks Save and shows the Terms tab (crew pass 538d14b7)', async () => {
    getProject.mockResolvedValue(withEmail());
    getQuotationLetterTemplates.mockResolvedValue(templates);
    renderForm();

    await openTab('Terms');
    fireEvent.click(await screen.findByRole('button', { name: 'Type an invalid validity' }));
    await openTab('Header');
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    expect(
      await screen.findByText('Validity needs a whole number from 1 to 999 and a unit.'),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();
    expect(screen.getByRole('tab', { name: /Terms/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('with no active template the terms start empty and Save sends no picks', async () => {
    getProject.mockResolvedValue(withEmail());
    getQuotationLetterTemplates.mockResolvedValue({ cover_letter_html: null, terms_html: null });
    renderForm();

    await openTab('Terms');
    await waitFor(() =>
      expect(JSON.parse(screen.getByLabelText('Terms values').textContent ?? '{}')).toMatchObject({
        payment_terms: '',
        validity: '',
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    const body = createQuotationDocument.mock.calls[0][1];
    expect(body).not.toHaveProperty('payment_term_id');
    expect(body).not.toHaveProperty('validity_value');
  });

  it('edit keeps a legacy validity untouched and PATCH carries a picked Payment Term', async () => {
    getQuotationDocument.mockResolvedValue(
      document({
        ...({
          recipient_email_snapshot: 'saved@example.test',
          quotation_purpose: 'Saved purpose',
          payment_terms: 'Saved payment',
          validity: 'Saved validity',
        } as unknown as Partial<QuotationDocument>),
      }),
    );
    renderForm('d1');

    await waitFor(() => expect(screen.getByLabelText('Email')).toHaveValue('saved@example.test'));
    // A stored purpose stays in the column but is no longer shown or sent.
    expect(screen.queryByLabelText('Quotation Purpose')).toBeNull();
    expect(screen.queryByText('Saved purpose')).toBeNull();
    await openTab('Terms');
    expect(
      JSON.parse((await screen.findByLabelText('Terms values')).textContent ?? '{}'),
    ).toMatchObject({ payment_term_id: null, payment_terms: 'Saved payment', validity: 'Saved validity' });
    fireEvent.click(screen.getByRole('button', { name: 'Pick CBD' }));
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    const body = updateQuotationDocument.mock.calls[0][2];
    expect(body).toMatchObject({
      payment_term_id: 'pt-cbd',
      payment_terms: 'CASH BEFORE DELIVERY',
      validity: 'Saved validity',
    });
    expect(body).not.toHaveProperty('validity_value');
  });

  it('edit shows Prepared By from the saved quotation, not the project owner', async () => {
    getProject.mockResolvedValue(withEmail({ owner_name: 'Wrong Project Owner' }));
    getQuotationDocument.mockResolvedValue(
      document({ ...({ prepared_by: 'Saved Creator' } as unknown as Partial<QuotationDocument>) }),
    );
    renderForm('d1');

    expect(await screen.findByText('Saved Creator')).toBeInTheDocument();
    expect(screen.queryByText('Wrong Project Owner')).not.toBeInTheDocument();
  });
});


/** QUOTE-COVER-DESIGN (UAC B1, B2): the Cover letter tab is a preview card plus Intro/Closing editors. */
describe('QuotationFormClient cover page preview and editors', () => {
  const previewBody = () =>
    new Response(
      JSON.stringify({
        cover_title: 'OFFER SHEET',
        cover_show_letterhead: true,
        cover_rows: [{ key: 'reference', label: 'Offer Number', text: 'SRT/Q/2026/0141-R1 Menara Test' }],
        cover_intro_html: '<p>INTRO PREVIEW</p>',
        cover_closing_html: '<p>CLOSING PREVIEW</p>',
        sender_name: 'Sorento Sdn Bhd',
        sender_logo_url: null,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  const lastPreviewBody = () => {
    const init = coverPreview.mock.calls.at(-1)?.[1] as RequestInit | undefined;
    return init?.body ? JSON.parse(String(init.body)) : null;
  };

  beforeEach(() => {
    coverPreview.mockReset();
    coverPreview.mockImplementation(async () => previewBody());
  });

  it('shows the preview card from the preview endpoint with the design title and rows', async () => {
    renderForm();
    await openTab('Cover letter');

    expect(await screen.findByText('OFFER SHEET')).toBeInTheDocument();
    expect(screen.getByText('Offer Number')).toBeInTheDocument();
    expect(screen.getByText('SRT/Q/2026/0141-R1 Menara Test')).toBeInTheDocument();
    expect((coverPreview.mock.calls[0][1] as RequestInit).method).toBe('POST');
  });

  it('M1: a new proposal prints PROPOSAL FROM on the cover letter tab, not QUOTATION FROM', async () => {
    renderForm();
    await openTab('Cover letter');

    expect(await screen.findByText('OFFER SHEET')).toBeInTheDocument();
    expect(screen.getByText('Proposal from')).toBeInTheDocument();
    expect(screen.queryByText('Quotation from')).toBeNull();
  });

  it('has Intro text and Closing text editors, the intro prefilled from the template', async () => {
    renderForm();
    await openTab('Cover letter');

    expect(await screen.findByLabelText('Intro text')).toHaveValue('<p>Dear {{attn_name}}</p>');
    expect(screen.getByLabelText('Closing text')).toBeInTheDocument();
  });

  it('the preview follows an unsaved intro edit', async () => {
    renderForm();
    await openTab('Cover letter');
    fireEvent.change(await screen.findByLabelText('Intro text'), { target: { value: '<p>EDITED INTRO</p>' } });

    await waitFor(() => expect(lastPreviewBody()).toMatchObject({ cover_letter_html: '<p>EDITED INTRO</p>' }), {
      timeout: 4000,
    });
  });

  it('B2: the preview body follows unsaved closing, Attn and terms edits from other tabs', async () => {
    renderForm();
    await openTab('Header');
    fireEvent.change(await screen.findByLabelText('Attn'), { target: { value: 'Mr Preview' } });
    await openTab('Terms');
    fireEvent.change(await screen.findByRole('textbox', { name: 'The clauses the customer holds us to' }), {
      target: { value: '<p>TERMS EDITED</p>' },
    });
    await openTab('Cover letter');
    fireEvent.change(await screen.findByLabelText('Closing text'), { target: { value: '<p>CLOSING EDITED</p>' } });

    await waitFor(
      () =>
        expect(lastPreviewBody()).toMatchObject({
          cover_closing_html: '<p>CLOSING EDITED</p>',
          attn_name: 'Mr Preview',
          terms_html: '<p>TERMS EDITED</p>',
        }),
      { timeout: 4000 },
    );
  });

  it('save sends cover_letter_html and cover_closing_html', async () => {
    renderForm();
    await openTab('Cover letter');
    fireEvent.change(await screen.findByLabelText('Intro text'), { target: { value: '<p>Intro typed</p>' } });
    fireEvent.change(screen.getByLabelText('Closing text'), { target: { value: '<p>Closing typed</p>' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    expect(createQuotationDocument.mock.calls[0][1]).toMatchObject({
      cover_letter_html: '<p>Intro typed</p>',
      cover_closing_html: '<p>Closing typed</p>',
    });
  });
});


/** QUOTE-COVER-DESIGN round 2: the editors' names come from a visible label, not the placeholder. */
describe('QuotationFormClient cover editor labels', () => {
  it('Intro text and Closing text are named by their label with seeded text present', async () => {
    renderForm();
    await openTab('Cover letter');
    const intro = await screen.findByRole('textbox', { name: 'Intro text' });
    expect(intro).toHaveValue('<p>Dear {{attn_name}}</p>');
    expect(screen.getByRole('textbox', { name: 'Closing text' })).toBeInTheDocument();
  });
});

describe('QuotationFormClient: open feedback on the revision-2 draft (PS-QUOTE-MATRIX fix round 2)', () => {
  it('marks the draft line the v1 note names, while it is being edited', async () => {
    listQuotationVersions.mockResolvedValue([
      version({ id: 'v1', version_no: 1, is_current: false, is_editable: false, is_issued: true }),
      version({ id: 'v2', version_no: 2, is_current: true, is_editable: true }),
    ]);
    listQuotationLines.mockImplementation(async (versionId: string) =>
      versionId === 'v1'
        ? [{ ...LINE, id: 'l1', version_id: 'v1' }]
        : [{ ...LINE, id: 'l1-v2', version_id: 'v2' }],
    );
    getQuotationFeedback.mockResolvedValue({
      open_count: 1,
      requests: [
        {
          id: 'r1',
          issue_label: 'Rev A',
          submitted_at: null,
          requester_name: null,
          note: null,
          rows: [
            {
              id: 'f1',
              line_id: 'l1',
              scope_id: 'q1',
              scope_label: 'Townhouse',
              line_description: 'Wall-hung WC',
              cell_key: null,
              cell_label: null,
              kind: 'note',
              value_from: null,
              value_to: null,
              model: null,
              note: 'Check the WC',
              handled_at: null,
              handled_by_name: null,
            },
          ],
        },
      ],
    });
    renderForm('d1');
    const card = await openLines('Townhouse');
    await within(card).findByRole('textbox', { name: 'Qty on SRT-WC-01' });

    expect(await screen.findByTestId('line-feedback-dot')).toBeInTheDocument();
    expect(getQuotationFeedback).toHaveBeenCalledWith('p1', 'd1');
  });
});

/**
 * Owner, hand test (3 Nov): the create view must behave like the edit view. Rule of 28 Oct: create,
 * edit and view of a form are identical and use the same component. So New proposal has the grid
 * editor Edit proposal has, column headers included, and Save carries the new scope's columns.
 */
describe('QuotationFormClient: New and Edit proposal are one editor (PS-QUOTE-MATRIX)', () => {
  /** What the open scope's grid offers: the controls and the header/footer it draws. */
  function gridShape(card: HTMLElement) {
    const table = within(card).getByRole('table');
    return {
      headerInputs: within(table)
        .queryAllByRole('textbox')
        .map((input) => input.getAttribute('aria-label'))
        .filter((label) => label?.startsWith('Column header')),
      columnHeaders: within(table)
        .getAllByRole('columnheader')
        .map((th) => (th.textContent ?? '').trim())
        .filter(Boolean),
      footer: (table.querySelector('tfoot')?.textContent ?? '').replace(/\s+/g, ' ').trim(),
    };
  }

  it('offers + Column header on a new scope exactly as on a saved one', async () => {
    renderForm();
    const created = await openLines();
    expect(within(created).getByRole('button', { name: 'Column header' })).toBeInTheDocument();
    cleanup();

    renderForm('d1');
    const edited = await openLines('Townhouse');
    expect(within(edited).getByRole('button', { name: 'Column header' })).toBeInTheDocument();
  });

  it('draws the same header and footer for a scope with columns, new or saved', async () => {
    // Create: a new scope gets its first column header from the same control.
    renderForm();
    const created = await openLines();
    await addLine(created, 1);
    fireEvent.click(within(created).getByRole('button', { name: 'Column header' }));
    await within(created).findByRole('textbox', { name: 'Column header Header 1' });
    const createShape = gridShape(created);
    cleanup();

    // Edit: a saved scope whose version holds that same header.
    listQuotationVersions.mockResolvedValue([
      version({ matrix_columns: [{ key: 'h1', label: 'Header 1', cols: [] }] }),
    ]);
    listQuotationLines.mockResolvedValue([{ ...LINE, qty_cells: { h1: '10.00' } }]);
    renderForm('d1');
    const edited = await openLines('Townhouse');
    await within(edited).findByRole('textbox', { name: 'Column header Header 1' });
    const editShape = gridShape(edited);

    expect(createShape.headerInputs).toEqual(['Column header Header 1']);
    expect(createShape.headerInputs).toEqual(editShape.headerInputs);
    expect(createShape.columnHeaders).toEqual(editShape.columnHeaders);
    expect(createShape.columnHeaders).toContain('Total qty');
    expect(createShape.columnHeaders).not.toContain('Qty');
    expect(createShape.footer).toMatch(/Total qty.*Total \(RM\)/);
    expect(editShape.footer).toMatch(/Total qty.*Total \(RM\)/);
  });

  it('Save on create sends the new scope\'s columns and each line\'s cells in the one request', async () => {
    renderForm();
    await nameScope(await openLines(), 'Townhouse');
    const card = scopeCard('Townhouse');
    await addLine(card, 1);
    await pickProduct(card, 1);
    fireEvent.click(within(card).getByRole('button', { name: 'Column header' }));
    await within(card).findByRole('textbox', { name: 'Column header Header 1' });
    fireEvent.change(within(card).getByRole('textbox', { name: /^Qty on SRT-BASIN-02, Header 1/ }), {
      target: { value: '995' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    const [, body] = createQuotationDocument.mock.calls[0];
    const [scope] = body.scopes;
    expect(scope.matrix_columns).toEqual([{ key: expect.any(String), label: 'Header 1', cols: [] }]);
    const key = scope.matrix_columns[0].key;
    expect(scope.lines).toEqual([
      expect.objectContaining({ product_id: 'p9', qty_cells: { [key]: '995' }, quantity: '995.00' }),
    ]);
  });
});

describe('QuotationFormClient round 4: Copy columns from on New proposal', () => {
  it('a second unsaved section copies the first one\'s headers and columns (fresh keys, no quantities)', async () => {
    renderForm();
    await nameScope(await openLines(), 'UNIT');
    const unit = scopeCard('UNIT');
    await addLine(unit, 1);
    await pickProduct(unit, 1);
    fireEvent.click(within(unit).getByRole('button', { name: 'Column header' }));
    await within(unit).findByRole('textbox', { name: 'Column header Header 1' });
    fireEvent.click(within(unit).getByRole('button', { name: '+ Column' }));
    await within(unit).findByRole('textbox', { name: 'Column Column 1' });
    fireEvent.change(within(unit).getByRole('textbox', { name: /^Qty on SRT-BASIN-02, Header 1 \/ Column 1/ }), {
      target: { value: '7' },
    });

    const second = await addScope('LEVEL 9');
    const trigger = within(second).getByRole('button', { name: /Copy columns from/ });
    fireEvent.keyDown(trigger, { key: 'Enter' });
    const menu = await screen.findByRole('menu');
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'UNIT' }));

    const card = scopeCard('LEVEL 9');
    expect(await within(card).findByRole('textbox', { name: 'Column header Header 1' })).toBeInTheDocument();
    expect(within(card).getByRole('textbox', { name: 'Column Column 1' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(createQuotationDocument).toHaveBeenCalledTimes(1));
    const [, body] = createQuotationDocument.mock.calls[0];
    const [first, copy] = body.scopes;
    expect(copy.matrix_columns.map((h: { label: string }) => h.label)).toEqual(['Header 1']);
    expect(copy.matrix_columns[0].cols.map((c: { label: string }) => c.label)).toEqual(['Column 1']);
    // Fresh keys, never the source's; and no quantities come across.
    expect(copy.matrix_columns[0].key).not.toBe(first.matrix_columns[0].key);
    expect(copy.matrix_columns[0].cols[0].key).not.toBe(first.matrix_columns[0].cols[0].key);
    expect(copy.lines).toEqual([]);
  });
});

describe('QuotationFormClient: an unsaved line keeps its product code across a section switch', () => {
  it('New proposal: pick a product, open another section and come back, and the code is still there', async () => {
    renderForm();
    const first = await openLines();
    await addLine(first, 1);
    await pickProduct(first, 1);

    await addScope('Guard House');
    fireEvent.mouseDown(screen.getByRole('tab', { name: /^Scope 1/ }), { button: 0 });
    const back = await waitFor(() => scopeCard('Scope 1'));

    const picker = await within(back).findByRole('combobox', { name: 'Product on SRT-BASIN-02' });
    expect(picker).toHaveTextContent('SRT-BASIN-02');
    expect(within(back).queryByText('Selected product')).toBeNull();
  });
});


// ---------------------------------------------------------------------------------------------
// PROPOSAL-HEADER-LAYOUT, owner hand test (5 Nov 2026): "the Lines also should be align with the
// view page also". The form reads like the view: no Lines tab, the lines under the letterhead on
// the Header tab, no per-area Won/Lost pill, no version row; the version and Recheck alerts sit in
// the record card at the top, as on the view page.
// ---------------------------------------------------------------------------------------------
describe('QuotationFormClient aligned with the view page (PROPOSAL-HEADER-LAYOUT)', () => {
  it('F1: create and edit read Header, Cover letter, Terms (no Lines tab)', async () => {
    const { unmount } = renderForm();
    await screen.findByLabelText('Your Ref');
    expect(await formTabNames()).toEqual(['Header', 'Cover letter', 'Terms']);
    unmount();

    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    expect(await formTabNames()).toEqual(['Header', 'Cover letter', 'Terms']);
  });

  it('F2: the Header tab holds the letterhead fields AND the editable lines under them', async () => {
    renderForm('d1');

    expect(await screen.findByRole('textbox', { name: 'Your Ref' })).toBeInTheDocument();
    const card = await waitFor(() => scopeCard('Townhouse'));
    expect(await within(card).findByRole('button', { name: 'Add a line' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Add a section' })).toBeInTheDocument();
  });

  it('F3: no per-area Won/Lost pill anywhere on the form', async () => {
    listQuotations.mockResolvedValue([{ ...SCOPE, outcome: 'won' }]);
    getQuotationDocument.mockResolvedValue(
      document({
        scopes: [{ ...document().scopes![0], outcome: 'won' }],
      }),
    );
    renderForm('d1');

    const card = await waitFor(() => scopeCard('Townhouse'));
    await within(card).findByRole('button', { name: 'Add a line' });
    expect(screen.queryByText('Won')).toBeNull();
  });

  it('F4: no version row above the lines; the version is a chip in the record card', async () => {
    renderForm('d1');

    const card = await waitFor(() => scopeCard('Townhouse'));
    await within(card).findByRole('button', { name: 'Add a line' });
    expect(
      screen
        .queryAllByRole('button', { name: /^v\d/ })
        .filter((button) => button.hasAttribute('aria-current')),
    ).toHaveLength(0);
    expect(within(card).queryByRole('button', { name: /Recheck alerts/ })).toBeNull();
    const header = await screen.findByTestId('record-header-card');
    expect(within(header).getByRole('heading', { name: 'PRJQ-2026-0002' })).toBeInTheDocument();
    expect(await within(header).findByText('v1')).toBeInTheDocument();
  });

  // Owner hand test (5 Nov 2026) struck Recheck alerts from the edit page: it lives in the view
  // page's gear only.
  it('F5: the edit page offers no Recheck alerts, in the card or above the lines', async () => {
    renderForm('d1');

    const header = await screen.findByTestId('record-header-card');
    const card = await waitFor(() => scopeCard('Townhouse'));
    await within(card).findByRole('button', { name: 'Add a line' });
    expect(within(header).getByText('v1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Recheck alerts/ })).toBeNull();
    expect(recomputeQuotationVersion).not.toHaveBeenCalled();
  });

  // QUOTE-HEADER-TIDY (owner, 11 Nov 2026): the record card names the project by its short name;
  // the full title is the Header's own Project title field below it.
  it('F7: the record card reads the project short name, not the full title', async () => {
    const savedTitle = 'Menara Test';
    getProject.mockResolvedValue(project({ name: 'Menara Ujian' }));
    renderForm('d1');

    const header = await screen.findByTestId('record-header-card');
    expect(await within(header).findByText('Menara Ujian')).toBeInTheDocument();
    const field = await screen.findByLabelText('Project title');
    expect(field).toHaveValue(savedTitle);
    expect(within(header).queryByText(savedTitle)).toBeNull();
  });

  it('F6: a new proposal has no record card yet (nothing numbered, no version)', async () => {
    renderForm();
    await screen.findByRole('textbox', { name: 'Your Ref' });
    expect(screen.queryByTestId('record-header-card')).toBeNull();
  });
});

/**
 * PROPOSAL-FORM-COLLAPSE (owner, 10 Nov): "I want to make the header and lines section to be
 * collapsible". Both open by default; a collapsed one shows a one-line summary and keeps its
 * fields mounted (hidden), so nothing typed is lost; Cover letter and Terms are untouched.
 */
describe('QuotationFormClient: collapsible Header and Lines (PROPOSAL-FORM-COLLAPSE)', () => {
  function toggle(name: RegExp) {
    return screen.getByRole('button', { name });
  }

  it('opens both sections by default, on New and on Edit', async () => {
    renderForm();
    await openLines();
    expect(toggle(/^Header/)).toHaveAttribute('aria-expanded', 'true');
    expect(toggle(/^Lines/)).toHaveAttribute('aria-expanded', 'true');
    cleanup();

    renderForm('d1');
    await openLines('Townhouse');
    expect(toggle(/^Header/)).toHaveAttribute('aria-expanded', 'true');
    expect(toggle(/^Lines/)).toHaveAttribute('aria-expanded', 'true');
  });

  it('a collapsed Header hides its fields and reads To, Subject, Date and Total on one line', async () => {
    renderForm('d1');
    await openLines('Townhouse');
    const name = screen.getByRole('textbox', { name: 'Name' });
    expect(name).toBeVisible();

    fireEvent.click(toggle(/^Header/));
    const collapsed = toggle(/^Header/);
    expect(collapsed).toHaveAttribute('aria-expanded', 'false');
    expect(collapsed).toHaveTextContent(
      /Nadi Cergas Sdn Bhd.*Menara Test.*28\/09\/2026.*RM [\d,]+\.\d\d/,
    );
    // Hidden, not unmounted: the typed value survives a collapse.
    expect(screen.getByDisplayValue('Nadi Cergas Sdn Bhd')).not.toBeVisible();
    // The lines stay open.
    expect(within(scopeCard('Townhouse')).getByRole('button', { name: 'Add a line' })).toBeVisible();

    fireEvent.click(collapsed);
    expect(toggle(/^Header/)).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeVisible();
  });

  it('a collapsed Lines section reads the scope count and total, and keeps staged lines', async () => {
    renderForm();
    const card = await openLines();
    await addLine(card, 1);
    // The description is typed in the cell's editor popover (QUOTE-DESC-RICHTEXT), then closed.
    const editor = await openDescription(card, 'line 1');
    fireEvent.change(editor, { target: { value: 'Kept while folded' } });
    fireEvent.keyDown(editor, { key: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByRole('textbox', { name: 'Description text on line 1' })).toBeNull(),
    );

    fireEvent.click(toggle(/^Lines/));
    const collapsed = toggle(/^Lines/);
    expect(collapsed).toHaveAttribute('aria-expanded', 'false');
    expect(collapsed).toHaveTextContent(/1 scope.*RM [\d,]+\.\d\d/);
    expect(screen.getByText('Kept while folded')).not.toBeVisible();
    // The Header stays open.
    expect(screen.getByRole('textbox', { name: 'Your Ref' })).toBeVisible();

    fireEvent.click(collapsed);
    expect(screen.getByText('Kept while folded')).toBeVisible();
  });

  it('leaves the Cover letter and Terms tabs without section toggles', async () => {
    renderForm();
    await openLines();
    expect(await formTabNames()).toEqual(['Header', 'Cover letter', 'Terms']);
    await openTab('Terms');
    const terms = screen.getByRole('tabpanel', { name: 'Terms' });
    expect(within(terms).queryByRole('button', { name: /^(Header|Lines)/ })).toBeNull();
  });
});

/**
 * PROPOSAL-FORM-COLLAPSE (review should-fix 4): a saved line that still carries a heading from
 * before heading rows is shown with that heading as its own row, but merely OPENING the scope is
 * not an edit: Save sends no lines for it, so nothing is rewritten until somebody changes it.
 */
describe('QuotationFormClient: a carried heading leaves an untouched scope clean', () => {
  it('opens the scope, shows the heading row, and saves without its lines', async () => {
    listQuotationLines.mockResolvedValue([{ ...LINE, band_label: 'BILL NO 1' }]);
    renderForm('d1');
    const card = await openLines('Townhouse');
    expect(
      await within(card).findByRole('textbox', { name: 'Section heading above SRT-WC-01' }),
    ).toHaveValue('BILL NO 1');

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    expect(updateQuotationDocument.mock.calls[0][2].scopes[0]).not.toHaveProperty('lines');
  });
});

/** QUOTE-TERMS-SELECT x QUOTE-AUTOSAVE: the payment term and validity picks ride in the draft, so a
 *  reopened draft (or a restored History entry) brings back exactly what was picked. */
describe('QuotationFormClient terms picks in the autosaved draft', () => {
  it('a pick is autosaved into the draft with what Save would send', async () => {
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'));
    await openTab('Terms');
    fireEvent.click(await screen.findByRole('button', { name: 'Pick CBD' }));
    await waitFor(() => expect(saveQuotationFormDraft).toHaveBeenCalled(), { timeout: 3000 });
    const state = saveQuotationFormDraft.mock.calls.at(-1)![2];
    expect(state.terms.picks.payment_term_id).toBe('pt-cbd');
    expect(state.terms.patch).toEqual({ payment_term_id: 'pt-cbd' });
    expect(state.header.payment_terms).toBe('CASH BEFORE DELIVERY');
  });

  it('a reopened draft restores the picks, and Save sends them', async () => {
    openQuotationFormDraft.mockResolvedValue({
      draft_id: 'draft-1',
      token: 'tok-1',
      doc: {
        v: 1,
        header: { your_ref: 'FROM-DRAFT', payment_terms: '30 DAYS', validity: '2 WEEKS' },
        letter: {},
        scopes: [{ key: 'q1', id: 'q1', scope_label: 'Townhouse', series_id: '' }],
        staged: {},
        removedIds: [],
        total: '0',
        terms: {
          picks: { payment_term_id: 'pt-30', validity_value: 2, validity_unit: 'week' },
          patch: { payment_term_id: 'pt-30', validity_value: 2, validity_unit: 'week' },
        },
      },
      updated_at: '2026-11-10T06:14:00',
      updated_by_name: 'Aina',
    });
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('FROM-DRAFT'));
    await openTab('Terms');
    expect(
      JSON.parse((await screen.findByLabelText('Terms values')).textContent ?? '{}'),
    ).toMatchObject({ payment_term_id: 'pt-30', validity_value: 2, validity_unit: 'week' });

    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    expect(updateQuotationDocument.mock.calls[0][2]).toMatchObject({
      payment_term_id: 'pt-30',
      validity_value: 2,
      validity_unit: 'week',
      payment_terms: '30 DAYS',
    });
  });

  it('a draft saved before the lane keeps the record picks and sends none', async () => {
    getQuotationDocument.mockResolvedValue(
      document({
        ...({ payment_term_id: 'pt-rec', payment_terms: 'Net 30 days' } as unknown as Partial<QuotationDocument>),
      }),
    );
    openQuotationFormDraft.mockResolvedValue({
      draft_id: 'draft-1',
      token: 'tok-1',
      doc: {
        v: 1,
        header: { your_ref: 'OLD-DRAFT', payment_terms: 'Net 30 days' },
        letter: {},
        scopes: [{ key: 'q1', id: 'q1', scope_label: 'Townhouse', series_id: '' }],
        staged: {},
        removedIds: [],
        total: '0',
      },
      updated_at: '2026-11-10T06:14:00',
      updated_by_name: 'Aina',
    });
    renderForm('d1');
    await waitFor(() => expect(screen.getByLabelText('Your Ref')).toHaveValue('OLD-DRAFT'));
    await openTab('Terms');
    expect(
      JSON.parse((await screen.findByLabelText('Terms values')).textContent ?? '{}'),
    ).toMatchObject({ payment_term_id: 'pt-rec' });
    fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
    await waitFor(() => expect(updateQuotationDocument).toHaveBeenCalledTimes(1));
    expect(updateQuotationDocument.mock.calls[0][2]).not.toHaveProperty('payment_term_id');
  });
});
