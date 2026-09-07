/**
 * "Update <template>" from a request tag (S6, PLAN D6, AC-S6-1/2/3/4/5/6).
 *
 * A `PlacedTag` carries the `template_id` it was cloned from. The toolbar's
 * Template dropdown offers "Update <name>" (published templates only) next
 * to "Save as new template"; confirming runs, in order:
 *   1. PUT the template's draft (the selected tag's current layers + size)
 *   2. POST publish, noted "Updated from <doc_number>"
 *   3. IF the sibling checkbox is on, spread the same design onto every
 *      OTHER line in this request that is currently on the same template
 *      (`applyDesignToSiblings`, pinned in isolation in
 *      `request-tags.test.ts`) - this file is the WIRING: the two service
 *      calls fire in that order, and the sibling apply happens ONLY when
 *      the checkbox stays on.
 *
 * Same stand-in idiom as `RequestTagDesigner.test.tsx` (Konva needs a real
 * canvas, unavailable in jsdom).
 */

import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from '@/lib/toast';
const mockToastSuccess = vi.mocked(toast.success);

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1/design',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings', () => ({
  useKitLibrary: () => ({
    assetUrls: {},
    fonts: [],
    specKeys: [],
    fontOptions: [],
    reload: vi.fn(async () => {}),
    remember: vi.fn(),
  }),
}));

type TagSheetDocCapture = { lineId: string; doc: TagTemplateDoc };
const canvasDocs: TagSheetDocCapture[] = [];
let currentLineId = '';

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor', () => ({
  TagCanvasEditor: ({
    doc,
    onLayersChange,
    leftRail,
    toolbarTrailing,
  }: {
    doc: TagTemplateDoc;
    onLayersChange?: (layers: TagLayer[]) => void;
    leftRail?: React.ReactNode;
    toolbarTrailing?: React.ReactNode;
  }) => {
    canvasDocs.push({ lineId: currentLineId, doc });
    const [layers, setLayers] = React.useState<TagLayer[]>(doc.layers);
    React.useEffect(() => {
      onLayersChange?.(doc.layers);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <div data-testid="canvas-editor">
        canvas: {layers.length} layers
        {leftRail}
        <div data-testid="toolbar-trailing">{toolbarTrailing}</div>
        <button
          type="button"
          onClick={() => {
            const next = [...layers, addedLayer(layers.length)];
            setLayers(next);
            onLayersChange?.(next);
          }}
        >
          Add layer
        </button>
        {/* B1: types a value into EVERY current layer's text_override,
            bound or not - the PUT map is what is supposed to tell them
            apart, not this button. */}
        <button
          type="button"
          onClick={() => {
            const next = layers.map((l) => ({ ...l, text_override: 'typed value' }));
            setLayers(next);
            onLayersChange?.(next);
          }}
        >
          Type into every layer
        </button>
      </div>
    );
  },
}));

vi.mock('./ArrangeSheetView', () => ({
  ArrangeSheetView: () => <div data-testid="arrange-view">arrange open</div>,
}));

vi.mock('../../../../services/tagTemplateService', () => ({
  listPublishedTemplates: vi.fn(),
  createTemplateFromTag: vi.fn(),
  updateTemplate: vi.fn(),
  publishTemplate: vi.fn(),
}));
vi.mock('../../../../services/priceTagRequestService', () => ({
  resolveRequestLines: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));
vi.mock('../../../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] as unknown[] }),
  useDeleteTagSizePreset: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));

import {
  listPublishedTemplates,
  publishTemplate,
  updateTemplate,
} from '../../../../services/tagTemplateService';
import { resolveRequestLines } from '../../../../services/priceTagRequestService';
import { RequestTagDesigner } from './RequestTagDesigner';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import type {
  LineTagData,
  TagLayer,
  TagTemplate,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';

const mockListTemplates = vi.mocked(listPublishedTemplates);
const mockResolveRequestLines = vi.mocked(resolveRequestLines);
const mockUpdateTemplate = vi.mocked(updateTemplate);
const mockPublishTemplate = vi.mocked(publishTemplate);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function line(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  return {
    id: 'line-a',
    line_type: 'product',
    product_id: 'prod-a',
    product_set_id: null,
    name: 'Kitchen Sink',
    code: 'AAA-1',
    show_promo_price: false,
    quantity: 1,
    alternatives: [],
    included_accessories: null,
    sort_order: 0,
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 1599,
    sell_price: null,
    ...overrides,
  };
}

function request(overrides: Partial<PriceTagRequestDetail> = {}): PriceTagRequestDetail {
  return {
    id: 'req-1',
    doc_number: 'PT-000001',
    debtor_code: null,
    debtor_name: null,
    promotion_id: null,
    promotion_name: null,
    needed_by_date: null,
    notes: null,
    status: 'designing',
    line_count: 2,
    created_at: '2026-09-01T00:00:00Z',
    assigned_to_id: 'user-1',
    assigned_to_name: 'Jayson',
    contact_name: 'Ziv Beh',
    contact_id: 'contact-1',
    lines: [
      line({ id: 'line-a', product_id: 'prod-a', code: 'AAA-1', name: 'Kitchen Sink' }),
      line({ id: 'line-b', product_id: 'prod-b', code: 'BBB-2', name: 'Basin' }),
    ],
    ...overrides,
  };
}

function lineTagData(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    line_id: 'line-a',
    code: 'AAA-1',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    ...overrides,
  };
}

