/**
 * Previewing a multi-block template, through the editor itself (D53, D10/S6).
 *
 * The pure rules are pinned in `lib/dealer-kit/preview.test.ts`. This is the
 * wiring: that each previewable block carries its OWN eye (shown while
 * hovered or selected, D10) rather than one toolbar-wide chip, that choosing
 * a product through one block's eye draws that block only, and that none of
 * it reaches the document Save writes. That last one is the whole safety
 * property of preview, so it is asserted rather than assumed.
 *
 * Konva does not run in jsdom, so the canvas is stood in for by a div per
 * layer carrying the text the editor resolved for it - the stand-in also
 * forwards `onSelect`/`onHoverChange` so a test can drive the SAME
 * hover/select signals the real Konva nodes would, which is what reveals a
 * block's eye chip in the first place.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProductTagData, TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultImageProps, defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

// -- Stand-ins for everything that needs a browser or a server ---------------

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Rect: passthrough('rect'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    display,
    onSelect,
    onHoverChange,
  }: {
    layer: TagLayer;
    display?: { text?: string; imageUrl?: string | null };
    onSelect?: (id: string, additive: boolean) => void;
    onHoverChange?: (id: string, hovering: boolean) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      data-image={display?.imageUrl ?? ''}
      onClick={() => onSelect?.(layer.id, false)}
      onMouseEnter={() => onHoverChange?.(layer.id, true)}
      onMouseLeave={() => onHoverChange?.(layer.id, false)}
    >
      {display?.text ?? ''}
    </div>
  ),
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => {}),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

const PRODUCTS: Record<string, ProductTagData> = {
  'p-sink': {
    id: 'p-sink',
    code: 'CBF3612',
    name: 'Carysil Big Bowl Sink',
    dimensions: 'L860xW500xH220mm',
    spec_lines: ['Nano grain finish'],
    specs: [{ key: 'material', label: 'Material', value: 'granite', unit: null }],
    images: [],
    list_price: 2000,
    offer_price: 1500,
    promotion_id: null,
    barcode: null,
  },
  'p-tap': {
    id: 'p-tap',
    code: 'SRT2201',
    name: 'Sorento Pillar Tap',
    dimensions: 'L200xW50xH300mm',
    spec_lines: ['Brass body'],
    specs: [],
    images: [],
    list_price: 400,
    offer_price: 320,
    promotion_id: null,
    barcode: null,
  },
};

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () =>
    Object.values(PRODUCTS).map((product) => ({
      value: product.id,
      label: product.code,
      description: product.name,
    })),
  ),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async (id: string) => PRODUCTS[id]),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

import { TagCanvasEditor } from './TagCanvasEditor';

// -- The document under test -------------------------------------------------

function base(id: string): Omit<TagLayer, 'props'> {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 20,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
  };
}

/** One product block: a photo and a code, wrapped in a group that ships unbound. */
function block(slug: string): TagLayer[] {
  return [
    {
      ...base(`${slug}-image`),
      type: 'image',
      slot_binding: 'product_image',
      props: defaultImageProps(),
    },
    {
      ...base(`${slug}-code`),
      slot_binding: 'code',
      props: { ...defaultTextProps(), text: 'Product code' },
    },
    {
      ...base(slug),
      type: 'group',
      props: {
        kind: 'group',
        children: [`${slug}-image`, `${slug}-code`],
        binding: {},
      },
    },
  ];
}

const MAIN_LABEL = 'Group (2) - block 1 - Product code';
const ALT_LABEL = 'Group (2) - block 2 - Product code';

function twoBlockDoc(): TagTemplateDoc {
  return {
    width_mm: 125.9,
    height_mm: 88.6,
    layers: [...block('main'), ...block('alt-a')],
  };
}

function oneBlockDoc(): TagTemplateDoc {
  return { ...twoBlockDoc(), layers: block('main') };
}

/**
 * A block's label carries `(N)` (e.g. `Group (2) - block 1 - ...`) - literal
 * parentheses that a `RegExp` would read as a capturing group, not text. A
 * plain substring matcher sidesteps that entirely.
 */
function accessibleNameIncludes(text: string) {
  return (name: string) => name.includes(text);
}

/** Hovering a block reveals its own eye chip (D10, AC-S6-4). */
function hoverBlock(groupId: string) {
  fireEvent.mouseEnter(screen.getByTestId(`layer-${groupId}`));
}

/** Open a block's own picker via its on-canvas eye - hover then click. */
async function openBlockPreview(groupId: string, label: string) {
  hoverBlock(groupId);
  fireEvent.click(
    await screen.findByRole('button', { name: accessibleNameIncludes(`Preview ${label}`) }),
  );
}

/** Choose the one product a single-mode picker offers. */
async function choose(code: string) {
  fireEvent.click(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: new RegExp(code) }));
}

