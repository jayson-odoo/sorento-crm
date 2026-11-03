/**
 * A host (the spec sheet page editor) may hand the editor the artwork URLs to draw with. The
 * library lists every asset with its ORIGINAL url; for an asset the host supplied, the editor
 * must draw the host's rendition and never the library's original (owner rule: screens never
 * load full-size originals).
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ProductTagData, TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultImageProps } from '@/lib/dealer-kit/tag-template-types';

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
    Group: passthrough('group'),
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
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

const ORIGINAL = 'https://cdn.test/library/logo-original-7mb.png';
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => [
    { id: 'asset-logo', name: 'Logo', kind: 'logo', url: 'https://cdn.test/library/logo-original-7mb.png' },
  ]),
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

const doc = {
  width_mm: 100,
  height_mm: 60,
  layers: [
    {
      id: 'logo-layer',
      type: 'image',
      x_mm: 0,
      y_mm: 0,
      width_mm: 30,
      height_mm: 20,
      rotation_deg: 0,
      z_index: 1,
      locked: false,
      visible: true,
      slot_binding: null,
      text_override: null,
      props: {
        ...defaultImageProps(),
        source: { type: 'asset', assetId: 'asset-logo' },
      },
    },
  ] as TagLayer[],
} satisfies TagTemplateDoc;

describe('TagCanvasEditor host-supplied asset urls', () => {
  it('draws the host rendition, never the library original, for an asset the host supplied', async () => {
    render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        assetUrls={{ 'asset-logo': 'https://cdn.test/library/logo.medium.jpg' }}
      />,
    );

    await waitFor(() =>
      expect(screen.getByTestId('layer-logo-layer')).toHaveAttribute(
        'data-image',
        'https://cdn.test/library/logo.medium.jpg',
      ),
    );
    // Give the library list time to land; the layer must still not switch to the original.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId('layer-logo-layer')).not.toHaveAttribute('data-image', ORIGINAL);
  });

  it('without the prop the library url is used, as before', async () => {
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByTestId('layer-logo-layer')).toHaveAttribute('data-image', ORIGINAL),
    );
  });
});
