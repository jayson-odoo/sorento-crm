/**
 * Padding on text and price badge layers (S3, AC-S3-1/2/3/4).
 *
 * The Konva canvas and `TagSheetRenderer` (`TagSheetRenderer.padding.test.tsx`)
 * both have to inset by the SAME box, which is what `paddedBox` in
 * `text-reflow.ts` pins once - this file is the wiring proof that
 * `KonvaTagLayer` actually calls it, the same idiom
 * `KonvaTagLayer.price-badge.test.tsx` uses for the callout.
 */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: {
      children?: React.ReactNode;
      text?: string;
      x?: number;
      y?: number;
      width?: number;
      height?: number;
      data?: string;
      fill?: string;
    }) {
      return (
        <div
          data-konva={name}
          data-text={props.text ?? ''}
          data-x={props.x ?? ''}
          data-y={props.y ?? ''}
          data-w={props.width ?? ''}
          data-h={props.height ?? ''}
          data-path={props.data ?? ''}
          data-fill={props.fill ?? ''}
        >
          {props.text}
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

import type {
  PriceBadgeLayerProps,
  TagLayer,
  TextLayerProps,
} from '@/lib/dealer-kit/tag-template-types';
import { defaultPriceBadgeProps, defaultTextProps } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

function textLayer(props: Partial<TextLayerProps> = {}): TagLayer {
  return {
    id: 't1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), ...props },
  } as TagLayer;
}

function badgeLayer(props: Partial<PriceBadgeLayerProps> = {}): TagLayer {
  return {
    id: 'pb1',
    type: 'price_badge',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultPriceBadgeProps('list_only'), ...props },
  } as TagLayer;
}

function nodes(container: HTMLElement, kind: string) {
  return Array.from(container.querySelectorAll(`[data-konva="${kind}"]`));
}

function only(container: HTMLElement, kind: string) {
  const [node] = nodes(container, kind);
  if (!node) throw new Error(`no ${kind} drawn`);
  return node;
}

describe('KonvaTagLayer text padding (S3, AC-S3-1/3/4)', () => {
  it('draws the Text at the layer box with no inset when padding is absent (AC-S3-3)', () => {
    const { container } = render(<KonvaTagLayer layer={textLayer()} scale={3} />);
    const text = only(container, 'text');
    expect(text.getAttribute('data-x')).toBe('0');
    expect(text.getAttribute('data-y')).toBe('0');
    expect(text.getAttribute('data-w')).toBe('120');
    expect(text.getAttribute('data-h')).toBe('60');
  });

  it('insets the Text node by the padding, converted mm to px (AC-S3-1)', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={textLayer({ padding: { top: 2, right: 4, bottom: 6, left: 8 } })}
        scale={3}
      />,
    );
    const text = only(container, 'text');
    // 2/4/6/8mm at 3px/mm is 6/12/18/24px.
    expect(text.getAttribute('data-x')).toBe('24');
    expect(text.getAttribute('data-y')).toBe('6');
    expect(text.getAttribute('data-w')).toBe(String(120 - 24 - 12));
    expect(text.getAttribute('data-h')).toBe(String(60 - 6 - 18));
  });

  it('clamps to a zero text area rather than a negative one (AC-S3-4)', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={textLayer({ padding: { top: 0, right: 0, bottom: 0, left: 50 } })}
        scale={3}
      />,
    );
    expect(only(container, 'text').getAttribute('data-w')).toBe('0');
  });
});

describe('KonvaTagLayer price badge padding (S3, AC-S3-2)', () => {
  it('leaves the badge exactly as it was when padding is absent (AC-S3-3)', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({ showBox: true, cornerRadius: 0 })}
        scale={3}
        display={{ price: { listPrice: 1599, offerPrice: 599 } }}
      />,
    );

    expect(only(container, 'path').getAttribute('data-path')).toBe(
      'M 0 0 L 120 0 L 120 60 L 0 60 Z',
    );
  });

  it('insets the whole badge - the figure AND, boxed, the callout itself (AC-S3-2)', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({
          showBox: true,
          cornerRadius: 0,
          padding: { top: 0, right: 0, bottom: 0, left: 10 },
        })}
        scale={3}
        display={{ price: { listPrice: 1599, offerPrice: 599 } }}
      />,
    );

    // The layer's own Group is the outer one (index 0); the padding inset
    // wraps the badge content in a second Group, shifted right by 10mm at
    // scale 3 = 30px.
    const insetGroup = nodes(container, 'group')[1];
    expect(insetGroup.getAttribute('data-x')).toBe('30');

    // The callout is drawn INSIDE that inset Group, at the smaller box the
    // Group leaves it - 40mm less the 10mm pad is 30mm, 90px at scale 3.
    expect(only(container, 'path').getAttribute('data-path')).toBe(
      'M 0 0 L 90 0 L 90 60 L 0 60 Z',
    );
  });
});
