/**
 * COMBO-SETTINGS-UX rule 3 (owner 10 Nov, mock v2 approved): each part, and the main product, gets a
 * Label ("CABINET"); the Description gets an Insert field button (Combo and Combo positions fields,
 * incl. "All parts as a list"); and "Each part prints as" opens the combo's own part line in the same
 * editor, starting on the default line. Edits save on blur / close, like the rest of the block.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';

import type { ProductComboPartRow, ProductComboRow } from '../../types/productCombo.types';

const permission = vi.hoisted(() => ({ canEdit: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => permission.canEdit,
}));

// PRICETAG-COMBO-FORMAT AC-21: the description is the shared RichTextEditor (its own suite covers
// tiptap) and the live tag preview has its own suite; both are stood in for here so these tests
// keep pinning what they always did.
vi.mock('@/components/ui/rich-text-editor', () => {
  // A stand-in with just enough of the editor API for "insert at the caret": insertContent appends.
  const Stand = (props: {
    value?: string;
    onChange: (v: string) => void;
    onEditorReady?: (editor: unknown) => void;
    'aria-labelledby'?: string;
  }) => {
    const html = React.useRef(props.value ?? '');
    html.current = props.value ?? '';
    React.useEffect(() => {
      const chain = {
        focus: () => chain,
        insertContent: (content: string) => {
          html.current = html.current.replace(/<\/p>$/, `${content}</p>`) || `<p>${content}</p>`;
          props.onChange(html.current);
          return chain;
        },
        run: () => true,
      };
      props.onEditorReady?.({ chain: () => chain, getHTML: () => html.current });
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <textarea
        aria-labelledby={props['aria-labelledby']}
        value={props.value ?? ''}
        onChange={(e) => props.onChange(e.target.value)}
      />
    );
  };
  return { RichTextEditor: Stand, default: Stand };
});
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
import { DEFAULT_PARTS_LINE } from '@/lib/dealer-kit/combo-parts';

const part = (over: Partial<ProductComboPartRow> & Pick<ProductComboPartRow, 'id' | 'code'>): ProductComboPartRow =>
  ({
    combo_id: 'combo-b',
    product_id: `p-${over.id}`,
    product_name: over.code,
    dimensions: null,
    choice_group: null,
    sort_order: 0,
    ...over,
  }) as ProductComboPartRow;

const BASIN = part({ id: 'basin', code: 'SRTWB2380', label: 'BASIN' } as never);
const WASTE = part({ id: 'waste', code: 'SRTW2600', sort_order: 1 });
const COMBO = {
  id: 'combo-b',
  host_product_id: 'prod-host',
  name: 'SRTBF11829 + SRTMCB8083-BL',
  sort_order: 0,
  description: null,
  main_label: 'CABINET',
  parts_line: null,
  parts: [BASIN, WASTE],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
} as unknown as ProductComboRow;

function show(combo: ProductComboRow = COMBO) {
  combosQuery.value = { data: [combo], isLoading: false, isError: false };
  return render(<ProductCombosSection productId="prod-host" productCode="SRTBF11829" />);
}

beforeEach(() => {
  permission.canEdit = true;
  updateComboMutate.mockReset();
  updatePartMutate.mockReset();
  insertDialog.props = null;
  previewProps.last = null;
});

describe('part labels', () => {
  it('each part has a Label box with its saved label; a change saves on blur, blank saves null', () => {
    show();
    const basin = screen.getByLabelText('Label for SRTWB2380') as HTMLInputElement;
    expect(basin.value).toBe('BASIN');
    fireEvent.change(basin, { target: { value: ' BASIN 800 ' } });
    fireEvent.blur(basin);
    expect(updatePartMutate).toHaveBeenCalledWith(
      { partId: 'basin', write: { label: 'BASIN 800' } },
      expect.anything(),
    );
    const waste = screen.getByLabelText('Label for SRTW2600') as HTMLInputElement;
    expect(waste.value).toBe('');
    fireEvent.change(waste, { target: { value: 'POP UP WASTE' } });
    fireEvent.blur(waste);
    expect(updatePartMutate).toHaveBeenLastCalledWith(
      { partId: 'waste', write: { label: 'POP UP WASTE' } },
      expect.anything(),
    );
    fireEvent.change(basin, { target: { value: '   ' } });
    fireEvent.blur(basin);
    expect(updatePartMutate).toHaveBeenLastCalledWith({ partId: 'basin', write: { label: null } }, expect.anything());
  });

  it('an unchanged label saves nothing', () => {
    show();
    fireEvent.blur(screen.getByLabelText('Label for SRTWB2380'));
    expect(updatePartMutate).not.toHaveBeenCalled();
  });

  it('the main product has a Label box too, saved on the combo', () => {
    show();
    const main = screen.getByLabelText('Label for SRTBF11829 (main product)') as HTMLInputElement;
    expect(main.value).toBe('CABINET');
    fireEvent.change(main, { target: { value: 'S/STEEL CABINET' } });
    fireEvent.blur(main);
    expect(updateComboMutate).toHaveBeenCalledWith(
      { comboId: 'combo-b', write: { main_label: 'S/STEEL CABINET' } },
      expect.anything(),
    );
  });

  it('a reader without edit permission sees the labels as text', () => {
    permission.canEdit = false;
    show();
    expect(screen.queryByLabelText('Label for SRTWB2380')).toBeNull();
    expect(screen.getByText('BASIN')).toBeInTheDocument();
    expect(screen.getByText('CABINET')).toBeInTheDocument();
  });
});

describe('description fields', () => {
  it('Insert field opens the field picker limited to the combo fields, never the description itself', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    expect(screen.getByRole('dialog', { name: 'Insert field' })).toBeInTheDocument();
    expect(insertDialog.props?.groups).toEqual(['Combo', 'Combo positions']);
    expect(insertDialog.props?.omitPaths).toEqual(['combo.description']);
  });

  it("the picker names this combo's positions by their codes (review S3)", () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    const data = insertDialog.props?.data as { kind: string; product: { slots: { main: { code: string }; fixed: { code: string }[] } } };
    expect(data.kind).toBe('product');
    expect(data.product.slots.main.code).toBe('SRTBF11829');
    expect(data.product.slots.fixed.map((p) => p.code)).toEqual(['SRTWB2380', 'SRTW2600']);
  });

  it('once the preview has this combo\'s real tag data, Insert field previews against it (owner round 1)', () => {
    show();
    const real = { kind: 'product', product: { code: 'SRTBF11829', combo: { main_label: 'CABINET' }, slots: null } };
    act(() => {
      (previewProps.last?.onBinding as (b: unknown) => void)(real);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    expect(insertDialog.props?.data).toEqual(real);
  });

  it('an inserted field is saved at once, not only on a later blur (review S4)', () => {
    show({ ...COMBO, description: '<p>Intro</p>' } as ProductComboRow);
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    act(() => {
      (insertDialog.props?.onDone as (c: string) => void)('{{combo.parts}}');
    });
    expect(updateComboMutate).toHaveBeenCalledWith(
      { comboId: 'combo-b', write: { description: '<p>Intro{{combo.parts}}</p>' } },
      expect.anything(),
    );
  });

  it('"Each part prints as" opens the part line on the default, and a change saves on close', async () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Each part prints as' }));
    const editor = (await screen.findByLabelText('Each part prints as')) as HTMLTextAreaElement;
    expect(editor.value).toBe(DEFAULT_PARTS_LINE);
    expect(screen.getByRole('button', { name: 'Insert part field' })).toBeInTheDocument();
    fireEvent.change(editor, { target: { value: '<p>- {{part.code}}</p>' } });
    // The preview follows the draft line before it is saved.
    expect((previewProps.last?.partsLine as string) ?? '').toBe('<p>- {{part.code}}</p>');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(updateComboMutate).toHaveBeenCalledWith(
      { comboId: 'combo-b', write: { parts_line: '<p>- {{part.code}}</p>' } },
      expect.anything(),
    );
  });

  it('closing the part line unchanged saves nothing', async () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Each part prints as' }));
    await screen.findByLabelText('Each part prints as');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(updateComboMutate).not.toHaveBeenCalled();
  });
});
