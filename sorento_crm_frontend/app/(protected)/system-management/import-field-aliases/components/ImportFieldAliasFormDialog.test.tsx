/**
 * Add mapping dialog - Supplier select (S4, `PLAN-stock-list-bare-model-codes.md` D6,
 * AC-F1). A clearable `Supplier` select appears ONLY for the `supplier_inventory_word` doc
 * type; picking one carries `supplier_id` on the create call. Every other doc type is
 * unchanged - no Supplier field at all.
 *
 * TEST-FIRST (Phase 2): the dialog has no Supplier select yet, so every test in the first
 * two `describe` blocks is expected to be RED until S4 lands.
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

// The codebase's established supplier-select hook (reused, per grep, by
// ProductSuppliersSection/AddCompanionRuleModal/PackingListForm and others) - the
// "existing supplier select service" this lane's brief points at.
vi.mock('../../../procurement-management/suppliers/hooks/useSupplierSelectQuery', () => ({
  useSupplierSelectQuery: () => ({
    data: [{ id: 'sup-1', supplier_code: 'DFY', supplier_name: 'DAFUYUAN' }],
  }),
}));

import { ImportFieldAliasFormDialog } from './ImportFieldAliasFormDialog';

beforeEach(() => {
  createMutateAsync.mockReset().mockResolvedValue({ field: 'SRT', label: 'SRT', aliases: [] });
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
  it('carries supplier_id on the create call when a supplier is chosen', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );

    fireEvent.click(screen.getByLabelText('System field'));
    fireEvent.click(await screen.findByRole('option', { name: 'SRT' }));
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

  it('omits supplier_id (shared row) when no supplier is chosen', async () => {
    render(
      <ImportFieldAliasFormDialog
        open
        onOpenChange={() => {}}
        docType={'supplier_inventory_word' as never}
      />,
    );

    fireEvent.click(screen.getByLabelText('System field'));
    fireEvent.click(await screen.findByRole('option', { name: 'SRT' }));
    fireEvent.change(screen.getByLabelText('Header'), { target: { value: 'SORENTO' } });

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const call = createMutateAsync.mock.calls[0][0];
    expect(call.supplier_id ?? null).toBeNull();
  });
});
