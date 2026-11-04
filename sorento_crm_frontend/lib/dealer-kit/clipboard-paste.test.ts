import { describe, expect, it } from 'vitest';

import type { TagLayer } from './tag-template-types';
import { defaultShapeProps, defaultTextProps } from './tag-template-types';

import {
  PASTE_IMAGE_MAX_BYTES,
  TAG_LAYERS_MIME,
  classifyPaste,
  copiedLayersText,
  fitPastedImage,
  pastedImageProblem,
  type PasteData,
} from './clipboard-paste';

function data(opts: {
  types?: Record<string, string>;
  files?: File[];
}): PasteData {
  const types = opts.types ?? {};
  const files = opts.files ?? [];
  return {
    types: [...Object.keys(types), ...(files.length ? ['Files'] : [])],
    getData: (type: string) => types[type] ?? '',
    files,
  };
}

const png = (bytes = 10) =>
  new File([new Uint8Array(bytes)], 'image.png', { type: 'image/png' });

describe('classifyPaste', () => {
  it('reads the editor own copy marker as an in-editor layer paste, ahead of anything else', () => {
    const intent = classifyPaste(
      data({
        types: { [TAG_LAYERS_MIME]: 'doc', 'text/plain': 'Hello' },
        files: [png()],
      }),
      'Hello',
    );
    expect(intent).toEqual({ kind: 'layers' });
  });

  it('ignores the marker when this tab holds no copied layers (reload, other tab) and uses the text', () => {
    expect(
      classifyPaste(
        data({ types: { [TAG_LAYERS_MIME]: 'doc', 'text/plain': 'Hello' } }),
        null,
      ),
    ).toEqual({ kind: 'text', text: 'Hello' });
  });

  it('text equal to the copied layers words is the copied layers (no-copy-event fallback)', () => {
    expect(
      classifyPaste(
        data({ types: { 'text/plain': 'Promo\r\nNow' } }),
        'Promo\nNow',
      ),
    ).toEqual({
      kind: 'layers',
    });
  });

  it('an image file on the clipboard is an image paste', () => {
    const file = png();
    expect(
      classifyPaste(data({ files: [file], types: { 'text/plain': '' } }), ''),
    ).toEqual({
      kind: 'image',
      file,
    });
  });

  it('an image copied from a web page (HTML holding an img) stays an image', () => {
    const file = png();
    expect(
      classifyPaste(
        data({
          files: [file],
          types: {
            'text/html': '<meta charset="utf-8"><img src="https://x/y.png">',
            'text/plain': 'https://x/y.png',
          },
        }),
        null,
      ),
    ).toEqual({ kind: 'image', file });
  });

  it('cells copied from Excel or Word (RTF or HTML without img, plus a picture) paste as text', () => {
    expect(
      classifyPaste(
        data({
          files: [png()],
          types: { 'text/rtf': '{\\rtf1}', 'text/plain': 'Sale' },
        }),
        null,
      ),
    ).toEqual({ kind: 'text', text: 'Sale' });
    expect(
      classifyPaste(
        data({
          files: [png()],
          types: {
            'text/html': '<table><td>Sale</td></table>',
            'text/plain': 'Sale',
          },
        }),
        null,
      ),
    ).toEqual({ kind: 'text', text: 'Sale' });
  });

  it('skips a non-image file and falls through to text', () => {
    const pdf = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    expect(
      classifyPaste(
        data({ files: [pdf], types: { 'text/plain': 'hi' } }),
        null,
      ),
    ).toEqual({
      kind: 'text',
      text: 'hi',
    });
  });

  it('plain text from another app is a text paste, even when the editor holds copied layers', () => {
    expect(
      classifyPaste(
        data({ types: { 'text/plain': 'Sale 20%' } }),
        'Other words',
      ),
    ).toEqual({
      kind: 'text',
      text: 'Sale 20%',
    });
  });

  it('whitespace-only text with copied layers pastes the layers', () => {
    expect(classifyPaste(data({ types: { 'text/plain': '   ' } }), '')).toEqual(
      {
        kind: 'layers',
      },
    );
  });

  it('an empty clipboard and nothing copied is nothing', () => {
    expect(classifyPaste(data({}), null)).toEqual({ kind: 'none' });
    expect(classifyPaste(null, null)).toEqual({ kind: 'none' });
    expect(classifyPaste(null, '')).toEqual({ kind: 'layers' });
  });

  it('normalises Windows line endings in pasted text', () => {
    expect(
      classifyPaste(data({ types: { 'text/plain': 'a\r\nb' } }), null),
    ).toEqual({
      kind: 'text',
      text: 'a\nb',
    });
  });
});