describe('TagCanvasEditor preview per block (D53, D10/S6)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a block eye only while that block is hovered', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    expect(screen.queryByRole('button', { name: accessibleNameIncludes(MAIN_LABEL) })).toBeNull();

    hoverBlock('main');
    expect(await screen.findByRole('button', { name: accessibleNameIncludes(MAIN_LABEL) })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: accessibleNameIncludes(ALT_LABEL) })).toBeNull();

    hoverBlock('alt-a');
    expect(await screen.findByRole('button', { name: accessibleNameIncludes(ALT_LABEL) })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: accessibleNameIncludes(MAIN_LABEL) })).toBeNull();
  });

  it("opens that block's own single-question picker", async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    await openBlockPreview('main', MAIN_LABEL);

    expect(await screen.findByText('Preview this block with')).toBeInTheDocument();
  });

  it('draws each block against its own product and leaves the rest alone', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    await openBlockPreview('main', MAIN_LABEL);
    await choose('CBF3612');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));

    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );
    expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('Product code');

    await openBlockPreview('alt-a', ALT_LABEL);
    await choose('SRT2201');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));

    await waitFor(() =>
      expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('SRT2201'),
    );
    // The block previewed a moment ago is untouched by the second choice.
    expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612');
  });

  it('names the block the same way whether the template has one or several', async () => {
    render(<TagCanvasEditor doc={oneBlockDoc()} onChange={vi.fn()} />);

    await openBlockPreview('main', MAIN_LABEL);
    expect(await screen.findByText('Preview this block with')).toBeInTheDocument();

    await choose('CBF3612');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));

    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: /Previewing CBF3612 - Carysil Big Bowl Sink/,
        }),
      ).toBeInTheDocument(),
    );
  });

  it('writes nothing it previewed into the document Save sends', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={onChange} />);

    await openBlockPreview('main', MAIN_LABEL);
    await choose('CBF3612');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );
    // The dialog's exit animation keeps it (and its aria-hidden on the rest of
    // the page) mounted a tick after the state update lands.
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    const saved = onChange.mock.calls[0][0] as TagTemplateDoc;
    for (const layer of saved.layers) {
      if (layer.props.kind === 'group') expect(layer.props.binding).toEqual({});
      expect(layer.text_override).toBeNull();
    }
  });

  it("clears one block's preview from the Inspector, independent of the other", async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    await openBlockPreview('main', MAIN_LABEL);
    await choose('CBF3612');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    await openBlockPreview('alt-a', ALT_LABEL);
    await choose('SRT2201');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await waitFor(() =>
      expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('SRT2201'),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    // Selecting a layer inside the main block surfaces its Clear action in
    // the Inspector (D53's existing per-block sidebar, unchanged by S6).
    fireEvent.click(screen.getByTestId('layer-main-code'));
    fireEvent.click(await screen.findByTitle('Stop previewing this block'));

    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('Product code'),
    );
    expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('SRT2201');
  });

  // -- B1: the chip must survive the pointer crossing onto it (AC-S6-4) -----

  it('keeps the eye chip mounted while the pointer crosses onto it, so the later click lands (B1, AC-S6-4)', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    hoverBlock('main');
    const chip = await screen.findByRole('button', {
      name: accessibleNameIncludes(MAIN_LABEL),
    });

    // The pointer crossing from the Konva shape onto the chip is ONE
    // continuous mouse movement: the Stage's own mouseleave on the block and
    // the chip's own mouseenter both fire from it, together - unlike the
    // click that follows a moment later, a genuinely separate gesture. The
    // OLD mock never fired this leave at all, which is why the bug never
    // showed up in the earlier "opens that block's own picker" test above.
    act(() => {
      fireEvent.mouseLeave(screen.getByTestId('layer-main'));
      fireEvent.mouseEnter(chip);
    });

    // Still mounted, still the SAME element - not remounted from a fallback.
    expect(screen.getByRole('button', { name: accessibleNameIncludes(MAIN_LABEL) })).toBe(
      chip,
    );

    fireEvent.mouseDown(chip);
    fireEvent.click(chip);

    expect(await screen.findByText('Preview this block with')).toBeInTheDocument();
  });

  // -- S1/AC-S6-5: the whole-tag eye, and clearing it -----------------------

  function looseLayerDoc(): TagTemplateDoc {
    return {
      width_mm: 60,
      height_mm: 40,
      layers: [
        {
          ...base('loose-code'),
          slot_binding: 'code',
          props: { ...defaultTextProps(), text: 'Product code' },
        },
      ],
    };
  }

  it("previews every loose bound layer from the frame's eye, and clears it in one click (S1, AC-S6-5)", async () => {
    render(<TagCanvasEditor doc={looseLayerDoc()} onChange={vi.fn()} />);

    const frameEye = await screen.findByRole('button', {
      name: 'Preview the whole tag',
    });
    // No clear affordance while nothing is previewed yet.
    expect(
      screen.queryByRole('button', { name: 'Stop previewing the whole tag' }),
    ).toBeNull();

    fireEvent.click(frameEye);
    await choose('CBF3612');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));

    await waitFor(() =>
      expect(screen.getByTestId('layer-loose-code')).toHaveTextContent('CBF3612'),
    );

    const clear = await screen.findByRole('button', {
      name: 'Stop previewing the whole tag',
    });
    fireEvent.click(clear);

    await waitFor(() =>
      expect(screen.getByTestId('layer-loose-code')).toHaveTextContent('Product code'),
    );
    expect(
      screen.queryByRole('button', { name: 'Stop previewing the whole tag' }),
    ).toBeNull();
  });
});
