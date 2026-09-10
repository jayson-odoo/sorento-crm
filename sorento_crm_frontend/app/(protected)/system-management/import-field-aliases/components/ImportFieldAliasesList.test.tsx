/**
 * Import column mappings (S5, AC-E3) - per document type, every system field and the
 * headers on file that resolve to it, plus the Add mapping dialog.
 *
 * The service layer is mocked; the real hooks (`useImportFieldAliases`,
 * `useCreateImportFieldAlias`) and the real `DataGrid` run.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
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

vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/import-field-aliases',
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
