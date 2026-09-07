/**
 * Image layer fit modes on the Konva canvas (S3b, AC-1/2/5).
 *
 * `contain` and `cover` are pinned here too, alongside `stretch`, so a change
 * to one cannot quietly move the other two - all three share the same
 * draw-size branch in `ImageContent`.
 */
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: {
      children?: React.ReactNode;
      x?: number;
      y?: number;
      width?: number;
      height?: number;
      // Only `Image` carries this (S8) - captured generically so the crop
      // prop reaches a test without a second, image-only stand-in.
      crop?: { x: number; y: number; width: number; height: number };
    }) {
      return (
        <div
          data-konva={name}
          data-x={props.x ?? ''}
          data-y={props.y ?? ''}
          data-width={props.width ?? ''}
          data-height={props.height ?? ''}
          data-crop={props.crop ? JSON.stringify(props.crop) : ''}
        >
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Path: passthrough('path'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
  };
});

import type { ImageLayerProps, TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

/**
 * An `Image` that "loads" at a fixed, testable size.
 *
 * `useHtmlImage` sets `src` BEFORE it assigns `onload`, so firing on the
 * `src` setter itself would call a still-null handler - the load is
 * deferred to a microtask instead, by which time `onload` is assigned.
 */
class StubImage {
  static width = 300;
  static height = 150;
  width: number;
  height: number;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = '';

  constructor() {
    this.width = StubImage.width;
    this.height = StubImage.height;
  }

  set src(value: string) {
    this._src = value;
    Promise.resolve().then(() => this.onload?.());
  }

  get src() {
    return this._src;
  }
}

beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

/** Render, then flush the microtask the stub's "load" fires on. */
async function renderLoaded(ui: React.ReactElement) {
  const result = render(ui);
  await act(async () => {
    await Promise.resolve();
  });
  return result;
}

function imageLayer(props: Partial<ImageLayerProps> = {}): TagLayer {
  return {
    id: 'img1',
    type: 'image',
    x_mm: 0,
    y_mm: 0,
    // 60mm x 20mm at scale 1: box ratio 3.
    width_mm: 60,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'image',
      source: null,
      fit: 'contain',
      maskShape: 'none',
      ...props,
    },
  } as TagLayer;
}

function nodes(container: HTMLElement, kind: string) {
  return Array.from(container.querySelectorAll(`[data-konva="${kind}"]`));
}

describe('KonvaTagLayer image fit (S3b)', () => {
  it('stretch draws at the box own w x h from 0,0 with no clip group (AC-2)', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ fit: 'stretch' })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    const image = nodes(container, 'image')[0] as HTMLElement;
    expect(image.getAttribute('data-x')).toBe('0');
    expect(image.getAttribute('data-y')).toBe('0');
    expect(image.getAttribute('data-width')).toBe('60');
    expect(image.getAttribute('data-height')).toBe('20');

    // Only the mandatory outer per-layer Group - no extra clip Group, since
    // a stretched picture never overflows its box.
    expect(nodes(container, 'group')).toHaveLength(1);
  });

  it('still applies a circle mask under stretch (AC-2)', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ fit: 'stretch', maskShape: 'circle' })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    // The outer layer Group, plus the circle-clip Group.
    expect(nodes(container, 'group')).toHaveLength(2);
  });

  it('contain letterboxes exactly as before (AC-5)', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ fit: 'contain' })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    // ratio 2 < boxRatio 3, so contain is NOT wide: drawW = h*ratio = 40,
    // drawH = h = 20, centred horizontally.
    const image = nodes(container, 'image')[0] as HTMLElement;
    expect(image.getAttribute('data-width')).toBe('40');
    expect(image.getAttribute('data-height')).toBe('20');
    expect(image.getAttribute('data-x')).toBe('10');
    expect(image.getAttribute('data-y')).toBe('0');
    expect(nodes(container, 'group')).toHaveLength(1);
  });

  it('cover fills and crops exactly as before (AC-5)', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ fit: 'cover' })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    // ratio 2 < boxRatio 3, so cover IS wide: drawW = w = 60,
    // drawH = w/ratio = 30, centred vertically, and clipped.
    const image = nodes(container, 'image')[0] as HTMLElement;
    expect(image.getAttribute('data-width')).toBe('60');
    expect(image.getAttribute('data-height')).toBe('30');
    expect(image.getAttribute('data-x')).toBe('0');
    expect(image.getAttribute('data-y')).toBe('-5');
    // The outer layer Group, plus the cover-clip Group.
    expect(nodes(container, 'group')).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Crop (S8, PLAN D8, AC-S8-3/6): the `crop` prop Konva reads from is present
// when `cropRect` is set, and `fit` places the CROPPED region, not the
// whole picture.
// ---------------------------------------------------------------------------

describe('KonvaTagLayer image crop (S8)', () => {
  it('no cropRect: the crop covers the whole 300x150 source image (AC-S8-6)', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ fit: 'contain' })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    const image = nodes(container, 'image')[0] as HTMLElement;
    expect(JSON.parse(image.getAttribute('data-crop') || '{}')).toEqual({
      x: 0,
      y: 0,
      width: 300,
      height: 150,
    });
  });

  it('a cropRect resolves to the matching SOURCE-PIXEL crop (AC-S8-3)', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({
          fit: 'contain',
          cropRect: { x: 0.25, y: 0, width: 0.5, height: 1 },
        })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    const image = nodes(container, 'image')[0] as HTMLElement;
    expect(JSON.parse(image.getAttribute('data-crop') || '{}')).toEqual({
      x: 75,
      y: 0,
      width: 150,
      height: 150,
    });
  });

  it('fit computes its ratio from the CROPPED region, not the full image (AC-S8-3)', async () => {
    // Uncropped: 300x150 -> ratio 2, boxRatio (60/20) 3 -> not wide ->
    // drawW = h*ratio = 40 (pinned in the existing "contain" test above).
    // Cropped to a SQUARE region (150x150, ratio 1): still not wide against
    // boxRatio 3, but drawW is now h*1 = 20 - a different number that could
    // only come from the cropped ratio, not the source's own 2:1.
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({
          fit: 'contain',
          cropRect: { x: 0.25, y: 0, width: 0.5, height: 1 },
        })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/photo.png' }}
      />,
    );

    const image = nodes(container, 'image')[0] as HTMLElement;
    expect(image.getAttribute('data-width')).toBe('20');
    expect(image.getAttribute('data-height')).toBe('20');
  });
});
