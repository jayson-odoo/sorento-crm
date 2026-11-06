/**
 * PRICETAG-ACCESSORIES crew pass 2 (6 Nov): the editor canvas (and the request designer, which draws
 * through this same layer) draws the box exactly as `accessoryBoxLayout` lays it out - the function
 * the print page uses - so canvas = request designer = print. The header shrinks to fit and is never
 * cut with an ellipsis.
 */
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-x={String(props.x ?? 0)}
          data-y={String(props.y ?? 0)}
          data-w={String(props.width ?? '')}
          data-h={String(props.height ?? '')}
          data-text={String(props.text ?? '')}
          data-size={String(props.fontSize ?? '')}
          data-ellipsis={props.ellipsis ? 'yes' : ''}
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

import {
  ACCESSORY_DEFAULT_BOX_MM,
  accessoryBoxLayout,
  accessoryLineCount,
  ptToMm,
} from '@/lib/dealer-kit/accessory-box';
import { defaultAccessoriesProps, type TagAccessory, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

class StubImage {
  width = 100;
  height = 100;
  onload: (() => void) | null = null;
  set src(_v: string) {
    Promise.resolve().then(() => this.onload?.());
  }
}

beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

const SCALE = 4;
const LIST: TagAccessory[] = [
  { kind: 'accessory', id: 'a1', name: 'CHOPPING BOARD', spec: null, image: null },
  { kind: 'accessory', id: 'a2', name: 'COLANDER', spec: '390x300x140, Depth: 160mm', image: null },
  { kind: 'product', id: 'p1', name: 'Popup Waste 80mm (w/o Overflow) Brass', spec: null, image: null, code: 'SRTW5000', list_price: 68 },
];

function layer(width_mm: number, height_mm: number, over = {}): TagLayer {
  return {
    id: 'acc',
    type: 'accessories',
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
    props: { ...defaultAccessoriesProps(), ...over },
  } as TagLayer;
}

async function draw(l: TagLayer, accessories?: TagAccessory[]) {
  const result = render(<KonvaTagLayer layer={l} scale={SCALE} display={accessories ? { accessories } : {}} />);
  await act(async () => {
    await Promise.resolve();
  });
  return result.container;
}

describe('canvas draws the shared layout', () => {
  it('frame, header size and card order match accessoryBoxLayout (what print draws)', async () => {
    const { width_mm, height_mm } = ACCESSORY_DEFAULT_BOX_MM;
    const l = layer(width_mm, height_mm);
    const box = accessoryBoxLayout(3, defaultAccessoriesProps(), width_mm, height_mm, accessoryLineCount(LIST));
    expect(box.shown).toBe(3);
    const c = await draw(l, LIST);
    const rects = [...c.querySelectorAll('[data-konva="rect"]')];
    const frame = rects.find((r) => r.getAttribute('data-w') === String(box.frame!.width_mm * SCALE));
    expect(frame).toBeDefined();
    expect(Number(frame!.getAttribute('data-h'))).toBeCloseTo(box.frame!.height_mm * SCALE);
    const texts = [...c.querySelectorAll('[data-konva="text"]')].map((t) => t.getAttribute('data-text'));
    expect(texts.indexOf('CHOPPING BOARD')).toBeLessThan(texts.indexOf('COLANDER'));
    expect(texts.indexOf('COLANDER')).toBeLessThan(texts.indexOf('SRTW5000'));
    expect(texts).toContain('LP: RM 68');
  });

  it('the header shrinks to the layout size at 45 mm and is never cut with an ellipsis', async () => {
    const l = layer(45, 60);
    const box = accessoryBoxLayout(1, defaultAccessoriesProps(), 45, 60, 2);
    const c = await draw(l, [LIST[0]]);
    const header = [...c.querySelectorAll('[data-konva="text"]')].find(
      (t) => t.getAttribute('data-text') === 'ACCESSORIES INCLUDED',
    )!;
    expect(header.getAttribute('data-ellipsis')).toBe('');
    expect(Number(header.getAttribute('data-size'))).toBeCloseTo(ptToMm(box.header!.fontSize_pt) * SCALE);
    expect(box.header!.fontSize_pt).toBeLessThan(defaultAccessoriesProps().headerFontSize);
  });

  it('an empty list draws only the dashed outline on the canvas', async () => {
    const c = await draw(layer(60, 60), []);
    expect(c.querySelector('[data-dash="dashed"]')).not.toBeNull();
    expect([...c.querySelectorAll('[data-konva="text"]')].map((t) => t.getAttribute('data-text'))).toEqual([
      'Accessories',
    ]);
  });
});