describe('copiedLayersText', () => {
  it('joins the text layers words, skipping other layers', () => {
    const text = (id: string, t: string) =>
      ({
        id,
        props: { ...defaultTextProps(), text: t },
      }) as unknown as TagLayer;
    const shape = {
      id: 's',
      props: defaultShapeProps(),
    } as unknown as TagLayer;
    expect(
      copiedLayersText([text('a', 'Promo'), shape, text('b', 'Now')]),
    ).toBe('Promo\nNow');
    expect(copiedLayersText([shape])).toBe('');
  });
});

describe('pastedImageProblem', () => {
  it('accepts the same types the image tool accepts', () => {
    for (const type of [
      'image/png',
      'image/jpeg',
      'image/webp',
      'image/svg+xml',
    ]) {
      expect(pastedImageProblem(new File(['x'], 'f', { type }))).toBeNull();
    }
  });

  it('refuses another image type', () => {
    expect(
      pastedImageProblem(new File(['x'], 'f.gif', { type: 'image/gif' })),
    ).toMatch(/PNG/);
  });

  it('refuses a file over 20 MB, the image tool cap', () => {
    expect(PASTE_IMAGE_MAX_BYTES).toBe(20 * 1024 * 1024);
    const big = png();
    Object.defineProperty(big, 'size', { value: PASTE_IMAGE_MAX_BYTES + 1 });
    expect(pastedImageProblem(big)).toMatch(/20 MB/);
  });
});

describe('fitPastedImage', () => {
  it('keeps a small image at 96 dpi, centred', () => {
    // 96 px = 25.4 mm
    const box = fitPastedImage(
      { width: 96, height: 48 },
      { width_mm: 100, height_mm: 60 },
    );
    expect(box.width_mm).toBeCloseTo(25.4);
    expect(box.height_mm).toBeCloseTo(12.7);
    expect(box.x_mm).toBeCloseTo((100 - 25.4) / 2);
    expect(box.y_mm).toBeCloseTo((60 - 12.7) / 2);
  });

  it('scales a large screenshot down to fit inside the canvas, aspect kept', () => {
    const box = fitPastedImage(
      { width: 1920, height: 1080 },
      { width_mm: 100, height_mm: 150 },
    );
    expect(box.width_mm).toBeCloseTo(100);
    expect(box.height_mm).toBeCloseTo(56.25);
    expect(box.x_mm).toBeCloseTo(0);
    expect(box.y_mm).toBeCloseTo((150 - 56.25) / 2);
  });

  it('a tall image is bounded by the canvas height', () => {
    const box = fitPastedImage(
      { width: 1000, height: 4000 },
      { width_mm: 100, height_mm: 100 },
    );
    expect(box.height_mm).toBeCloseTo(100);
    expect(box.width_mm).toBeCloseTo(25);
  });

  it('falls back to a 40 x 30 mm box when the size could not be read', () => {
    const box = fitPastedImage(null, { width_mm: 100, height_mm: 100 });
    expect(box).toEqual({ x_mm: 30, y_mm: 35, width_mm: 40, height_mm: 30 });
  });
});
