/**
 * The price badge on the Konva canvas (r4b, AC-S6-1/2/4/5).
 *
 * `price-badge.test.ts` pins WHAT a badge is made of; this pins that the
 * canvas draws that composition - the callout as a `Path` from the same
 * builder a polygon shape uses, so the proof on screen and the PDF cannot
 * disagree about a slanted edge, and the figure set in whatever the layer's
 * own typography says.
 *
 * `react-konva`'s primitives are stood in for by divs carrying the props that
 * matter, the same pattern `KonvaTagLayer.barcode.test.tsx` uses: Konva needs
 * a real Stage and a layout engine, which jsdom has neither of.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: {
      children?: React.ReactNode;
      text?: string;
      data?: string;
      fill?: string;
      fontFamily?: string;
      fontSize?: number;
      fontStyle?: string;
      textDecoration?: string;
      align?: string;
    }) {
      return (
        <div
          data-konva={name}
          data-text={props.text ?? ''}
          data-path={props.data ?? ''}
          data-fill={props.fill ?? ''}
          data-font-family={props.fontFamily ?? ''}
          data-font-size={props.fontSize ?? ''}
          data-font-style={props.fontStyle ?? ''}
          data-decoration={props.textDecoration ?? ''}
          data-align={props.align ?? ''}
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

import type { PriceBadgeLayerProps, TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { defaultPriceBadgeProps } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

const PRICE = { listPrice: 1599, offerPrice: 599 };

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

function figure(container: HTMLElement) {
  const node = nodes(container, 'text').find((n) =>
    (n.getAttribute('data-text') ?? '').includes('RM'),
  );
  if (!node) throw new Error('no figure drawn');
  return node;
}

describe('KonvaTagLayer price badge box (AC-S6-1/2)', () => {
  it('draws no box for a badge saved before the flag (AC-S6-1)', () => {
    const { container } = render(
      <KonvaTagLayer layer={badgeLayer()} scale={3} display={{ price: PRICE }} />,
    );

    expect(nodes(container, 'path')).toHaveLength(0);
    expect(screen.getByText('RM 1,599')).toBeInTheDocument();
  });

  it('draws the callout as a Path in Box Fill once the layer asks for one', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({ showBox: true, fill: '#ffffff', cornerRadius: 0 })}
        scale={3}
        display={{ price: PRICE }}
      />,
    );

    const path = nodes(container, 'path');
    expect(path).toHaveLength(1);
    // 40mm x 20mm at scale 3 is 120 x 60 px: the box's own four corners.
    expect(path[0].getAttribute('data-path')).toBe('M 0 0 L 120 0 L 120 60 L 0 60 Z');
    expect(path[0].getAttribute('data-fill')).toBe('#ffffff');
    expect(screen.getByText('RM 1,599')).toBeInTheDocument();
  });

  it('follows the layer own corners, so the callout can slant (AC-S6-2)', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({
          showBox: true,
          cornerRadius: 0,
          points: [
            { x: 0.25, y: 0 },
            { x: 1, y: 0 },
            { x: 1, y: 1 },
            { x: 0, y: 1 },
          ],
        })}
        scale={3}
        display={{ price: PRICE }}
      />,
    );

    expect(nodes(container, 'path')[0].getAttribute('data-path')).toBe(
      'M 30 0 L 120 0 L 120 60 L 0 60 Z',
    );
  });

  it('leaves the promotional block on its rounded rectangle (AC-S6-3)', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({ variant: 'promo' })}
        scale={3}
        display={{ price: PRICE }}
      />,
    );

    expect(nodes(container, 'path')).toHaveLength(0);
    expect(screen.getByText('LP: RM 1,599')).toBeInTheDocument();
    expect(screen.getByText('RM 599')).toBeInTheDocument();
  });
});

describe('KonvaTagLayer price badge typography (AC-S6-4/5)', () => {
  it('sets the figure in the layer own face and size', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({
          fontFamily: 'Bebas Neue',
          fontSize: 20,
          italic: true,
          underline: true,
          align: 'left',
        })}
        scale={3}
        display={{ price: PRICE }}
      />,
    );

    const node = figure(container);
    expect(node.getAttribute('data-font-family')).toBe('Bebas Neue');
    // Points to canvas pixels, the same conversion a text layer uses.
    expect(node.getAttribute('data-font-size')).toBe(String(20 * 3 * 0.35));
    expect(node.getAttribute('data-font-style')).toBe('italic bold');
    expect(node.getAttribute('data-decoration')).toBe('underline');
    expect(node.getAttribute('data-align')).toBe('left');
  });

  it('keeps the box-derived size and centred bold face when the layer names none (AC-S6-5)', () => {
    const { container } = render(
      <KonvaTagLayer layer={badgeLayer()} scale={3} display={{ price: PRICE }} />,
    );

    const node = figure(container);
    expect(node.getAttribute('data-font-family')).toBe('');
    // min(h * 0.6, w / 6) on a 120 x 60 px box, exactly as before.
    expect(node.getAttribute('data-font-size')).toBe('20');
    expect(node.getAttribute('data-font-style')).toBe('bold');
    expect(node.getAttribute('data-decoration')).toBe('');
    expect(node.getAttribute('data-align')).toBe('center');
  });

  it('scales the promotional block SP and NETT with the figure', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={badgeLayer({ variant: 'promo', fontSize: 20 })}
        scale={3}
        display={{ price: PRICE }}
      />,
    );

    const big = 20 * 3 * 0.35;
    const amount = nodes(container, 'text').find(
      (n) => n.getAttribute('data-text') === 'RM 599',
    );
    expect(amount?.getAttribute('data-font-size')).toBe(String(big));
    const nett = nodes(container, 'text').find(
      (n) => n.getAttribute('data-text') === 'NETT',
    );
    expect(nett?.getAttribute('data-font-size')).toBe(String(Math.max(4, big * 0.56)));
  });
});
