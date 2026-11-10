/**
 * COMBO-SETTINGS-UX review B2: with the REAL editor, a field inserted from Insert field is saved as
 * its plain `{{token}}`, never as the chip's readable name (the editor draws chips by name).
 * Also S8: "All parts" keeps anything else composed in the dialog with it; and S7: a chip's name
 * follows a renamed or removed part without a reload.
 */
import '@/test-utils/prosemirrorGeometry';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { ProductComboPartRow, ProductComboRow } from '../../types/productCombo.types';

const permission = vi.hoisted(() => ({ canEdit: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => permission.canEdit,
}));

// PRICETAG-COMBO-FORMAT AC-21: the description is the shared RichTextEditor (its own suite covers
// tiptap) and the live tag preview has its own suite; both are stood in for here so these tests
// keep pinning what they always did.
const previewProps = vi.hoisted(() => ({ last: null as null | Record<string, unknown> }));
vi.mock('./ComboTagPreview', () => ({
  ComboTagPreview: (props: Record<string, unknown>) => {
    previewProps.last = props;
    return null;
  },
}));
const insertDialog = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/InsertFieldDialog', () => ({
  InsertFieldDialog: (props: { open: boolean } & Record<string, unknown>) => {
    if (props.open) insertDialog.props = props;
    return props.open ? <div role="dialog" aria-label="Insert field" /> : null;
  },
}));
vi.mock('@/hooks/useSpecKeys', () => ({ useSpecKeys: () => ({ data: [] }) }));

vi.mock('./ComboTemplatesField', () => ({ ComboTemplatesField: () => null }));
// The accessory list has its own suite; here it stands in as a labelled marker.
vi.mock('./AccessoryListField', () => ({
  AccessoryListField: (props: { label?: string; ownerId: string; canEdit: boolean }) => (
    <div data-testid="accessory-list" data-owner={props.ownerId} data-can-edit={String(props.canEdit)}>
      {props.label}
    </div>
  ),
}));

vi.mock('./AddComboModal', () => ({
  AddComboModal: () => null,
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

const combosQuery = vi.hoisted(() => ({
  value: { data: undefined, isLoading: false, isError: false } as {
    data: ProductComboRow[] | undefined;
    isLoading: boolean;
    isError: boolean;
  },
}));
const updateComboMutate = vi.hoisted(() => vi.fn());
const updatePartMutate = vi.hoisted(() => vi.fn());

vi.mock('../../hooks/useProductCombos', () => ({
  useProductCombos: () => combosQuery.value,
  useProductComboDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useProductComboPartDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useAddProductComboPart: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProductComboPart: () => ({ mutate: updatePartMutate }),
  useUpdateProductCombo: () => ({ mutate: updateComboMutate, isPending: false }),
}));

vi.mock('../../hooks/useProductComboImage', () => ({
  useProductComboImage: () => ({
    uploadMutateAsync: vi.fn(),
    deleteMutateAsync: vi.fn(),
    isUploading: false,
    isDeleting: false,
  }),
}));

import { ProductCombosSection } from './ProductCombosSection';
import { partRef } from '@/lib/dealer-kit/combo-part-fields';

const part = (over: Partial<ProductComboPartRow> & Pick<ProductComboPartRow, 'id' | 'code'>): ProductComboPartRow =>
  ({
    combo_id: 'combo-b', product_id: `p-${over.id}`, product_name: over.code, dimensions: null,
    choice_group: null, sort_order: 0, ...over,
  }) as ProductComboPartRow;
const BASIN = part({ id: 'basin', code: 'SRTWB2380', label: 'BASIN' } as never);
const COMBO = {
  id: 'combo-b', host_product_id: 'prod-host', name: 'BF', sort_order: 0,
  description: '<p>Intro</p>', main_label: 'CABINET', parts_line: null, parts: [BASIN],
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
} as unknown as ProductComboRow;

function show(combo: ProductComboRow = COMBO) {
  combosQuery.value = { data: [combo], isLoading: false, isError: false };
  return render(<ProductCombosSection productId="prod-host" productCode="SRTBF11829" />);
}

async function insert(content: string) {
  await waitFor(() => expect(document.querySelector('.ProseMirror')).not.toBeNull());
  fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
  act(() => {
    (insertDialog.props?.onDone as (c: string) => void)(content);
  });
  return (updateComboMutate.mock.calls.at(-1)?.[0] as { write: { description: string } }).write.description;
}

beforeEach(() => {
  permission.canEdit = true;
  updateComboMutate.mockReset();
  insertDialog.props = null;
});

describe('real editor: inserted fields save as plain tokens', () => {
  it('the description chips and the Insert field box never show a part id (owner 22:33)', async () => {
    const withToken = { ...COMBO, description: `<p>{{${partRef('p-basin')}.label}}</p>` } as ProductComboRow;
    const { container } = show(withToken);
    await waitFor(() => expect(container.querySelector('[data-merge-field]')?.textContent).toBe('BASIN - SRTWB2380: label'));
    expect(container.textContent ?? '').not.toContain(partRef('p-basin'));
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    const tokenLabel = insertDialog.props?.tokenLabel as (path: string) => string | null;
    expect(tokenLabel(`${partRef('p-basin')}.label`)).toBe('BASIN - SRTWB2380: label');
  });

  it('saves {{part.main.code}}, not the chip name the editor shows', async () => {
    const { container } = show();
    const saved = await insert('{{part.main.code}}');
    expect(saved).toContain('{{part.main.code}}');
    expect(saved).not.toContain('CABINET - SRTBF11829');
    expect(saved).not.toContain('data-merge-field');
    // The editor itself shows the chip by the part's name.
    await waitFor(() =>
      expect([...container.querySelectorAll('[data-merge-field]')].map((el) => el.textContent)).toContain(
        'CABINET - SRTBF11829: code',
      ),
    );
  });

  it('"All parts" keeps the other text composed with it (review S8)', async () => {
    show();
    const saved = await insert('Tap: {{part.main.code}} {{combo.all_parts}}');
    expect(saved).toContain('Tap: {{part.main.code}}');
    expect(saved).toContain('{{part.main.code}} ({{part.main.label}})');
    expect(saved).toContain(`{{${partRef('p-basin')}.code}} ({{${partRef('p-basin')}.label}})`);
    expect(saved).not.toContain('combo.all_parts');
  });

  it('a chip name follows a removed part without a reload (review S7)', async () => {
    const withToken = { ...COMBO, description: `<p>{{${partRef('p-basin')}.code}}</p>` } as ProductComboRow;
    const view = show(withToken);
    await waitFor(() =>
      expect(view.container.querySelector('[data-merge-field]')?.textContent).toBe('BASIN - SRTWB2380: code'),
    );
    combosQuery.value = { data: [{ ...withToken, parts: [] }], isLoading: false, isError: false };
    view.rerender(<ProductCombosSection productId="prod-host" productCode="SRTBF11829" />);
    await waitFor(() =>
      expect(view.container.querySelector('[data-merge-field]')?.textContent).toBe('Removed part: code'),
    );
    // No part id in anything the reader sees (owner 22:33).
    expect(view.container.textContent ?? '').not.toMatch(/\{\{part\./);
  });
});
