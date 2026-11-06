/**
 * DESIGNER-RICH-TEXT: a text layer whose OWN content carries per-run formatting draws those runs
 * through the one renderer (`layerRichBlocks`) on canvas and through `TagSheetRenderer` on print.
 *
 *  - A value substituted into a token inherits that token's marks.
 *  - A rich DATA token (`{{product.price_tag_description}}` / `{{combo.description}}`) inside a
 *    formatted layer is spliced in as the data's own blocks; the data keeps every mark it carries
 *    and the token's marks act only as the default for unmarked data text (crew ruling (a), 6 Nov).
 *  - Plain content renders exactly as before.
 *
 * Written test-FIRST: today a rich data token inside rich layer text is flattened to plain text,
 * `layerText` returns markup for a rich layer, and the Layers panel names it by its markup.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagBindingData, TagLayer } from './tag-template-types';
import { layerDisplayName, layerRichBlocks, layerText } from './product-block';
import type { RichRun } from './rich-text';
import { richTextLayer, tagSheetDocWith } from './rich-text.e1.fixture';

const TAG = 'tag-1';
const GREY = '#6b7280';
const RED = '#ff0000';

function line(over: Record<string, unknown> = {}): ResolvedLineData {
  return {
    tag_id: TAG,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'SRTBF11416',
    name: 'Cabinet',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: null,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    parts: [],
    specs: [{ key: 'width', label: 'Width', value: '400', unit: 'mm' }],
    price_tag_description: `<p><span style="color: ${GREY}">grey</span> plain</p><p>second <em>it</em></p>`,
    ...over,
  } as unknown as ResolvedLineData;
}

const binding = (l: ResolvedLineData) => ({ kind: 'line', line: l }) as unknown as TagBindingData;

type Run = { text: string; bold: boolean; italic: boolean; color: string | null };
const shape = (run: RichRun): Run => ({
  text: run.text,
  bold: !!run.bold,
  italic: !!run.italic,
  color: run.color ?? null,
});

function canvasBlocks(text: string, l = line()) {
  const blocks = layerRichBlocks(richTextLayer(text), binding(l), 'print');
  return (blocks ?? []).map((b) => b.runs.filter((r) => r.text !== '').map(shape));
}

type Printed = { text: string; bold: boolean; italic: boolean; color: string };
function printed(text: string, l = line()): Printed[] {
  const doc = tagSheetDocWith(richTextLayer(text));
  (doc.sheets[0].tags[0] as { request_tag_id: string | null }).request_tag_id = TAG;
  const { container } = render(<TagSheetRenderer doc={doc} resolvedData={{ [TAG]: l }} />);
  return Array.from(container.querySelectorAll<HTMLElement>('span'))
    .filter((s) => s.childElementCount === 0 && (s.textContent ?? '').trim() !== '')
    .map((s) => ({
      text: s.textContent!.trim(),
      bold: s.style.fontWeight === 'bold' || Number(s.style.fontWeight) >= 600,
      italic: s.style.fontStyle === 'italic',
      color: s.style.color,
    }));
}

describe('token values inherit the token marks', () => {
  const HTML = '<p><strong>{{product.code}}</strong></p><p>W: <span style="color: #ff0000">{{spec.width}}</span></p>';

  it('canvas: the code run is bold, the width value red, the label plain', () => {
    expect(canvasBlocks(HTML)).toEqual([
      [{ text: 'SRTBF11416', bold: true, italic: false, color: null }],
      [
        { text: 'W: ', bold: false, italic: false, color: null },
        { text: expect.stringContaining('400'), bold: false, italic: false, color: RED },
      ],
    ]);
  });

  it('print draws the same runs', () => {
    const spans = printed(HTML);
    expect(spans.find((s) => s.text === 'SRTBF11416')).toMatchObject({ bold: true });
    expect(spans.find((s) => s.text === 'W:')).toMatchObject({ bold: false });
    expect(spans.find((s) => s.text.includes('400'))).toMatchObject({ color: 'rgb(255, 0, 0)', bold: false });
  });
});

describe('a rich data token inside formatted layer text (union, data marks win)', () => {
  it('a bold token: the description keeps its colour and italics and is bold throughout', () => {
    expect(canvasBlocks('<p><strong>{{product.price_tag_description}}</strong></p>')).toEqual([
      [
        { text: 'grey', bold: true, italic: false, color: GREY },
        { text: ' plain', bold: true, italic: false, color: null },
      ],
      [
        { text: 'second ', bold: true, italic: false, color: null },
        { text: 'it', bold: true, italic: true, color: null },
      ],
    ]);
  });

  it('a red token: unmarked description text is red, the product-page grey wins', () => {
    const blocks = canvasBlocks(`<p><span style="color: ${RED}">{{product.price_tag_description}}</span></p>`);
    expect(blocks[0]).toEqual([
      { text: 'grey', bold: false, italic: false, color: GREY },
      { text: ' plain', bold: false, italic: false, color: RED },
    ]);
  });

  it('text around the token stays in the first and last description paragraphs', () => {
    const blocks = canvasBlocks('<p><strong>A </strong>{{product.price_tag_description}} Z</p>');
    expect(blocks.map((b) => b.map((r) => r.text).join(''))).toEqual(['A grey plain', 'second it Z']);
    expect(blocks[0][0]).toEqual({ text: 'A ', bold: true, italic: false, color: null });
  });

  it('print draws the same description runs', () => {
    const spans = printed('<p><strong>{{product.price_tag_description}}</strong></p>');
    expect(spans.find((s) => s.text === 'grey')).toMatchObject({ bold: true, color: 'rgb(107, 114, 128)' });
    expect(spans.find((s) => s.text === 'it')).toMatchObject({ bold: true, italic: true });
    expect(spans.some((s) => s.text.includes('<'))).toBe(false);
  });
});

describe('back-compatible: plain content and plain readers', () => {
  it('plain content with plain tokens takes the plain path as before', () => {
    expect(layerRichBlocks(richTextLayer('Code {{product.code}}'), binding(line()), 'print')).toBeNull();
    expect(layerText(richTextLayer('Code {{product.code}}'), binding(line()), 'print')).toBe('Code SRTBF11416');
  });

  it('layerText of a formatted layer is its resolved text, one line per paragraph, no markup', () => {
    const text = layerText(
      richTextLayer('<p><strong>{{product.code}}</strong></p><p>LP: x</p>'),
      binding(line()),
      'print',
    );
    expect(text).toBe('SRTBF11416\nLP: x');
  });

  it('the Layers panel names a formatted layer by its text, not its markup', () => {
    const name = layerDisplayName(richTextLayer('<p><strong>{{product.code}}</strong> big</p>'));
    expect(name).not.toContain('<');
    expect(name.startsWith('{{product.code}} big')).toBe(true);
  });
});
