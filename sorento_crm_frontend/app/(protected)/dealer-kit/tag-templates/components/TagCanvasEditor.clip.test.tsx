/**
 * WYSIWYG after a shrink (S9 review S4): a layer dragged or resized past the
 * tag's own edge must be hidden on screen exactly the way `TagSheetRenderer`
 * clips it on the printed sheet (`overflow: hidden`), not still visible on a
 * canvas that quietly disagrees with what the PDF will show.
 *
 * Konva does not run in jsdom, so this pins the WIRING rather than a
 * rendered pixel: the layers sit inside a `Group` whose `clipFunc` draws the
 * exact same rectangle the white artboard background itself is drawn at
 * (`canvasWidthPx`/`canvasHeightPx`) - the one geometry the editor already
 * computes and the one this test can read off the background `Rect` without
 * having to reproduce the zoom/scale arithmetic itself.
 */

import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

const capturedRects: { name?: string; x?: number; y?: number; width?: number; height?: number }[] =
  [];
const capturedGroups: { clipFunc?: (ctx: { rect: (...args: number[]) => void }) => void }[] = [];

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: (props: {
      children?: React.ReactNode;
      clipFunc?: (ctx: { rect: (...args: number[]) => void }) => void;
    }) => {
      capturedGroups.push({ clipFunc: props.clipFunc });
      return <div data-konva="group">{props.children}</div>;
    },
    Rect: (props: {
      name?: string;
      x?: number;
      y?: number;
      width?: number;
      height?: number;
      children?: React.ReactNode;
    }) => {
      capturedRects.push(props);
      return <div data-konva="rect" data-name={props.name} />;
    },
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: () => null,
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

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

import { TagCanvasEditor } from './TagCanvasEditor';

function doc(): TagTemplateDoc {
  const layer: TagLayer = {
    id: 'text-1',
    type: 'text',
    x_mm: 5,
    y_mm: 5,
    width_mm: 20,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: 'Hello' },
  };
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

describe('TagCanvasEditor artboard clip (S9 review S4)', () => {
  it('clips the layers Group to exactly the artboard background rect', () => {
    capturedRects.length = 0;
    capturedGroups.length = 0;

    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);

    const artboardBg = capturedRects.filter((r) => r.name === 'artboard-bg').at(-1);
    expect(artboardBg).toBeDefined();
    expect(artboardBg!.width).toBeGreaterThan(0);
    expect(artboardBg!.height).toBeGreaterThan(0);

    // The layers Group's clipFunc draws the SAME rectangle the background is
    // drawn at - the artboard's own bounds, not some other guess at the
    // tag's size. (Re-renders after mount - e.g. the fit-to-view effect
    // measuring its container - can call the mocked component more than
    // once; the LAST render is what actually stayed on screen.)
    expect(capturedGroups.length).toBeGreaterThan(0);
    const clipFunc = capturedGroups[capturedGroups.length - 1].clipFunc;
    expect(clipFunc).toBeTypeOf('function');

    const rectCalls: number[][] = [];
    const ctx = { rect: (...args: number[]) => rectCalls.push(args) };
    clipFunc!(ctx);

    expect(rectCalls).toEqual([[0, 0, artboardBg!.width, artboardBg!.height]]);
  });
});
