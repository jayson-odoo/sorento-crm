/**
 * PRICETAG-COMBO-FORMAT S4 + S8 on the Combos section (AC-21, AC-23, AC-24, AC-40, AC-41, AC-42).
 *
 * Written test-FIRST. The description is a plain Textarea today, there is no live preview, and the
 * thumbnail is a bare <img>.
 *
 * Mocks follow `ProductCombosSection.test.tsx`. Two stand-ins matter here:
 * - `RichTextEditor` is a textarea with the same `value` / `onChange` (and `onBlur`, whichever of
 *   the editor or a wrapper the implementation puts it on), so the test drives the section's
 *   wiring, not tiptap (the editor has its own suite);
 * - `DesignViewer` prints the payload it is given as JSON, so "the preview shows what I typed" is
 *   an assertion on that payload.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

// R18: the live preview asks the staff preview service for the combo's line and draws the response
// (its template, line and images) with only the description replaced by the draft.
const TEMPLATE = {
  id: 'tpl-sp',
  name: 'Bathroom Furniture SP',
  family: 'ala_carte',
  doc: { layers: [], width_mm: 85, height_mm: 58 },
  print_size: { width_mm: 85, height_mm: 58 },
  published_version_id: 'v1',
  published_version_no: 1,
};
const previewTags = vi.hoisted(() => vi.fn());
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  previewTags,
}));
vi.mock('@/app/(protected)/dealer-kit/hooks/usePublishedTagTemplates', () => ({
  usePublishedTagTemplates: () => ({ data: [], isLoading: false, isError: false }),
}));

const preview = vi.hoisted(() => ({
  open: [] as Array<{ open: boolean; items: unknown[] }>,
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => {
  // A named component, so the hook below sits in a React component (rules-of-hooks).
  function PreviewModalStub({
    open,
    onOpenChange,
    items,
  }: {
    open: boolean;
    onOpenChange: (o: boolean) => void;
    items: unknown[];
  }) {
    preview.open.push({ open, items });
    React.useEffect(() => {
      if (!open) return;
      const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onOpenChange(false);
      document.addEventListener('keydown', onKey);
      return () => document.removeEventListener('keydown', onKey);
    }, [open, onOpenChange]);
    return open ? <div data-testid="preview-modal" data-items={JSON.stringify(items)} /> : null;
  }
  return { default: PreviewModalStub };
});

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

const SAVED = '<p><strong>SRTBF11416</strong> (CABINET)</p>';

function combo(over: Partial<ProductComboRow> = {}): ProductComboRow {
  return {
    id: 'combo-3',
    host_product_id: 'prod-cabinet',
    name: '3 in 1',
    sort_order: 0,
    description: SAVED,
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

beforeEach(() => {
  vi.clearAllMocks();
  previewTags.mockImplementation(async (...args: unknown[]) => {
    const key = (JSON.parse(JSON.stringify(args)).flat(3).find((x: { key?: string }) => x && x.key) ?? { key: 'k' }).key;
    return {
      lines: [{ line_id: key, tag_id: key, code: '3 in 1', name: '3 in 1', images: [], combo: { id: 'combo-3', name: '3 in 1', description: null, choices: [], upgrades: [] } }],
      templates: { [key]: TEMPLATE },
      assets: {},
      images: {},
      fonts: [],
    };
  });
  permission.canEdit = true;
  links.rows = [];
  preview.open = [];
});

describe('combo description editor (AC-21)', () => {
  it('AC-21: an editor user gets the rich editor holding the saved HTML', () => {
    draw(combo());
    expect((screen.getByTestId('rte') as HTMLTextAreaElement).value).toBe(SAVED);
  });

  it('AC-21: blur saves the HTML through the combo PATCH', () => {
    draw(combo());
    const editor = screen.getByTestId('rte');
    fireEvent.change(editor, { target: { value: '<p><strong>NEW</strong></p>' } });
    expect(updateComboMutate).not.toHaveBeenCalled();
    fireEvent.blur(editor);

    expect(updateComboMutate).toHaveBeenCalledWith(
      { comboId: 'combo-3', write: { description: '<p><strong>NEW</strong></p>' } },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('AC-21: blur without a change saves nothing', () => {
    draw(combo());
    fireEvent.blur(screen.getByTestId('rte'));
    expect(updateComboMutate).not.toHaveBeenCalled();
  });

  it('AC-21: a failed save puts the saved HTML back', () => {
    draw(combo());
    const editor = screen.getByTestId('rte') as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '<p>lost</p>' } });
    fireEvent.blur(editor);
    const { onError } = updateComboMutate.mock.calls[0][1] as { onError: () => void };
    act(() => onError());

    expect((screen.getByTestId('rte') as HTMLTextAreaElement).value).toBe(SAVED);
  });
});

describe('live tag preview beside the editor (AC-23)', () => {
  const defaultLink = {
    id: 'tpl-sp',
    name: 'Bathroom Furniture SP',
    family: 'ala_carte',
    published: true,
    width_mm: 85,
    height_mm: 58,
    price_type: 'selling',
    is_default: true,
    default_list: true,
    default_selling: true,
  };

  it('AC-23: with a default template the combo is drawn through DesignViewer', async () => {
    links.rows = [defaultLink];
    draw(combo());
    const viewer = await screen.findByTestId('design-viewer');
    expect(viewer.textContent).toContain('CABINET');
  });

  it('AC-23: typing updates the preview before the blur', async () => {
    links.rows = [defaultLink];
    draw(combo());
    await screen.findByTestId('design-viewer');
    fireEvent.change(screen.getByTestId('rte'), { target: { value: '<p>TYPED-BEFORE-BLUR</p>' } });

    await waitFor(() =>
      expect(screen.getByTestId('design-viewer').textContent).toContain('TYPED-BEFORE-BLUR'),
    );
    expect(updateComboMutate).not.toHaveBeenCalled();
  });

  it('AC-23: with no default template the preview says so', async () => {
    links.rows = [];
    draw(combo());
    expect(await screen.findByText('No price tag template linked')).toBeInTheDocument();
    expect(screen.queryByTestId('design-viewer')).toBeNull();
  });
});

describe('read-only description (AC-24)', () => {
  it('AC-24: shows the formatting, never the tags', () => {
    permission.canEdit = false;
    const { container } = draw(combo());

    expect(screen.queryByTestId('rte')).toBeNull();
    const code = screen.getByText('SRTBF11416');
    const bold =
      code.tagName === 'STRONG' ||
      /bold|700|600/.test(code.style.fontWeight) ||
      /font-(bold|semibold)/.test(code.className);
    expect(bold).toBe(true);
    for (const raw of ['<strong>', '</strong>', '<p>', '&lt;']) {
      expect(container.textContent, raw).not.toContain(raw);
    }
  });
});

describe('combo photo preview (AC-40, AC-41, AC-42)', () => {
  // R17: the serialised image names the file, so the viewer can tell what kind of file it is.
  const image = {
    attachment_id: 'att-combo-1',
    url: 'https://cdn.example.test/combo.jpg',
    file_name: 'cabinet.jpg',
    mime_type: 'image/jpeg',
  };

  it('AC-40: the thumbnail is a button named for the combo; click opens the preview with the item', () => {
    draw(combo({ image }));
    const trigger = screen.getByRole('button', { name: 'Preview photo of 3 in 1' });
    // A native button, so Enter and Space open it without extra key handling.
    expect(trigger.tagName).toBe('BUTTON');
    expect(screen.queryByTestId('preview-modal')).toBeNull();

    fireEvent.click(trigger);

    const modal = screen.getByTestId('preview-modal');
    expect(JSON.parse(modal.dataset.items!)).toEqual([
      { id: 'att-combo-1', name: 'cabinet.jpg', url: 'https://cdn.example.test/combo.jpg' },
    ]);
  });

  it('R17: without a file name the item falls back to the combo name', () => {
    draw(combo({ image: { attachment_id: 'att-combo-1', url: 'https://cdn.example.test/combo.jpg' } as never }));
    fireEvent.click(screen.getByRole('button', { name: 'Preview photo of 3 in 1' }));
    const items = JSON.parse(screen.getByTestId('preview-modal').dataset.items!);
    expect(items[0].name).toBe('3 in 1');
  });

  it('AC-40: Escape closes it', () => {
    draw(combo({ image }));
    fireEvent.click(screen.getByRole('button', { name: 'Preview photo of 3 in 1' }));
    expect(screen.getByTestId('preview-modal')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByTestId('preview-modal')).toBeNull();
  });

  it('AC-41: a read-only user can open it, and has no Replace or Clear', () => {
    permission.canEdit = false;
    draw(combo({ image }));
    fireEvent.click(screen.getByRole('button', { name: 'Preview photo of 3 in 1' }));

    expect(screen.getByTestId('preview-modal')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /replace/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /clear/i })).toBeNull();
  });

  it('AC-41: an editor still has Replace and Clear beside it', () => {
    draw(combo({ image }));
    const block = screen.getByText('3 in 1').closest('[data-testid="combo-block"]') as HTMLElement;
    expect(within(block).getByRole('button', { name: /replace/i })).toBeInTheDocument();
    expect(within(block).getByRole('button', { name: /clear/i })).toBeInTheDocument();
  });

  it('AC-42: a combo without a photo has no preview button (unchanged)', () => {
    draw(combo({ image: null }));
    expect(screen.queryByRole('button', { name: /Preview photo of/ })).toBeNull();
  });
});