function realTemplate(overrides: Partial<TagTemplate> = {}): TagTemplate {
  return {
    id: 'tpl-1',
    name: 'DIY Tag',
    family: 'ala_carte',
    doc: {
      layers: [
        {
          id: 'l1',
          type: 'text',
          x_mm: 0,
          y_mm: 0,
          width_mm: 20,
          height_mm: 10,
          rotation_deg: 0,
          z_index: 0,
          locked: false,
          visible: true,
          slot_binding: 'code',
          text_override: null,
          props: {
            kind: 'text',
            text: '',
            align: 'left',
            color: '#000',
            fontSize: 10,
            fontFamily: 'Jost',
            fontWeight: 400,
            lineHeight: 1.2,
            letterSpacing: 0,
          },
        },
      ],
      width_mm: 60,
      height_mm: 40,
    },
    print_size: { width_mm: 60, height_mm: 40 },
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    published_version_id: 'v1',
    published_version_no: 1,
    ...overrides,
  } as TagTemplate;
}

function addedLayer(index: number): TagLayer {
  return {
    id: `added-${index}`,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: index,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Added',
      align: 'left',
      color: '#000',
      fontSize: 10,
      fontFamily: 'Jost',
      fontWeight: 400,
      lineHeight: 1.2,
      letterSpacing: 0,
    },
  };
}

beforeEach(() => {
  canvasDocs.length = 0;
  currentLineId = '';
  vi.clearAllMocks();
  mockUpdateTemplate.mockResolvedValue(realTemplate() as never);
  mockPublishTemplate.mockResolvedValue(
    realTemplate({ published_version_no: 2 }) as never,
  );
});

/**
 * Both lines resolve, and both clone from the SAME published template - the
 * natural way two lines end up "siblings" on the same template_id.
 *
 * `tags[lineId]` only exists once a line has been the SELECTED one at least
 * once (the auto-clone effect fires on selection, not up front) - so a
 * "sibling" line the test never visited would read as no tag at all, and
 * `updateSiblingCount` would see 0. This visits line B once, then returns to
 * line A, so both tags exist before the Template dropdown ever opens.
 */
async function mountBothOnSameTemplate() {
  mockListTemplates.mockResolvedValue([realTemplate()]);
  mockResolveRequestLines.mockResolvedValue([
    lineTagData({ line_id: 'line-a', code: 'AAA-1', name: 'Kitchen Sink' }),
    lineTagData({ line_id: 'line-b', code: 'BBB-2', name: 'Basin' }),
  ]);

  render(
    <RequestTagDesigner
      request={request()}
      initialDoc={null}
      onSave={vi.fn(async () => {})}
      onAutosave={vi.fn(async () => {})}
    />,
  );
  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

  fireEvent.click(screen.getByText('Basin'));
  await waitFor(() => expect(screen.getByText(/canvas: 1 layers/)).toBeInTheDocument());
  fireEvent.click(screen.getByText('Kitchen Sink'));
  await waitFor(() => expect(screen.getByText(/canvas: 1 layers/)).toBeInTheDocument());
}

