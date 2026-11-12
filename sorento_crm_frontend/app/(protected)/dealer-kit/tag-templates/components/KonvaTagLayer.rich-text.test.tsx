/**
 * PRICETAG-COMBO-FORMAT AC-16: the canvas draws a rich description as one Konva Text per RUN, in
 * the run's face, colour and decoration; a heading run is the layer size times its factor. The
 * font family and base size are the layer's.
 *
 * Written test-FIRST. Today the whole HTML string is handed to a single Text node.
 * `react-konva` is stood in for by a div carrying the props that matter, as in
 * `KonvaTagLayer.text-lines.test.tsx`.
 */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const standIn = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-text={String(props.text ?? '')}
          data-font-size={String(props.fontSize ?? '')}
          data-font-style={String(props.fontStyle ?? '')}
          data-font-family={String(props.fontFamily ?? '')}
          data-fill={String(props.fill ?? '')}
          data-decoration={String(props.textDecoration ?? '')}
        >
          {props.children}
        </div>
      );
    };
  return {
    Group: standIn('group'),
    Rect: standIn('rect'),
    Text: standIn('text'),
    Image: standIn('image'),
    Ellipse: standIn('ellipse'),
    Line: standIn('line'),
    Path: standIn('path'),
  };
});

import {
  E1_BOLD_WORDS,
  E1_GREY,
  E1_HTML,
  richTextLayer,
} from '@/lib/dealer-kit/rich-text.e1.fixture';
import { KonvaTagLayer } from './KonvaTagLayer';

const SCALE = 3;
const isBold = (style: string) => /bold|\b[6-9]00\b/.test(style);

function textNodes(html: string, props = {}) {
  const { container } = render(<KonvaTagLayer layer={richTextLayer(html, {}, props)} scale={SCALE} />);
  return Array.from(container.querySelectorAll<HTMLElement>('[data-konva="text"]'));
}

describe('KonvaTagLayer rich text (AC-16)', () => {
  it('AC-16: E1 draws one Text node per run, never the markup', () => {
    const nodes = textNodes(E1_HTML);
    // 6 code lines x (bold code + grey part name) + 6 dimension lines; the space between is blank.
    const runCount = 6 * 2 + 6;
    const drawn = nodes.filter((node) => node.dataset.text!.trim() !== '');

    expect(drawn).toHaveLength(runCount);
    expect(nodes.some((node) => node.dataset.text!.includes('<'))).toBe(false);
  });

  it('AC-16: the six bold words are drawn bold, the dimensions in the grey fill', () => {
    const nodes = textNodes(E1_HTML);
    for (const word of E1_BOLD_WORDS) {
      const node = nodes.find((n) => n.dataset.text!.trim() === word);
      expect(node, word).toBeDefined();
      expect(isBold(node!.dataset.fontStyle!), word).toBe(true);
    }
    const dimension = nodes.find((n) => n.dataset.text!.trim() === 'L400xW345xH390mm');
    expect(dimension!.dataset.fill).toBe(E1_GREY);
    const regular = nodes.find((n) => n.dataset.text!.trim() === '(CABINET)');
    expect(isBold(regular!.dataset.fontStyle!)).toBe(false);
  });

  it('AC-16: family and base size are the layer\'s, not the description\'s', () => {
    const nodes = textNodes(E1_HTML);
    const bold = nodes.find((n) => n.dataset.text!.trim() === 'SRTBF11416')!;
    expect(bold.dataset.fontFamily).toBe('DM Sans');
    expect(parseFloat(bold.dataset.fontSize!)).toBeCloseTo(10 * 0.35 * SCALE, 6);
  });

  it('AC-16: a run without a colour keeps the layer colour', () => {
    const nodes = textNodes('<p>plain</p>', { color: '#123456' });
    expect(nodes.find((n) => n.dataset.text!.trim() === 'plain')!.dataset.fill).toBe('#123456');
  });

  it('AC-16: an h1 run is the layer size times 1.4, bold', () => {
    const nodes = textNodes('<h1>Title</h1>');
    const title = nodes.find((n) => n.dataset.text!.trim() === 'Title')!;
    expect(parseFloat(title.dataset.fontSize!)).toBeCloseTo(10 * 0.35 * SCALE * 1.4, 6);
    expect(isBold(title.dataset.fontStyle!)).toBe(true);
  });

  it('AC-16: underline and strike become text decoration on that run only', () => {
    const nodes = textNodes('<p><u>under</u> <s>gone</s> same</p>');
    const by = (text: string) => nodes.find((n) => n.dataset.text!.trim() === text)!;
    expect(by('under').dataset.decoration).toContain('underline');
    expect(by('gone').dataset.decoration).toContain('line-through');
    expect(by('same').dataset.decoration ?? '').toBe('');
  });
});
