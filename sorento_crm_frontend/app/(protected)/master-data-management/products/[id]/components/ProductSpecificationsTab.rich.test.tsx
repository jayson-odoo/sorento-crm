/**
 * PRICETAG-COMBO-FORMAT AC-22: the product's price tag description is edited in the rich editor,
 * and "Insert field" puts the merge field at the cursor through `onEditorReady`.
 *
 * Written test-FIRST. Today the block is a plain Textarea labelled "Price tag description".
 * Mocks follow `ProductSpecificationsTab.priceTagDescription.test.tsx`. `RichTextEditor` is a
 * stand-in that hands the tab a recording editor through `onEditorReady`: any chain the tab runs
 * (`chain().focus().insertContent(...).run()` or `commands.insertContent(...)`) is recorded, and
 * the test asserts that the merge field text reached it.
 */
import type { ReactNode } from 'react';
import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ProductSpecificationsTab from './ProductSpecificationsTab';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));
vi.mock('@/components/spec-table', () => ({
  SpecTable: () => <div data-testid="spec-table-stub" />,
  AddSpecificationDialog: () => null,
}));
vi.mock('./SpecExtractPanel', () => ({ default: () => null }));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({ usePermissions: () => usePermissions() }));

const useProductSpecTable = vi.fn();
vi.mock('../../hooks/useProductSpecTable', () => ({
  DETAIL_KEY: (id: string) => ['product-spec-detail', id],
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));

const updateMutateAsync = vi.fn().mockResolvedValue({});
const useProduct = vi.fn();
vi.mock('../../hooks/useProducts', () => ({
  useProduct: (...a: unknown[]) => useProduct(...a),
  useUpdateProduct: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
}));

const recorded = vi.hoisted(() => ({ calls: [] as Array<{ method: string; args: unknown[] }> }));

function recordingEditor() {
  const make = (): unknown =>
    new Proxy(() => undefined, {
      get: (_t, method: string) => {
        if (method === 'run') return () => true;
        return (...args: unknown[]) => {
          recorded.calls.push({ method, args });
          return make();
        };
      },
    });
  return new Proxy(
    { getHTML: () => '<p>Stored</p>', isEditable: true },
    {
      get: (target, key: string) =>
        key in target ? (target as never)[key] : key === 'chain' ? make : key === 'commands' ? make() : vi.fn(),
    },
  );
}

vi.mock('@/components/ui/rich-text-editor', () => {
  const Stand = (props: {
    value?: string;
    onChange: (v: string) => void;
    onEditorReady?: (editor: unknown) => void;
  }) => {
    React.useEffect(() => {
      props.onEditorReady?.(recordingEditor());
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return <textarea data-testid="rte" value={props.value ?? ''} onChange={(e) => props.onChange(e.target.value)} />;
  };
  return { RichTextEditor: Stand, default: Stand };
});

const MATERIAL_ROW = {
  specKey: 'material',
  label: 'Material',
  value: 'stainless_steel',
  unit: null,
  dataType: 'enum',
  options: [],
  source: 'human',
  evidence: null,
  unknownKey: false,
  valueLabels: { stainless_steel: 'Stainless Steel' },
};

function mockSpecHook() {
  useProductSpecTable.mockReturnValue({
    detail: {
      product_id: 'p-1',
      product_code: 'WC100',
      category_code: 'BR-KS',
      searchable: true,
      diagnosis: { reason: 'eligible', class_label: 'Kitchen Sink', brand_hint: 'Sorento', suffix: null },
      spec: { values: {}, provenance: {}, rendered_text: '', status: 'authored', derived_at: null },
      exceptions: [],
      source_text: '',
      verification: { state: 'unverified' },
      values_hash: 'h',
    },
    rows: [MATERIAL_ROW],
    registry: [
      {
        spec_key: 'material',
        label: 'Material',
        data_type: 'enum',
        unit: null,
        allowed_values: [],
        synonyms: {},
        value_labels: { stainless_steel: 'Stainless Steel' },
      },
    ],
    applicableKeys: [],
    otherKeys: [],
    heldKeys: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    verify: vi.fn(),
    verificationBusy: false,
    setValue: vi.fn(),
    tombstone: vi.fn(),
    revert: vi.fn(),
    addValue: vi.fn(),
    createKey: vi.fn(),
    checkSimilarKey: vi.fn(),
  });
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductSpecificationsTab productId="p-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  recorded.calls = [];
  usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.edit']) });
  useProduct.mockReturnValue({
    data: {
      id: 'p-1',
      product_code: 'WC100',
      product_name: 'Basin Tap',
      list_price: 250,
      price_tag_description: '<p>Stored</p>',
    },
    isLoading: false,
  });
  mockSpecHook();
});
afterEach(() => cleanup());

describe('Price tag description in the rich editor (AC-22)', () => {
  it('AC-22: Edit opens the rich editor with the stored HTML (no plain textarea label)', () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: /edit price tag description/i }));

    expect((screen.getByTestId('rte') as HTMLTextAreaElement).value).toBe('<p>Stored</p>');
  });

  it('AC-22: Insert field inserts the merge field at the cursor through onEditorReady', () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: /edit price tag description/i }));
    fireEvent.click(screen.getByRole('button', { name: /insert field/i }));

    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByText('Material'));
    fireEvent.click(dialog.getByRole('button', { name: /^done$/i }));

    const inserted = recorded.calls.some((call) =>
      call.args.some((arg) => typeof arg === 'string' && arg.includes('{{spec.material}}')),
    );
    expect(inserted).toBe(true);
  });

  it('AC-22: Save sends the editor HTML', async () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: /edit price tag description/i }));
    fireEvent.change(screen.getByTestId('rte'), { target: { value: '<p><strong>{{spec.material}}</strong></p>' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await vi.waitFor(() =>
      expect(updateMutateAsync).toHaveBeenCalledWith({
        id: 'p-1',
        data: { price_tag_description: '<p><strong>{{spec.material}}</strong></p>' },
      }),
    );
  });
});
