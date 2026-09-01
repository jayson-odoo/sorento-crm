/**
 * Ruler guide click-vs-drag (D9/D17, S6, B2).
 *
 * The pure geometry (`guideCrossedIntoRuler`, `moveGuide`, `removeGuide`) is
 * pinned in `lib/dealer-kit/ruler-guides.test.ts`. The bug lived entirely in
 * how the WIRING read that geometry - no slop threshold on `moved`, and no
 * memory of whether the drag had ever actually left ruler territory - so
 * this pins the wiring: a click that jitters a pixel or two must not delete
 * the guide it just placed, and only a drag that genuinely LEAVES ruler
 * territory before coming back counts as "dragged back onto the ruler".
 *
 * Konva does not run in jsdom. `Line` is the one primitive this file needs to
 * see the props of - a ruler guide's own `stroke` colour is what tells it
 * apart from the transient snap guides, which is enough to count them without
 * reaching into the component's internals.
 */

import { fireEvent, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

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
    // A ruler guide's `stroke` is the one prop a component test can tell it
    // apart BY - it already differs from the snap guides in the real file
    // (`#0ea5e9` vs `#f43f5e`), and its own `onMouseDown` (an existing guide
    // picked back up) is wrapped to look like the Konva event the real
    // handler expects (`.evt`, a settable `.cancelBubble`).
    Line: (props: {
      stroke?: string;
      onMouseDown?: (e: { cancelBubble: boolean; evt: React.MouseEvent }) => void;
    }) => (
      <div
        data-konva="line"
        data-stroke={props.stroke}
        onMouseDown={(e) => props.onMouseDown?.({ cancelBubble: false, evt: e })}
      />
    ),
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

const RULER_GUIDE_STROKE = '#0ea5e9';

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

function ruleGuideCount(container: HTMLElement) {
  return container.querySelectorAll(`[data-stroke="${RULER_GUIDE_STROKE}"]`).length;
}

describe('TagCanvasEditor ruler guide click-vs-drag (B2, AC-S6-3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps a guide it just placed against a plain click, even with a pixel or two of jitter', () => {
    const { container } = render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);

    // The top ruler drops a VERTICAL guide (D17).
    const topRuler = container.querySelector('.cursor-col-resize') as HTMLElement;
    expect(topRuler).toBeTruthy();

    fireEvent.mouseDown(topRuler, { clientX: 100, clientY: 10 });
    expect(ruleGuideCount(container)).toBe(1);

    // A real click always wanders a pixel or two before the button releases -
    // well under the marquee's own slop (3px).
    fireEvent.mouseMove(window, { clientX: 101, clientY: 11, buttons: 1 });
    fireEvent.mouseUp(window, { clientX: 101, clientY: 11 });

    expect(ruleGuideCount(container)).toBe(1);
  });

  it('deletes a guide only once the drag has actually left ruler territory and come back', () => {
    const { container } = render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);

    const topRuler = container.querySelector('.cursor-col-resize') as HTMLElement;
    fireEvent.mouseDown(topRuler, { clientX: 100, clientY: 10 });
    expect(ruleGuideCount(container)).toBe(1);

    // Drag well past the slop, onto the artboard - genuinely leaves ruler
    // territory - then back onto the ruler, and release there.
    fireEvent.mouseMove(window, { clientX: 100, clientY: 100, buttons: 1 });
    fireEvent.mouseMove(window, { clientX: 100, clientY: 5, buttons: 1 });
    fireEvent.mouseUp(window, { clientX: 100, clientY: 5 });

    expect(ruleGuideCount(container)).toBe(0);
  });

  it('does not delete an existing guide dragged around the canvas without re-entering the ruler', () => {
    const { container } = render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);

    const topRuler = container.querySelector('.cursor-col-resize') as HTMLElement;
    fireEvent.mouseDown(topRuler, { clientX: 100, clientY: 10 });
    fireEvent.mouseMove(window, { clientX: 100, clientY: 100, buttons: 1 });
    fireEvent.mouseUp(window, { clientX: 100, clientY: 100 });
    expect(ruleGuideCount(container)).toBe(1);

    // Pick the placed guide back up off the canvas and move it - never
    // crosses back into ruler territory, so it must survive.
    const guideLine = container.querySelector(
      `[data-stroke="${RULER_GUIDE_STROKE}"]`,
    ) as HTMLElement;
    fireEvent.mouseDown(guideLine, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 100, clientY: 150, buttons: 1 });
    fireEvent.mouseUp(window, { clientX: 100, clientY: 150 });

    expect(ruleGuideCount(container)).toBe(1);
  });
});