/** Radix opens its DropdownMenu on pointerdown, not click. */
function openTemplateMenu() {
  const trailing = within(screen.getByTestId('toolbar-trailing'));
  const trigger = trailing.getByRole('button', { name: 'Template' });
  fireEvent.pointerDown(trigger, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
}

function openUpdateDialog() {
  openTemplateMenu();
  fireEvent.click(screen.getByRole('menuitem', { name: 'Update "DIY Tag"' }));
}

describe('RequestTagDesigner - Update template (S6, AC-S6-1/2/3)', () => {
  it('the Template dropdown offers "Update <name>" and "Save as new template"', async () => {
    await mountBothOnSameTemplate();

    openTemplateMenu();

    expect(screen.getByRole('menuitem', { name: 'Update "DIY Tag"' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Save as new template' })).toBeInTheDocument();
  });

  it('the dialog names the template, the next version and the sibling count (AC-S6-2)', async () => {
    await mountBothOnSameTemplate();

    openUpdateDialog();

    expect(screen.getByText(/Publish this design as v2 of DIY Tag/)).toBeInTheDocument();
    expect(
      screen.getByText(/Also apply to the 1 other line in this request that use DIY Tag/),
    ).toBeInTheDocument();
  });

  it('confirms PUT then POST publish, in that order, noted with the doc number (AC-S6-3)', async () => {
    await mountBothOnSameTemplate();

    openUpdateDialog();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(mockPublishTemplate).toHaveBeenCalled());
    expect(mockUpdateTemplate).toHaveBeenCalledWith(
      'tpl-1',
      expect.objectContaining({ layers: expect.any(Array), width_mm: 60, height_mm: 40 }),
    );
    expect(mockPublishTemplate).toHaveBeenCalledWith('tpl-1', 'Updated from PT-000001');
    expect(mockUpdateTemplate.mock.invocationCallOrder[0]).toBeLessThan(
      mockPublishTemplate.mock.invocationCallOrder[0],
    );
  });

  it('Cancel changes nothing (AC-S6-6)', async () => {
    await mountBothOnSameTemplate();

    openUpdateDialog();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));

    expect(mockUpdateTemplate).not.toHaveBeenCalled();
    expect(mockPublishTemplate).not.toHaveBeenCalled();
    // Radix's own close animation unmounts the dialog a tick after the
    // click, not synchronously with it.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('RequestTagDesigner - Update template strips bound text_override (B1)', () => {
  it('a bound layer\'s text_override is null in the PUT payload, an unbound layer keeps its text', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1', name: 'Kitchen Sink' }),
    ]);

    render(
      <RequestTagDesigner
        request={request({ lines: [line({ id: 'line-a' })], line_count: 1 })}
        initialDoc={null}
        onSave={vi.fn(async () => {})}
        onAutosave={vi.fn(async () => {})}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    // The mocked canvas starts on the template's own single bound ("code")
    // layer; add an unbound one, then type a value into EVERY layer's
    // text_override - a real editor session typing a line-specific price or
    // name would leave the SAME shape (both bound and unbound layers
    // carrying a value), so this is what the PUT map has to tell apart.
    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    expect(screen.getByText(/canvas: 2 layers/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Type into every layer' }));

    openUpdateDialog();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(mockUpdateTemplate).toHaveBeenCalled());
    const [, payload] = mockUpdateTemplate.mock.calls[0];
    const bound = payload.layers.find((l: TagLayer) => l.slot_binding === 'code');
    const unbound = payload.layers.find((l: TagLayer) => l.id === 'added-1');

    expect(bound?.text_override).toBeNull();
    expect(unbound?.text_override).toBe('typed value');
  });
});

describe('RequestTagDesigner - Update template sibling checkbox (S6, AC-S6-4/5)', () => {
  it('with the checkbox ON (default), every other line on this template gets the new design', async () => {
    await mountBothOnSameTemplate();

    // A deliberate edit on line A - what "the same design" actually means.
    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    expect(screen.getByText(/canvas: 2 layers/)).toBeInTheDocument();

    openUpdateDialog();
    // Checkbox defaults ON - confirm without touching it.
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Publish' }));

    await waitFor(() =>
      expect(mockToastSuccess).toHaveBeenCalledWith(
        expect.stringContaining('applied to 1 other line'),
        expect.anything(),
      ),
    );

    // Switch to the sibling line - its tag now carries the 2-layer design,
    // not the template's original 1-layer clone.
    fireEvent.click(screen.getByText('Basin'));
    await waitFor(() =>
      expect(screen.getByText(/canvas: 2 layers/)).toBeInTheDocument(),
    );
  });

  it('with the checkbox OFF, the sibling line is left exactly as it was (AC-S6-5)', async () => {
    await mountBothOnSameTemplate();

    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    expect(screen.getByText(/canvas: 2 layers/)).toBeInTheDocument();

    openUpdateDialog();
    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByRole('checkbox'));
    fireEvent.click(dialog.getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(mockPublishTemplate).toHaveBeenCalled());
    // No "applied to" phrasing when the checkbox was off.
    expect(mockToastSuccess).toHaveBeenCalledWith(expect.stringContaining('Updated "DIY Tag"'));
    expect(mockToastSuccess).not.toHaveBeenCalledWith(
      expect.stringContaining('applied to'),
    );

    // The sibling line's own tag is UNCHANGED - still its own 1-layer clone.
    fireEvent.click(screen.getByText('Basin'));
    await waitFor(() =>
      expect(screen.getByText(/canvas: 1 layers/)).toBeInTheDocument(),
    );
  });
});
