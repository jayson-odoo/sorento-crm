/**
 * Import column mappings (S5, AC-E3) - per document type, every system field and the
 * headers on file that resolve to it, plus the Add mapping dialog.
 *
 * The service layer is mocked; the real hooks (`useImportFieldAliases`,
 * `useCreateImportFieldAlias`) and the real `DataGrid` run.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn().mockResolvedValue({
    id: 'pa-1',
    action_key: 'import_field_alias.forget',
    entity_type: 'import_field_alias',
    entity_id: 'alias-1',
    commit_at: '2026-09-10T10:00:05',
    window_seconds: 5,
  }),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

// AC-F5: the page opens on `?doc_type=` when present. `nav.search` is mutated per-test
// rather than re-mocking the module, since `vi.mock` factories are hoisted above any
// per-test local.
const nav = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/import-field-aliases',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const listImportFieldAliases = vi.fn();
const listImportFieldAliasFields = vi.fn();
const createImportFieldAlias = vi.fn();
const deleteImportFieldAlias = vi.fn();

vi.mock('../services/importFieldAliasService', () => ({
  listImportFieldAliases: (...a: unknown[]) => listImportFieldAliases(...a),
  listImportFieldAliasFields: (...a: unknown[]) => listImportFieldAliasFields(...a),
  createImportFieldAlias: (...a: unknown[]) => createImportFieldAlias(...a),
  deleteImportFieldAlias: (...a: unknown[]) => deleteImportFieldAlias(...a),
}));

import ImportFieldAliasesList from './ImportFieldAliasesList';

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ImportFieldAliasesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listImportFieldAliases.mockReset().mockResolvedValue([
    {
      field: 'item_code',
      label: 'Item code',
      aliases: [
        { id: 'alias-1', alias: '货号', locale: 'zh', created_at: '2026-09-01T00:00:00' },
      ],
    },
    { field: 'cartons', label: 'Cartons', aliases: [] },
  ]);
  listImportFieldAliasFields.mockReset().mockResolvedValue([
    { field: 'item_code', label: 'Item code' },
    { field: 'cartons', label: 'Cartons' },
  ]);
  createImportFieldAlias.mockReset().mockResolvedValue({
    field: 'cartons',
    label: 'Cartons',
    aliases: [{ id: 'alias-2', alias: '箱数', locale: null, created_at: '2026-09-10T00:00:00' }],
  });
  deleteImportFieldAlias.mockReset();
});

describe('ImportFieldAliasesList - the grid (AC-E1/E3)', () => {
  it('lists every system field, each carrying the headers on file that resolve to it', async () => {
    renderList();

    expect(await screen.findByText('Item code')).toBeInTheDocument();
    expect(screen.getByText('货号')).toBeInTheDocument();
    // A field with no alias yet still gets a row (AC-E1) - "even a field with no alias".
    expect(screen.getByText('Cartons')).toBeInTheDocument();
    expect(screen.getByText('No header maps here yet.')).toBeInTheDocument();
  });

  it('asks the service for the doc type the page filter is showing', async () => {
    renderList();
    await waitFor(() => expect(listImportFieldAliases).toHaveBeenCalledWith('proforma_invoice'));
  });
});

describe('ImportFieldAliasesList - Add mapping (AC-E3)', () => {
  it('posts {doc_type, field, alias} on submit, locked to the pages own doc-type filter', async () => {
    renderList();
    await screen.findByText('Item code');

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));
    await screen.findByLabelText('System field');

    // Field: SearchableSelect over E1's own field list (never hand-typed).
    fireEvent.click(screen.getByLabelText('System field'));
    fireEvent.click(await screen.findByRole('option', { name: 'Cartons' }));

    fireEvent.change(screen.getByLabelText('Header'), { target: { value: '箱数' } });

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));

    await waitFor(() =>
      expect(createImportFieldAlias).toHaveBeenCalledWith({
        doc_type: 'proforma_invoice',
        field: 'cartons',
        alias: '箱数',
        locale: null,
      }),
    );
  });

  it('leaves Add mapping disabled until both a field and a header are given', async () => {
    renderList();
    await screen.findByText('Item code');

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));
    await screen.findByLabelText('System field');

    // The toolbar's OWN "Add mapping" button is now `aria-hidden` (Radix Dialog hides
    // its siblings while modal) - this is the dialog's own submit button.
    const submit = screen.getByRole('button', { name: /add mapping/i });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Header'), { target: { value: '箱数' } });
    expect(submit).toBeDisabled(); // no field chosen yet
  });
});

// S4 (`PLAN-stock-list-bare-model-codes.md`).
describe('ImportFieldAliasesList - Stock list words doc type (AC-F1)', () => {
  it('offers "Stock list words" in the document type select', async () => {
    renderList();
    await screen.findByText('Item code');

    fireEvent.click(screen.getByLabelText('Document type'));

    expect(await screen.findByRole('option', { name: 'Stock list words' })).toBeInTheDocument();
  });

  it('shows the supplier name beside a supplier-scoped word, and blank for a shared one', async () => {
    listImportFieldAliases.mockReset().mockImplementation((docType: string) => {
      if (docType === 'supplier_inventory_word') {
        return Promise.resolve([
          {
            field: 'SH',
            label: 'SH',
            aliases: [
              {
                id: 'w-1',
                alias: '对冲',
                locale: null,
                created_at: '2026-09-17T00:00:00',
                supplier_id: 'sup-1',
                supplier_name: 'DAFUYUAN',
              },
              {
                id: 'w-2',
                alias: 'SORENTO',
                locale: null,
                created_at: '2026-09-17T00:00:00',
                supplier_id: null,
                supplier_name: null,
              },
            ],
          },
        ]);
      }
      return Promise.resolve([]);
    });
    renderList();
    await screen.findByLabelText('Document type');

    fireEvent.click(screen.getByLabelText('Document type'));
    fireEvent.click(await screen.findByRole('option', { name: 'Stock list words' }));

    await screen.findByText('对冲');
    // The supplier-scoped row carries the supplier's NAME (never a UUID) somewhere on
    // screen; the shared row carries none.
    expect(screen.getByText('DAFUYUAN')).toBeInTheDocument();
    expect(screen.queryByText('sup-1')).not.toBeInTheDocument();
  });
});

describe('ImportFieldAliasesList - initial doc type from the URL (AC-F5)', () => {
  afterEach(() => {
    nav.search = '';
  });

  it('opens on the ?doc_type= query param when present', async () => {
    nav.search = 'doc_type=supplier_inventory_word';
    renderList();

    await waitFor(() =>
      expect(listImportFieldAliases).toHaveBeenCalledWith('supplier_inventory_word'),
    );
  });

  it('opens on the default doc type when the query param is absent', async () => {
    renderList();

    await waitFor(() => expect(listImportFieldAliases).toHaveBeenCalledWith('proforma_invoice'));
  });
});
