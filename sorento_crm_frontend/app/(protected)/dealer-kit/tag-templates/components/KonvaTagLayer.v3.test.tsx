/**
 * SPEC-SHEET-PARITY-B2 v3 editor, on the shared CANVAS (`KonvaTagLayer`, both designers).
 * Written test-FIRST.
 *
 * - AC-C4.1: a table with `headerRow: true` draws row 1 bold on a light shade (the cell's own fill
 *   wins); other rows are plain.
 * - AC-C5.2: `uppercase: true` on a table or a text layer draws capitals; the stored text is not
 *   changed (the layer handed in keeps its case).
 * - AC-C8.1: an image whose download FAILS shows "Image not available"; one still loading shows
 *   "Fetching image"; a loaded one draws the picture.
 *
 * `react-konva` is stood in for by divs carrying the props that matter, as in
 * `KonvaTagLayer.text-lines.test.tsx`.
 */
import { act, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-text={String(props.text ?? '')}
          data-font-style={String(props.fontStyle ?? '')}
          data-fill={String(props.fill ?? '')}
          data-x={String(props.x ?? '')}
          data-y={String(props.y ?? '')}
          data-width={String(props.width ?? '')}
          data-height={String(props.height ?? '')}
        >
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
    Path: passthrough('path'),
  };
});

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

const side = { color: '#000000', width_mm: 0.2 };
const cell = (text: string, more: Record<string, unknown> = {}) => ({
  text,
  padding_mm: 1,
  border: { top: side, right: side, bottom: side, left: side },
  ...more,
});

function tableLayer(extra: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'tbl',
    type: 'table',
    x_mm: 0,
    y_mm: 0,
    width_mm: 60,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'table',
      columns: [{ width_mm: 30 }, { width_mm: 30 }],
      rows: [{ height_mm: 6 }, { height_mm: 6 }],
      cells: [
        [cell('Ref'), cell('Value', { fill: '#ff0000' })],
        [cell('Code'), cell('Mixed case')],
      ],
      fontFamily: 'DM Sans',
      fontSize: 10,
      color: '#000000',
      align: 'left',
      verticalAlign: 'middle',
      ...extra,
    },
  } as unknown as TagLayer;
}

function textLayer(extra: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'title',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 120,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Wall hung',
      fontFamily: 'DM Sans',
      fontSize: 10,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
      ...extra,
    },
  } as unknown as TagLayer;
}

const texts = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLElement>('[data-konva="text"]'));
const textNode = (container: HTMLElement, needle: string) =>
  texts(container).find((n) => (n.getAttribute('data-text') ?? '').toLowerCase().includes(needle.toLowerCase()));
const isBold = (node: HTMLElement | undefined) => /bold/.test(node?.getAttribute('data-font-style') ?? '');

describe('canvas: Header row (AC-C4.1)', () => {
  it('row 1 text is bold, row 2 is not', () => {
    const { container } = render(<KonvaTagLayer layer={tableLayer({ headerRow: true })} scale={1} />);
    expect(isBold(textNode(container, 'Ref'))).toBe(true);
    expect(isBold(textNode(container, 'Value'))).toBe(true);
    expect(isBold(textNode(container, 'Code'))).toBe(false);
  });

  it('row 1 gets a light shade behind the cell with no fill; the own fill (red) stays', () => {
    const plain = render(<KonvaTagLayer layer={tableLayer()} scale={1} />);
    const plainFills = Array.from(plain.container.querySelectorAll('[data-konva="rect"]'))
      .map((r) => (r.getAttribute('data-fill') ?? '').toLowerCase())
      .filter((f) => f && f !== 'rgba(0,0,0,0.001)');
    plain.unmount();

    const { container } = render(<KonvaTagLayer layer={tableLayer({ headerRow: true })} scale={1} />);
    const fills = Array.from(container.querySelectorAll('[data-konva="rect"]'))
      .map((r) => (r.getAttribute('data-fill') ?? '').toLowerCase())
      .filter((f) => f && f !== 'rgba(0,0,0,0.001)');
    // One more filled rect: the shade behind header cell 0,0; the red own fill is kept, not shaded over.
    expect(fills.length).toBe(plainFills.length + 1);
    expect(fills).toContain('#ff0000');
  });

  it('without headerRow row 1 is plain', () => {
    const { container } = render(<KonvaTagLayer layer={tableLayer()} scale={1} />);
    expect(isBold(textNode(container, 'Ref'))).toBe(false);
  });
});

describe('canvas: ALL CAPS (AC-C5.2)', () => {
  it('a table with uppercase draws capitals and keeps the stored text', () => {
    const layer = tableLayer({ uppercase: true });
    const { container } = render(<KonvaTagLayer layer={layer} scale={1} />);
    expect(texts(container).map((n) => n.getAttribute('data-text'))).toContain('MIXED CASE');
    expect((layer.props as unknown as { cells: { text: string }[][] }).cells[1][1].text).toBe('Mixed case');
  });

  it('a text layer with uppercase draws capitals', () => {
    const { container } = render(<KonvaTagLayer layer={textLayer({ uppercase: true })} scale={1} />);
    const all = texts(container).map((n) => n.getAttribute('data-text') ?? '').join('\n');
    expect(all).toContain('WALL HUNG');
    expect(all).not.toContain('Wall hung');
  });

  it('a text layer without uppercase keeps its case', () => {
    const { container } = render(<KonvaTagLayer layer={textLayer()} scale={1} />);
    const all = texts(container).map((n) => n.getAttribute('data-text') ?? '').join('\n');
    expect(all).toContain('Wall hung');
  });
});

// ---------------------------------------------------------------------------
// AC-C8.1: a picture that cannot load.
// ---------------------------------------------------------------------------

type Outcome = 'load' | 'error' | 'never';
let outcome: Outcome = 'load';

class StubImage {
  width = 300;
  height = 150;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = '';
  set src(value: string) {
    this._src = value;
    Promise.resolve().then(() => {
      if (outcome === 'load') this.onload?.();
      if (outcome === 'error') this.onerror?.();
    });
  }
  get src() {
    return this._src;
  }
}

function imageLayer(): TagLayer {
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
    props: { kind: 'image', source: null, fit: 'contain', maskShape: 'none' },
  } as TagLayer;
}

async function renderImage(result: Outcome) {
  outcome = result;
  vi.stubGlobal('Image', StubImage);
  const view = render(
    <KonvaTagLayer layer={imageLayer()} scale={1} display={{ imageUrl: 'https://cdn.test/cover.png' }} />,
  );
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  return view;
}

describe('canvas: a picture that cannot load (AC-C8.1)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a failed download shows "Image not available", not "Fetching image"', async () => {
    const { container } = await renderImage('error');
    const shown = texts(container).map((n) => n.getAttribute('data-text'));
    expect(shown).toContain('Image not available');
    expect(shown).not.toContain('Fetching image');
  });

  it('a picture still loading shows "Fetching image"', async () => {
    const { container } = await renderImage('never');
    expect(texts(container).map((n) => n.getAttribute('data-text'))).toContain('Fetching image');
  });

  it('a loaded picture draws, with no placeholder text', async () => {
    const { container } = await renderImage('load');
    expect(container.querySelector('[data-konva="image"]')).not.toBeNull();
    const shown = texts(container).map((n) => n.getAttribute('data-text'));
    expect(shown).not.toContain('Fetching image');
    expect(shown).not.toContain('Image not available');
  });
});
