/**
 * PRICETAG-DESIGNER-FEEDBACK B2 on the canvas (KonvaTagLayer):
 * AC-7.6 the Spec icons box lays out with `featureIconGrid` (Columns / Rows, rows from the top, never
 * hide) and an overflow shows a visible warning on the canvas;
 * AC-8.3 icons named in `hiddenIconIds` are skipped and the rest close up.
 *
 * Harness copied from KonvaTagLayer.feature-icons.test.tsx (react-konva stand-ins carry x / y / text).
 * Written test-FIRST.
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

function iconsLayer(props: Record<string, unknown> = {}, width_mm = 40, height_mm = 10): TagLayer {
  return {
    id: 'fi',
    type: 'feature_icons',
    x_mm: 0,
    y_mm: 0,
    width_mm,
    height_mm,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 2, align: 'left', ...props },
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

const THREE = {
  icons: [
    { id: 'cold', url: 'https://cdn.test/cold.png' },
    { id: 'hot', url: 'https://cdn.test/hot.png' },
    { id: 'warm', url: 'https://cdn.test/warm.png' },
  ],
};

const spots = (c: HTMLElement) => images(c).map((n) => absolute(n, c));
const texts = (c: HTMLElement) =>
  Array.from(c.querySelectorAll('[data-konva="text"]')).map((n) => n.getAttribute('data-text') ?? '');

describe('KonvaTagLayer spec icons grid (AC-7.6)', () => {
  it('Columns 1 stacks the icons from the top', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer({ columns: 1 }, 40, 30)} scale={1} display={THREE} />,
    );
    const at = spots(container);
    expect(at.map((s) => s.x)).toEqual([0, 0, 0]);
    expect(at.map((s) => s.y)).toEqual([0, 10, 20]);
  });

  it('Rows 2 puts 2 icons on the first row and 1 on the second', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer({ rows: 2 }, 40, 30)} scale={2} display={THREE} />,
    );
    const at = spots(container);
    expect(at.map((s) => s.x)).toEqual([0, 20, 0]);
    expect(at.map((s) => s.y)).toEqual([0, 0, 20]);
  });

  it('never hides an icon that does not fit the width', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer({}, 15, 10)} scale={1} display={THREE} />,
    );
    expect(images(container)).toHaveLength(3);
  });

  it('a grid taller than its box shows a visible warning on the canvas', async () => {
    // 3 icons stacked in a 5 mm tall box: even at 4 mm they need 16 mm.
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer({ columns: 1 }, 40, 5)} scale={1} display={THREE} />,
    );
    expect(images(container)).toHaveLength(3);
    expect(texts(container).some((t) => /fit/i.test(t))).toBe(true);
  });

  it('no warning when the grid fits', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer({ columns: 1 }, 40, 30)} scale={1} display={THREE} />,
    );
    expect(texts(container).some((t) => /fit/i.test(t))).toBe(false);
  });
});

describe('KonvaTagLayer hidden spec icons (AC-8.3)', () => {
  it('skips a hidden icon and closes up the rest', async () => {
    const { container } = await renderLoaded(
      <KonvaTagLayer layer={iconsLayer({ hiddenIconIds: ['cold'] })} scale={1} display={THREE} />,
    );
    const found = images(container);
    expect(found).toHaveLength(2);
    expect(spots(container).map((s) => s.x)).toEqual([0, 10]);
  });
});
