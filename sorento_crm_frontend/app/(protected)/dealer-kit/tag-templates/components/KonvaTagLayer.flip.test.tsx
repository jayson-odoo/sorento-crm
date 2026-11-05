/**
 * PRICETAG-DESIGNER-GAPS item 1: a flipped image layer draws mirrored on the
 * canvas, in place inside its own box; an unflipped one draws exactly as before.
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
      scaleX?: number;
      scaleY?: number;
    }) {
      return (
        <div
          data-konva={name}
          data-x={props.x ?? ''}
          data-y={props.y ?? ''}
          data-scale-x={props.scaleX ?? ''}
          data-scale-y={props.scaleY ?? ''}
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

beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

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
    width_mm: 60,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'image', source: null, fit: 'contain', maskShape: 'none', ...props },
  } as TagLayer;
}

function groups(container: HTMLElement) {
  return Array.from(container.querySelectorAll('[data-konva="group"]')) as HTMLElement[];
}

describe('KonvaTagLayer image flip', () => {
  it('adds no mirror group when the layer is not flipped', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={imageLayer()} scale={1} display={{ imageUrl: 'https://cdn.test/tap.png' }} />,
    );
    expect(groups(container)).toHaveLength(1);
  });

  it('mirrors left-right about the box for flipX', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ flipX: true })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/tap.png' }}
      />,
    );
    const mirror = groups(container).find((g) => g.getAttribute('data-scale-x') === '-1');
    expect(mirror).toBeDefined();
    expect(mirror!.getAttribute('data-x')).toBe('60');
    expect(mirror!.getAttribute('data-scale-y')).toBe('1');
    // The picture itself sits inside the mirror group.
    expect(mirror!.querySelector('[data-konva="image"]')).not.toBeNull();
  });

  it('mirrors top-bottom for flipY', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={imageLayer({ flipY: true })}
        scale={1}
        display={{ imageUrl: 'https://cdn.test/tap.png' }}
      />,
    );
    const mirror = groups(container).find((g) => g.getAttribute('data-scale-y') === '-1');
    expect(mirror).toBeDefined();
    expect(mirror!.getAttribute('data-y')).toBe('20');
  });
});
