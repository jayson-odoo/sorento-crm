/**
 * The read-only version viewer (D16, AC-S5-8), and the crash it was blamed
 * for (#726).
 *
 * Versions > View on the newest version took the whole route down with
 * `InvalidStateError: Failed to execute 'drawImage' on
 * 'CanvasRenderingContext2D': ... is a canvas element with a width or height
 * of 0`. A Konva stage sizes its BUFFER canvas from its own width/height, and
 * a stage measured at 0 gives Konva a 0x0 canvas to `drawImage` from the
 * moment any shape composites through that buffer.
 *
 * The viewer was NOT where that happened - it has always refused to render a
 * Stage until its container measures (the throw came from the template
 * editor, which the page keeps mounted and merely `hidden` behind the viewer;
 * pinned in `TagCanvasEditor.clip.test.tsx`). This file holds the viewer's
 * own half of that contract so it cannot drift into the same trap: no
 * measurement, no Stage; measured, a Stage with real dimensions that draws
 * the version's layers.
 *
 * Konva does not run in jsdom, so react-konva is stood in for by divs and
 * `KonvaTagLayer` is left REAL - an image layer is the shape that actually
 * reaches `drawImage`, so it is the one worth drawing here.
 */

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultImageProps, defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: {
      children?: React.ReactNode;
      width?: number;
      height?: number;
    }) {
      return (
        <div
          data-konva={name}
          data-width={props.width ?? ''}
          data-height={props.height ?? ''}
        >
          {props.children}
        </div>
      );
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Path: passthrough('path'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
  };
});

vi.mock('./useTagBindings', () => ({
  useKitLibrary: () => ({
    assetUrls: { 'asset-1': 'https://cdn.example.com/tag.png' },
    fonts: [],
    specKeys: [],
    fontOptions: [],
    reload: vi.fn(async () => {}),
    remember: vi.fn(),
  }),
}));

import { TagVersionViewer } from './TagVersionViewer';

/** Loads at a real size on the next microtask, same idiom as
 *  `KonvaTagLayer.image.test.tsx`. */
class StubImage {
  width = 300;
  height = 150;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = '';
  set src(value: string) {
    this._src = value;
    Promise.resolve().then(() => this.onload?.());
  }
  get src() {
    return this._src;
  }
}

/** jsdom lays nothing out, so a container's size is whatever this says. */
function stubContainerSize(width: number, height: number) {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get: () => width,
  });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get: () => height,
  });
}

function versionDoc(): TagTemplateDoc {
  const image: TagLayer = {
    id: 'img-1',
    type: 'image',
    x_mm: 2,
    y_mm: 2,
    width_mm: 40,
    height_mm: 30,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultImageProps(), assetId: 'asset-1' },
  };
  const text: TagLayer = {
    id: 'text-1',
    type: 'text',
    x_mm: 2,
    y_mm: 34,
    width_mm: 40,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 2,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: 'Bathroom Furniture' },
  };
  return { width_mm: 60, height_mm: 40, layers: [image, text] };
}

function renderViewer() {
  return render(
    <TagVersionViewer
      doc={versionDoc()}
      versionNo={4}
      onBackToDraft={vi.fn()}
      onRestore={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

afterEach(() => {
  stubContainerSize(0, 0);
  vi.unstubAllGlobals();
});

describe('TagVersionViewer stage sizing (#726)', () => {
  it('draws no Stage at all while its container measures 0, and does not throw', async () => {
    stubContainerSize(0, 0);

    const { container } = renderViewer();
    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector('[data-konva="stage"]')).toBeNull();
    // The read-only banner is still up, so the user sees the version rather
    // than a blank route: it is only the canvas that waits to be measured.
    expect(container.textContent).toContain('Viewing v4 - read-only');
  });

  it('draws the version once measured, at real dimensions, with the image layer on it', async () => {
    stubContainerSize(900, 600);

    const { container } = renderViewer();
    await act(async () => {
      await Promise.resolve();
    });

    const stage = container.querySelector('[data-konva="stage"]');
    expect(stage).not.toBeNull();
    expect(Number(stage!.getAttribute('data-width'))).toBeGreaterThan(0);
    expect(Number(stage!.getAttribute('data-height'))).toBeGreaterThan(0);

    // The image layer reached the canvas as a real Konva image, not the
    // "Fetching image" placeholder `ImageContent` falls back to for a 0x0
    // source (#723).
    expect(container.querySelector('[data-konva="image"]')).not.toBeNull();
    expect(container.textContent).not.toContain('Fetching image');
  });
});
