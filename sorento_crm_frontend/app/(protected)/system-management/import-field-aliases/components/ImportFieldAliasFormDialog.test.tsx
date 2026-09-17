/**
 * Add mapping dialog - Supplier select (S4, `PLAN-stock-list-bare-model-codes.md` D6,
 * AC-F1). A clearable `Supplier` select appears ONLY for the `supplier_inventory_word` doc
 * type; picking one carries `supplier_id` on the create call. Every other doc type is
 * unchanged - no Supplier field at all.
 *
 * TEST-FIRST (Phase 2): the dialog has no Supplier select yet, so every test in the first
 * two `describe` blocks is expected to be RED until S4 lands.
 *
 * Fix round 1 (review round 1): two production-shape changes moved the mock/assertions
 * below, noted at each site -
 *   - item 5 (review blocker): the Supplier select now reads through the server-searched,
 *     paged `getFulfilmentSuppliers` (via a small `enabled`-gated hook in the dialog itself)
 *     instead of the bare, 100-row-capped `/select` endpoint - the mock changed to that
 *     service function.
 *   - item 4 (review blocker): `WORD_TOKENS` is no longer a closed list; the word doc
 *     type's "System field" is a plain uppercase text input, not a `SearchableSelect` - the
 *     two submit tests in the second `describe` block now type into it instead of picking
 *     an option.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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

const fieldsData = [
  { field: 'SRT', label: 'SRT' },
  { field: 'C', label: 'C' },
];
const createMutateAsync = vi.fn();

vi.mock('../hooks/useImportFieldAliases', () => ({
  useImportFieldAliasFields: () => ({ data: fieldsData, isLoading: false }),
  useCreateImportFieldAlias: () => ({ mutateAsync: createMutateAsync, isPending: false }),
}));

// Fix round 1, item 5: the server-searched, paged supplier lookup - `SearchableSelect`'s own
// `fetchOptions(query, pageIndex)` contract, so the mock returns option shape directly
// rather than raw supplier rows.
const getFulfilmentSuppliersMock = vi.fn().mockResolvedValue([{ value: 'sup-1', label: 'DAFUYUAN' }]);
vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  getFulfilmentSuppliers: (...args: unknown[]) => getFulfilmentSuppliersMock(...args),
}));

import { ImportFieldAliasFormDialog } from './ImportFieldAliasFormDialog';

beforeEach(() => {
  createMutateAsync.mockReset().mockResolvedValue({ field: 'SRT', label: 'SRT', aliases: [] });
  getFulfilmentSuppliersMock.mockReset().mockResolvedValue([{ value: 'sup-1', label: 'DAFUYUAN' }]);
});

describe('ImportFieldAliasFormDialog - Supplier select (AC-F1)', () => {
  it('shows a Supplier select when the doc type is supplier_inventory_word', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );

    expect(await screen.findByLabelText('Supplier')).toBeInTheDocument();
  });

  it('is clearable', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );
    const supplierField = await screen.findByLabelText('Supplier');

    fireEvent.click(supplierField);
    fireEvent.click(await screen.findByRole('option', { name: 'DAFUYUAN' }));

    expect(screen.getByRole('button', { name: /clear selection/i })).toBeInTheDocument();
  });

  it('hides the Supplier select for every other doc type', () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'proforma_invoice' as never}
      />,
    );

    expect(screen.queryByLabelText('Supplier')).not.toBeInTheDocument();
  });
});

describe('ImportFieldAliasFormDialog - submitting a supplier-scoped word (AC-F1)', () => {
  // Rewritten (item 4, review round 1): the word doc type's "System field" is now a plain
  // uppercase text input (open vocabulary), not a `SearchableSelect` over a closed list -
  // was `fireEvent.click` + pick an option, now `fireEvent.change` + type.
  it('carries supplier_id on the create call when a supplier is chosen', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );

    fireEvent.change(screen.getByLabelText('System field'), { target: { value: 'srt' } });
    fireEvent.change(screen.getByLabelText('Header'), { target: { value: 'SORENTO' } });

    const supplierField = await screen.findByLabelText('Supplier');
    fireEvent.click(supplierField);
    fireEvent.click(await screen.findByRole('option', { name: 'DAFUYUAN' }));

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));

    await waitFor(() =>
      expect(createMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ field: 'SRT', alias: 'SORENTO', supplier_id: 'sup-1' }),
      ),
    );
  });

  it('uppercases the typed field on the create call', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );

    const fieldInput = screen.getByLabelText('System field') as HTMLInputElement;
    fireEvent.change(fieldInput, { target: { value: 'srt' } });
    expect(fieldInput.value).toBe('SRT');
    fireEvent.change(screen.getByLabelText('Header'), { target: { value: 'SORENTO' } });

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));

    await waitFor(() =>
      expect(createMutateAsync).toHaveBeenCalledWith(expect.objectContaining({ field: 'SRT' })),
    );
  });

  it('omits supplier_id (shared row) when no supplier is chosen', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );

    fireEvent.change(screen.getByLabelText('System field'), { target: { value: 'srt' } });
    fireEvent.change(screen.getByLabelText('Header'), { target: { value: 'SORENTO' } });

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const call = createMutateAsync.mock.calls[0][0];
    expect(call.supplier_id ?? null).toBeNull();
  });
});
