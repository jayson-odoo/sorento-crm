/**
 * Previewing a multi-block template, through the editor itself (D53).
 *
 * The pure rules are pinned in `lib/dealer-kit/preview.test.ts`. This is the
 * wiring: that the picker offers one row per block, that applying two products
 * draws each block against its OWN product, and that none of it reaches the
 * document Save writes. That last one is the whole safety property of preview,
 * so it is asserted rather than assumed.
 *
 * Konva does not run in jsdom, so the canvas is stood in for by a div per
 * layer carrying the text the editor resolved for it. That is exactly the
 * boundary under test: the editor decides what each layer shows and hands it
 * down as `display`.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  }: {
    layer: TagLayer;
    display?: { text?: string; imageUrl?: string | null };
  }) => (
    <div data-testid={`layer-${layer.id}`} data-image={display?.imageUrl ?? ''}>
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

/** Open the picker the toolbar's eye leads to. */
function openPreview() {
  fireEvent.click(screen.getByRole('button', { name: 'Preview with a product' }));
}

/**
 * Choose a product in one row of the block picker.
 *
 * The popover is opened by STATE rather than by one event: the first click
 * after another popover shut opens a menu that the closing layer then dismisses
 * again a tick later, so a single `fireEvent.click` on the second row leaves
 * nothing on screen to choose from.
 */
async function chooseInRow(label: string, code: string) {
  const row = screen.getByText(label).closest('div')!;
  const trigger = within(row).getByRole('combobox');
  await waitFor(async () => {
    if (trigger.getAttribute('aria-expanded') !== 'true') fireEvent.click(trigger);
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });
  fireEvent.click(await screen.findByRole('option', { name: new RegExp(code) }));
}

describe('TagCanvasEditor preview per block (D53)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers one row per previewable block', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    openPreview();

    expect(await screen.findByText('Preview with products')).toBeInTheDocument();
    expect(screen.getByText('Group (2) - block 1 - Product code')).toBeInTheDocument();
    expect(screen.getByText('Group (2) - block 2 - Product code')).toBeInTheDocument();
  });

  it('draws each block against its own product and leaves the rest alone', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    openPreview();
    await screen.findByText('Preview with products');
    await chooseInRow('Group (2) - block 1 - Product code', 'CBF3612');
    await chooseInRow('Group (2) - block 2 - Product code', 'SRT2201');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );
    expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('SRT2201');
    expect(screen.getByText('Previewing 2 of 2 blocks')).toBeInTheDocument();
  });

  it('keeps an unpreviewed block on its placeholder', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    openPreview();
    await screen.findByText('Preview with products');
    await chooseInRow('Group (2) - block 1 - Product code', 'CBF3612');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );
    expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('Product code');
    expect(screen.getByText('Previewing 1 of 2 blocks')).toBeInTheDocument();
  });

  it('names the product itself when the template has one block', async () => {
    render(<TagCanvasEditor doc={oneBlockDoc()} onChange={vi.fn()} />);

    openPreview();
    // One block is one question, so it keeps D41's single picker.
    expect(await screen.findByText('Preview this template with')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /CBF3612/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));

    await waitFor(() =>
      expect(
        screen.getByText('Previewing: CBF3612 - Carysil Big Bowl Sink'),
      ).toBeInTheDocument(),
    );
  });

  it('writes nothing it previewed into the document Save sends', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={onChange} />);

    openPreview();
    await screen.findByText('Preview with products');
    await chooseInRow('Group (2) - block 1 - Product code', 'CBF3612');
    await chooseInRow('Group (2) - block 2 - Product code', 'SRT2201');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    const saved = onChange.mock.calls[0][0] as TagTemplateDoc;
    for (const layer of saved.layers) {
      if (layer.props.kind === 'group') expect(layer.props.binding).toEqual({});
      expect(layer.text_override).toBeNull();
    }
  });

  it('clears every block from the chip', async () => {
    render(<TagCanvasEditor doc={twoBlockDoc()} onChange={vi.fn()} />);

    openPreview();
    await screen.findByText('Preview with products');
    await chooseInRow('Group (2) - block 1 - Product code', 'CBF3612');
    await chooseInRow('Group (2) - block 2 - Product code', 'SRT2201');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('CBF3612'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Stop previewing' }));

    await waitFor(() =>
      expect(screen.getByTestId('layer-main-code')).toHaveTextContent('Product code'),
    );
    expect(screen.getByTestId('layer-alt-a-code')).toHaveTextContent('Product code');
  });
});
