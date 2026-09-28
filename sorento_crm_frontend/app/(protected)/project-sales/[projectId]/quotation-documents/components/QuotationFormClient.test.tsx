/**
 * #1341 - the quotation form page, create and edit (AC-QF010 to AC-QF024, AC-QF040/041).
 *
 * The owner: "I should be able to add product straight away and save when I am satisfied, if I
 * want to edit I can click on the gear button to edit". So create is a page that writes nothing
 * until Save, and Save is ONE request; edit is the same page, filled, and its Save is ONE PATCH.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
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
    };
  },
);

const getProject = vi.fn();
const listQuotations = vi.fn();
const listQuotationVersions = vi.fn();
const listQuotationLines = vi.fn();
const listSeries = vi.fn();
const replaceQuotationLines = vi.fn();
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

import { QuotationFormClient } from './QuotationFormClient';

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

function scopeSection(index: number) {
  return screen.getAllByRole('region', { name: /^Scope \d+$/ })[index];
}

beforeEach(() => {
  vi.clearAllMocks();
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
});

describe('QuotationFormClient create', () => {
  it('AC-QF011/012: opens with the letterhead and one empty scope ready for products', async () => {
    renderForm();

    expect(await screen.findByLabelText('Your Ref')).toBeInTheDocument();
    expect(screen.getByLabelText('Attn')).toBeInTheDocument();
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    expect(screen.getByLabelText('Date')).toHaveValue(today);
    // The subject arrives as the project's title, the same default the server would use.
    await waitFor(() =>
      expect(screen.getByLabelText('Subject')).toHaveValue('Menara Test'),
    );
    const scope = scopeSection(0);
    expect(within(scope).getByLabelText('Scope name')).toHaveValue('');
    expect(
      within(scope).getByRole('combobox', { name: 'Series' }),
    ).toBeInTheDocument();
    expect(
      within(scope).getByRole('button', { name: /Add a line/i }),
    ).toBeInTheDocument();
  });

  it('AC-QF010: writes nothing while the form is being filled', async () => {
    renderForm();
    const scope = await waitFor(() => scopeSection(0));

    fireEvent.change(within(scope).getByLabelText('Scope name'), {
      target: { value: 'Townhouse' },
    });
    fireEvent.click(within(scope).getByRole('button', { name: /Add a line/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add a scope/i }));

    expect(createQuotationDocument).not.toHaveBeenCalled();
    expect(updateQuotationDocument).not.toHaveBeenCalled();
    expect(replaceQuotationLines).not.toHaveBeenCalled();
  });

  it('AC-QF014: Save sends ONE request with the header, every scope and every line', async () => {
    renderForm();
    const first = await waitFor(() => scopeSection(0));

    fireEvent.change(screen.getByLabelText('Your Ref'), {
      target: { value: 'NC/19' },
    });
    fireEvent.change(within(first).getByLabelText('Scope name'), {
      target: { value: 'Townhouse' },
    });
    fireEvent.click(within(first).getByRole('button', { name: /Add a line/i }));
    const editor = await within(first).findByRole('group', { name: 'Line 1' });
    fireEvent.change(within(editor).getByLabelText('Description'), {
      target: { value: 'Bespoke vanity top' },
    });
    fireEvent.change(within(editor).getByLabelText('Unit price'), {
      target: { value: '120.00' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Add a scope/i }));
    const second = scopeSection(1);
    fireEvent.change(within(second).getByLabelText('Scope name'), {
      target: { value: 'Guard House' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save quotation' }));

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
              description_snapshot: 'Bespoke vanity top',
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
    const scope = await waitFor(() => scopeSection(0));
    fireEvent.click(within(scope).getByRole('button', { name: /Add a line/i }));
    await within(scope).findByRole('group', { name: 'Line 1' });

    fireEvent.click(screen.getByRole('button', { name: 'Save quotation' }));

    expect(
      await screen.findByText(/Every scope needs a name/i),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();

    fireEvent.change(within(scope).getByLabelText('Scope name'), {
      target: { value: 'Townhouse' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save quotation' }));

    expect(
      await screen.findByText(
        /One line still needs a product or a description/i,
      ),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });

  it('AC-QF013: a scope added on the form can be removed before Save', async () => {
    renderForm();
    await waitFor(() => scopeSection(0));

    fireEvent.click(screen.getByRole('button', { name: /Add a scope/i }));
    expect(screen.getAllByRole('region', { name: /^Scope \d+$/ })).toHaveLength(
      2,
    );

    fireEvent.click(
      within(scopeSection(1)).getByRole('button', { name: 'Remove scope' }),
    );
    expect(screen.getAllByRole('region', { name: /^Scope \d+$/ })).toHaveLength(
      1,
    );
  });

  it('AC-QF016: Cancel goes back to the Quotations tab and writes nothing', async () => {
    renderForm();
    await waitFor(() => scopeSection(0));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(push).toHaveBeenCalledWith('/project-sales/p1?tab=quotations');
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });

  it('AC-QF040: one primary CTA and no subtitle under the title', async () => {
    renderForm();
    await waitFor(() => scopeSection(0));

    expect(
      screen.getByRole('heading', { level: 1, name: 'New quotation' }),
    ).toBeInTheDocument();
    // Cancel is an outline button; Save is the only filled one.
    const save = screen.getByRole('button', { name: 'Save quotation' });
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    expect(save.className).toMatch(/bg-primary/);
    expect(cancel.className).not.toMatch(/bg-primary/);
    expect(
      screen
        .getAllByRole('button')
        .filter((b) => /bg-primary /.test(b.className)),
    ).toHaveLength(1);
  });
});

describe('QuotationFormClient edit', () => {
  it('AC-QF020: opens filled from the saved quotation, with the same sections plus the letter', async () => {
    renderForm('d1');

    await waitFor(() =>
      expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'),
    );
    expect(screen.getByLabelText('Attn')).toHaveValue('Kelly');
    const scope = scopeSection(0);
    expect(within(scope).getByLabelText('Scope name')).toHaveValue('Townhouse');
    expect(await within(scope).findByText('Wall-hung WC')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'PRJQ-2026-0002' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Cover letter')).toBeInTheDocument();
    expect(screen.getByText('Terms and conditions')).toBeInTheDocument();
  });

  it('AC-QF021: Save sends ONE PATCH with the header and every scope, lines included', async () => {
    renderForm('d1');
    const scope = await waitFor(() => scopeSection(0));
    await within(scope).findByText('Wall-hung WC');

    fireEvent.change(screen.getByLabelText('Your Ref'), {
      target: { value: 'NC/20' },
    });
    fireEvent.change(within(scope).getByLabelText('Scope name'), {
      target: { value: 'Townhouse Block A' },
    });
    fireEvent.click(within(scope).getByRole('button', { name: 'Edit line 1' }));
    const editor = await within(scope).findByRole('group', { name: 'Line 1' });
    fireEvent.change(within(editor).getByLabelText('Qty'), {
      target: { value: '12' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Add a scope/i }));
    fireEvent.change(within(scopeSection(1)).getByLabelText('Scope name'), {
      target: { value: 'Reception' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save quotation' }));

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

  it('AC-QF022: Cancel goes back to the quotation page and writes nothing', async () => {
    renderForm('d1');
    await waitFor(() =>
      expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'),
    );

    fireEvent.change(screen.getByLabelText('Your Ref'), {
      target: { value: 'changed' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(push).toHaveBeenCalledWith(
      '/project-sales/p1/quotation-documents/d1',
    );
    expect(updateQuotationDocument).not.toHaveBeenCalled();
  });

  it('AC-QF023: a scope the customer holds shows its lines read-only and never sends them', async () => {
    listQuotationVersions.mockResolvedValue([version({ is_editable: false })]);
    renderForm('d1');
    const scope = await waitFor(() => scopeSection(0));
    await within(scope).findByText('Wall-hung WC');

    expect(
      within(scope).queryByRole('button', { name: /Add a line/i }),
    ).toBeNull();
    expect(
      within(scope).queryByRole('button', { name: 'Edit line 1' }),
    ).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save quotation' }));
    await waitFor(() =>
      expect(updateQuotationDocument).toHaveBeenCalledTimes(1),
    );
    const body = updateQuotationDocument.mock.calls[0][2];
    expect(body.scopes[0]).not.toHaveProperty('lines');
  });

  it('AC-QF024: a saved scope offers no Remove', async () => {
    renderForm('d1');
    const scope = await waitFor(() => scopeSection(0));
    await within(scope).findByText('Wall-hung WC');

    expect(
      within(scope).queryByRole('button', { name: 'Remove scope' }),
    ).toBeNull();
  });

  it('keeps Save off until a saved scope has its lines, so it never sends a guessed set', async () => {
    let answer: (lines: QuotationLine[]) => void = () => {};
    listQuotationLines.mockReturnValue(
      new Promise<QuotationLine[]>((resolve) => {
        answer = resolve;
      }),
    );
    renderForm('d1');
    await waitFor(() =>
      expect(screen.getByLabelText('Your Ref')).toHaveValue('NC/18'),
    );

    expect(
      screen.getByRole('button', { name: 'Save quotation' }),
    ).toBeDisabled();

    answer([LINE]);
    await within(scopeSection(0)).findByText('Wall-hung WC');
    expect(
      screen.getByRole('button', { name: 'Save quotation' }),
    ).toBeEnabled();
  });
});

describe('QuotationFormClient guards', () => {
  it('refuses a quantity that is not a number before any request', async () => {
    renderForm();
    const scope = await waitFor(() => scopeSection(0));
    fireEvent.change(within(scope).getByLabelText('Scope name'), {
      target: { value: 'Townhouse' },
    });
    fireEvent.click(within(scope).getByRole('button', { name: /Add a line/i }));
    const editor = await within(scope).findByRole('group', { name: 'Line 1' });
    fireEvent.change(within(editor).getByLabelText('Description'), {
      target: { value: 'Grab bar' },
    });
    fireEvent.change(within(editor).getByLabelText('Qty'), {
      target: { value: 'two' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save quotation' }));

    expect(
      await screen.findByText(
        /One line has a quantity or unit price that is not a number/i,
      ),
    ).toBeInTheDocument();
    expect(createQuotationDocument).not.toHaveBeenCalled();
  });

  it('warns before the browser throws typed work away, and not before anything is typed', async () => {
    renderForm();
    await waitFor(() => scopeSection(0));

    const untouched = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(untouched);
    expect(untouched.defaultPrevented).toBe(false);

    fireEvent.change(screen.getByLabelText('Your Ref'), {
      target: { value: 'NC/21' },
    });
    const touched = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(touched);
    expect(touched.defaultPrevented).toBe(true);
  });
});
