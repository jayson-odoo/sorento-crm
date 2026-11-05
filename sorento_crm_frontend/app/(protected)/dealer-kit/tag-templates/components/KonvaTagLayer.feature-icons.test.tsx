/**
 * PRICETAG-DESIGNER-GAPS item 3: a feature_icons layer draws one picture per matched icon in a
 * packed row (featureIconRow), and a dashed "Feature icons" outline when nothing matches.
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
      text?: string;
      dash?: number[];
    }) {
      return (
        <div
          data-konva={name}
          data-x={props.x ?? 0}
          data-y={props.y ?? 0}
          data-text={props.text ?? ''}
          data-dash={props.dash ? 'dashed' : ''}
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

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

// Square pictures, so a "contain" fit adds no offset inside the icon box.
class StubImage {
  width = 100;
  height = 100;
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

function iconsLayer(props: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'fi',
    type: 'feature_icons',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 2, align: 'left', order: [], ...props },
  } as unknown as TagLayer;
}

/** Absolute x/y of a node: the sum of its own and every ancestor's offset. */
function absolute(node: HTMLElement, root: HTMLElement) {
  let x = 0;
  let y = 0;
  let cur: HTMLElement | null = node;
  while (cur && cur !== root) {
    x += Number(cur.getAttribute('data-x') ?? 0);
    y += Number(cur.getAttribute('data-y') ?? 0);
    cur = cur.parentElement;
  }
  return { x, y };
}

const images = (c: HTMLElement) => Array.from(c.querySelectorAll('[data-konva="image"]')) as HTMLElement[];

describe('KonvaTagLayer feature icons', () => {
  it('draws one image per icon at the packed row positions', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={iconsLayer()}
        scale={2}
        display={{
          icons: [
            { id: 'cold', url: 'https://cdn.test/cold.png' },
            { id: 'hot', url: 'https://cdn.test/hot.png' },
            { id: 'sus', url: 'https://cdn.test/sus.png' },
          ],
        }}
      />,
    );
    const found = images(container);
    expect(found).toHaveLength(3);
    // 8mm icons, 2mm gap, scale 2 px/mm: x = 0, 20, 40 px; vertically centred (10-8)/2 = 1mm = 2px.
    const spots = found.map((n) => absolute(n, container));
    expect(spots.map((s) => s.x)).toEqual([0, 20, 40]);
    spots.forEach((s) => expect(s.y).toBe(2));
  });

  it('right-aligns the row inside the box', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer
        layer={iconsLayer({ align: 'right' })}
        scale={1}
        display={{
          icons: [
            { id: 'cold', url: 'https://cdn.test/cold.png' },
            { id: 'hot', url: 'https://cdn.test/hot.png' },
          ],
        }}
      />,
    );
    // total 18mm in a 40mm box: starts at 22.
    expect(images(container).map((n) => absolute(n, container).x)).toEqual([22, 32]);
  });

  it('draws a dashed placeholder labelled "Feature icons" when no icon matches', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer()} scale={1} display={{ icons: [] }} />,
    );
    expect(images(container)).toHaveLength(0);
    expect(container.querySelector('[data-dash="dashed"]')).not.toBeNull();
    const labels = Array.from(container.querySelectorAll('[data-konva="text"]')).map((n) =>
      n.getAttribute('data-text'),
    );
    expect(labels).toContain('Feature icons');
  });

  it('draws the placeholder when there is no display at all', async () => {
    const { container } = await renderLoaded(<KonvaTagLayer layer={iconsLayer()} scale={1} />);
    const labels = Array.from(container.querySelectorAll('[data-konva="text"]')).map((n) =>
      n.getAttribute('data-text'),
    );
    expect(labels).toContain('Feature icons');
  });
});
