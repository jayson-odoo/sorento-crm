/**
 * PRICETAG-COMBO-FORMAT R17: the combo photo opens in the REAL preview modal as an image. The modal
 * picks its viewer from the item's file name, so the item must carry the attachment's file name
 * ("cabinet.jpg"), not the combo name ("3 in 1", which reads as an unknown type and shows
 * "No inline preview for this file type").
 *
 * Written test-FIRST: the section passes the combo name today. Same mocks as
 * `ProductCombosSection.rich.test.tsx`, minus the modal stand-in.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProductComboRow } from '../../types/productCombo.types';

const permission = vi.hoisted(() => ({ canEdit: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => permission.canEdit,
}));

vi.mock('./ComboTemplatesField', () => ({ ComboTemplatesField: () => null }));
// The accessory list has its own suite; here it stands in as a labelled marker.
vi.mock('./AccessoryListField', () => ({
  AccessoryListField: (props: { label?: string; ownerId: string; canEdit: boolean }) => (
    <div data-testid="accessory-list" data-owner={props.ownerId} data-can-edit={String(props.canEdit)}>
      {props.label}
    </div>
  ),
}));
vi.mock('./AddComboModal', () => ({ AddComboModal: () => null }));
vi.mock('@/components/common/SearchableSelect', () => ({ SearchableSelect: () => null }));

vi.mock('@/components/ui/rich-text-editor', () => {
  const Stand = (props: {
    value?: string;
    onChange: (v: string) => void;
    onBlur?: React.FocusEventHandler<HTMLTextAreaElement>;
  }) => (
    <textarea
      data-testid="rte"
      value={props.value ?? ''}
      onChange={(e) => props.onChange(e.target.value)}
      onBlur={props.onBlur}
    />
  );
  return { RichTextEditor: Stand, default: Stand };
});

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  default: (props: { payload: unknown; emptyMessage?: string }) => (
    <div data-testid="design-viewer">{props.payload ? JSON.stringify(props.payload) : props.emptyMessage}</div>
  ),
}));

const links = vi.hoisted(() => ({ rows: [] as unknown[] }));
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  comboTagTemplatesKey: (id: string) => ['combo-tag-templates', id],
  useComboTagTemplates: () => ({ data: links.rows, isLoading: false, isError: false }),
  useSetComboTagTemplates: () => ({ mutate: vi.fn(), isPending: false }),
  usePriceTagTemplateOptions: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

const template = {
  id: 'tpl-sp',
  name: 'Bathroom Furniture SP',
  family: 'ala_carte',
  print_size: { width_mm: 85, height_mm: 58 },
  published_version_id: 'v1',
  published_version_no: 1,
  doc: {
    layers: [
      {
        id: 'desc',
        type: 'text',
        x_mm: 0,
        y_mm: 0,
        width_mm: 80,
        height_mm: 40,
        rotation_deg: 0,
        z_index: 1,
        locked: false,
        visible: true,
        slot_binding: 'combo_description',
        text_override: null,
        props: {
          kind: 'text',
          text: '',
          fontFamily: 'DM Sans',
          fontSize: 8,
          fontWeight: 400,
          color: '#000000',
          align: 'left',
          lineHeight: 1.2,
          letterSpacing: 0,
        },
      },
    ],
  },
};
vi.mock('@/app/(protected)/dealer-kit/services/tagTemplateService', () => ({
  getTemplate: vi.fn(async () => template),
  listTemplates: vi.fn(async () => [template]),
  listPublishedTemplates: vi.fn(async () => [template]),
}));

const combosQuery = vi.hoisted(() => ({
  value: { data: [] as ProductComboRow[], isLoading: false, isError: false },
}));
const updateComboMutate = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/useProductCombos', () => ({
  useProductCombos: () => combosQuery.value,
  useProductComboDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useProductComboPartDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useAddProductComboPart: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProductComboPart: () => ({ mutate: vi.fn() }),
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

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProductCombosSection } from './ProductCombosSection';

function combo(over: Partial<ProductComboRow> = {}): ProductComboRow {
  return {
    id: 'combo-3',
    host_product_id: 'prod-cabinet',
    name: '3 in 1',
    sort_order: 0,
    description: null,
    parts: [],
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    ...over,
  };
}

function draw(row: ProductComboRow) {
  combosQuery.value = { data: [row], isLoading: false, isError: false };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductCombosSection productId="prod-cabinet" />
    </QueryClientProvider>,
  );
}

const URL = 'https://cdn.example.test/combo.jpg';

function openPhoto(image: Record<string, unknown>) {
  draw(combo({ image: image as never }));
  fireEvent.click(screen.getByRole('button', { name: 'Preview photo of 3 in 1' }));
}

describe('combo photo in the real preview modal (R17)', () => {
  it('R17: a photo with a file name opens as an image', async () => {
    openPhoto({ attachment_id: 'att-1', url: URL, file_name: 'cabinet.jpg', mime_type: 'image/jpeg' });
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelector(`img[src="${URL}"]`)).not.toBeNull();
    expect(screen.queryByText('No inline preview for this file type.')).toBeNull();
  });

  it('R17: the photo is not treated as an unknown file type', async () => {
    openPhoto({ attachment_id: 'att-1', url: URL, file_name: 'cabinet.jpg', mime_type: 'image/jpeg' });
    await screen.findByRole('dialog');
    expect(screen.queryByText(/No inline preview/)).toBeNull();
  });
});
