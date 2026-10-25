/**
 * The barcode label as ONE SVG (PRICETAG-BARCODE-MATCH).
 *
 * The canvas, the request preview and the printed PDF all draw this same SVG,
 * so what is pinned here is what every surface shows. The target is the
 * barcode artwork staff already use: product code above the bars in a black
 * serif with no box behind it, standard EAN-13 guard bars running down into
 * the digit row, large digits split 1 / 6 / 6 around the guards, white
 * background with quiet zones.
 *
 * The scan check decodes the SVG's own bars with an independent decoder
 * (`@zxing/library`), so "renders like a barcode" is never just "has rects".
 */
import { BitArray, Code128Reader, EAN13Reader } from '@zxing/library';
import { describe, expect, it } from 'vitest';

import { barcodeSvg, svgDataUrl } from './barcode';

// Synthetic, checksum-valid (the same value the other barcode tests use).
const VALID_EAN13 = '4006381333931';
const CODE = 'ZZT-6638-DIY';

const BLACK = new Set(['#000', '#000000', 'black']);
const WHITE = new Set(['#fff', '#ffffff', 'white']);

/** An attribute on the element or the nearest ancestor that carries it. */
function inherited(el: Element, name: string): string | null {
  let node: Element | null = el;
  while (node) {
    const value = node.getAttribute(name);
    if (value != null) return value;
    node = node.parentElement;
  }
  return null;
}

function num(el: Element, name: string): number {
  return parseFloat(el.getAttribute(name) ?? '0');
}

interface Bar {
  x: number;
  y: number;
  w: number;
  h: number;
}

function parse(svg: string) {
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const root = doc.documentElement;
  const [, , W, H] = (root.getAttribute('viewBox') ?? '').trim().split(/\s+/).map(Number);
  const rects = Array.from(root.querySelectorAll('rect')).map((r) => ({
    x: num(r, 'x'),
    y: num(r, 'y'),
    w: num(r, 'width'),
    h: num(r, 'height'),
    fill: (inherited(r, 'fill') ?? '').toLowerCase(),
  }));
  const bars: Bar[] = rects.filter((r) => BLACK.has(r.fill)).sort((a, b) => a.x - b.x);
  const texts = Array.from(root.querySelectorAll('text')).map((t) => ({
    text: t.textContent ?? '',
    x: num(t, 'x'),
    y: num(t, 'y'),
    fontSize: parseFloat(inherited(t, 'font-size') ?? '0'),
    fontFamily: inherited(t, 'font-family') ?? '',
    fill: (inherited(t, 'fill') ?? '').toLowerCase(),
    anchor: inherited(t, 'text-anchor'),
    textLength: t.getAttribute('textLength'),
  }));
  const top = Math.min(...bars.map((b) => b.y));
  const normalBottom = Math.min(...bars.map((b) => b.y + b.h));
  return { root, W, H, rects, bars, texts, top, normalBottom };
}

/**
 * One horizontal scanline through the bars, as the pixel row a scanner sees,
 * at `pxPerUnit` pixels per SVG unit (mm).
 */
function scanline(p: ReturnType<typeof parse>, pixels = 2000): BitArray {
  const y = (p.top + p.normalBottom) / 2;
  const row = new BitArray(pixels);
  for (let i = 0; i < pixels; i += 1) {
    const x = ((i + 0.5) / pixels) * p.W;
    if (p.bars.some((b) => x >= b.x && x < b.x + b.w && y >= b.y && y <= b.y + b.h)) {
      row.set(i);
    }
  }
  return row;
}

function decode(svg: string | null, reader: EAN13Reader | Code128Reader): string {
  expect(svg).not.toBeNull();
  return reader.decodeRow(0, scanline(parse(svg as string)), new Map()).getText();
}

function svgFor(
  value: string,
  opts: Partial<{ code: string | null; showCode: boolean; widthMm: number; heightMm: number }> = {},
): string {
  const svg = barcodeSvg({
    value,
    code: opts.code === undefined ? CODE : opts.code,
    showCode: opts.showCode ?? true,
    widthMm: opts.widthMm ?? 40,
    heightMm: opts.heightMm ?? 22,
  });
  expect(svg).not.toBeNull();
  return svg as string;
}

// ---------------------------------------------------------------------------
// Scan check
// ---------------------------------------------------------------------------

describe('barcodeSvg: the bars decode back to the value (scan check)', () => {
  it('an EAN-13 decodes to the same 13 digits', () => {
    expect(decode(svgFor(VALID_EAN13), new EAN13Reader())).toBe(VALID_EAN13);
  });

  it('decodes with the code row hidden, and in a squat or a tall box', () => {
    expect(decode(svgFor(VALID_EAN13, { showCode: false }), new EAN13Reader())).toBe(VALID_EAN13);
    expect(decode(svgFor(VALID_EAN13, { heightMm: 10 }), new EAN13Reader())).toBe(VALID_EAN13);
    expect(decode(svgFor(VALID_EAN13, { widthMm: 30, heightMm: 40 }), new EAN13Reader())).toBe(
      VALID_EAN13,
    );
  });

  it('a non-EAN value decodes as Code128', () => {
    expect(decode(svgFor('SKU-NOT-EAN'), new Code128Reader())).toBe('SKU-NOT-EAN');
  });

  it('12-digit, 8-digit and bad-checksum 13-digit values print as Code128, still scannable', () => {
    for (const value of ['400638133393', '96385074', '4006381333932']) {
      expect(decode(svgFor(value, { widthMm: 60 }), new Code128Reader())).toBe(value);
    }
  });
});

// ---------------------------------------------------------------------------
// Layout: the staff barcode
// ---------------------------------------------------------------------------

describe('barcodeSvg: EAN-13 layout matches the staff barcode', () => {
  const p = parse(svgFor(VALID_EAN13));
  const X = p.W / 113; // 11X left quiet zone + 95X symbol + 7X right quiet zone

  it('is sized in mm of the layer box, with a white background over the whole box', () => {
    expect(p.root.getAttribute('viewBox')?.trim()).toBe('0 0 40 22');
    expect(p.root.getAttribute('width')).toBe('40mm');
    expect(p.root.getAttribute('height')).toBe('22mm');
    expect(
      p.rects.some(
        (r) => WHITE.has(r.fill) && r.x === 0 && r.y === 0 && r.w === p.W && r.h === p.H,
      ),
    ).toBe(true);
  });

  it('prints the product code ABOVE the bars, centred, in black serif', () => {
    const code = p.texts.find((t) => t.text === CODE);
    expect(code).toBeDefined();
    expect(code!.y).toBeLessThan(p.top);
    expect(code!.y - code!.fontSize * 0.75).toBeGreaterThanOrEqual(0);
    expect(code!.anchor).toBe('middle');
    expect(code!.x).toBeCloseTo(p.W / 2, 2);
    expect(BLACK.has(code!.fill)).toBe(true);
    // A serif face (Times-like), never the old white bold sans.
    expect(code!.fontFamily).toMatch(/(^|,)\s*['"]?(serif|Times)/);
    expect(code!.fontFamily).not.toMatch(/sans-serif/);
  });

  it('has no black strip or box: every black rect is a bar, at most 4 modules wide', () => {
    for (const r of p.rects) {
      expect(WHITE.has(r.fill) || BLACK.has(r.fill)).toBe(true);
    }
    for (const bar of p.bars) {
      expect(bar.w).toBeLessThanOrEqual(4 * X + 1e-6);
    }
  });

  it('runs exactly the start, centre and end guard bars longer, down into the digit row', () => {
    const extended = p.bars.filter((b) => b.y + b.h > p.normalBottom + 1e-6);
    expect(extended).toHaveLength(6);
    const n = p.bars.length;
    expect(extended).toContain(p.bars[0]);
    expect(extended).toContain(p.bars[1]);
    expect(extended).toContain(p.bars[n - 2]);
    expect(extended).toContain(p.bars[n - 1]);
    const centre = 11 * X + 47.5 * X;
    expect(extended.filter((b) => Math.abs(b.x + b.w / 2 - centre) < 3 * X)).toHaveLength(2);
  });

  it('splits the digits 1 / 6 / 6 around the guards: first digit left of the start guard', () => {
    const digits = p.texts.filter((t) => /^\d$/.test(t.text)).sort((a, b) => a.x - b.x);
    expect(digits.map((d) => d.text).join('')).toBe(VALID_EAN13);

    const n = p.bars.length;
    const startGuardLeft = p.bars[0].x;
    const startGuardRight = p.bars[1].x + p.bars[1].w;
    const centreGuard = p.bars.filter((b) => Math.abs(b.x + b.w / 2 - (11 + 47.5) * X) < 3 * X);
    const centreLeft = Math.min(...centreGuard.map((b) => b.x));
    const centreRight = Math.max(...centreGuard.map((b) => b.x + b.w));
    const endGuardLeft = p.bars[n - 2].x;

    expect(digits[0].x).toBeLessThan(startGuardLeft);
    for (const d of digits.slice(1, 7)) {
      expect(d.x).toBeGreaterThan(startGuardRight);
      expect(d.x).toBeLessThan(centreLeft);
    }
    for (const d of digits.slice(7)) {
      expect(d.x).toBeGreaterThan(centreRight);
      expect(d.x).toBeLessThan(endGuardLeft);
    }
  });

  it('draws the digits LARGE, below the normal bars, and the guards reach into them', () => {
    const digits = p.texts.filter((t) => /^\d$/.test(t.text));
    const guardBottom = Math.max(...p.bars.map((b) => b.y + b.h));
    for (const d of digits) {
      // Fills its 7-module cell: at least 10 modules of font.
      expect(d.fontSize).toBeGreaterThanOrEqual(10 * X);
      expect(BLACK.has(d.fill)).toBe(true);
      // The digit's top sits under the normal bars, its baseline inside the box.
      expect(d.y - d.fontSize * 0.7).toBeGreaterThanOrEqual(p.normalBottom - 1e-6);
      expect(d.y).toBeLessThanOrEqual(p.H + 1e-6);
      // The guards end inside the digit row, not above it.
      expect(guardBottom).toBeGreaterThan(d.y - d.fontSize * 0.7);
    }
  });

  it('keeps the standard quiet zones: 11 modules left, 7 right', () => {
    const n = p.bars.length;
    expect(p.bars[0].x).toBeCloseTo(11 * X, 3);
    expect(p.bars[n - 1].x + p.bars[n - 1].w).toBeCloseTo(p.W - 7 * X, 3);
  });
});

describe('barcodeSvg: proportions', () => {
  it('scales uniformly: a box twice the size is the same drawing at twice the size', () => {
    const small = parse(svgFor(VALID_EAN13, { widthMm: 40, heightMm: 22 }));
    const big = parse(svgFor(VALID_EAN13, { widthMm: 80, heightMm: 44 }));
    expect(big.rects).toHaveLength(small.rects.length);
    big.rects.forEach((r, i) => {
      expect(r.x).toBeCloseTo(small.rects[i].x * 2, 2);
      expect(r.y).toBeCloseTo(small.rects[i].y * 2, 2);
      expect(r.w).toBeCloseTo(small.rects[i].w * 2, 2);
      expect(r.h).toBeCloseTo(small.rects[i].h * 2, 2);
    });
    big.texts.forEach((t, i) => {
      expect(t.x).toBeCloseTo(small.texts[i].x * 2, 2);
      expect(t.y).toBeCloseTo(small.texts[i].y * 2, 2);
      expect(t.fontSize).toBeCloseTo(small.texts[i].fontSize * 2, 2);
    });
  });

  it('keeps bars visible in a squat box: the digit size gives way to the height', () => {
    const p = parse(svgFor(VALID_EAN13, { widthMm: 40, heightMm: 10 }));
    expect(p.normalBottom - p.top).toBeGreaterThanOrEqual(0.3 * p.H);
  });

  it('compresses a code too long for the width instead of clipping it', () => {
    const long = 'ZZT-VERY-LONG-PRODUCT-CODE-0001';
    const p = parse(svgFor(VALID_EAN13, { code: long }));
    const code = p.texts.find((t) => t.text === long);
    expect(code?.textLength).not.toBeNull();
    expect(parseFloat(code!.textLength!)).toBeLessThanOrEqual(p.W);
  });

  it('drops the code row when show_code is off or there is no code; the bars take its place', () => {
    for (const svg of [
      svgFor(VALID_EAN13, { showCode: false }),
      svgFor(VALID_EAN13, { code: null }),
      svgFor(VALID_EAN13, { code: '' }),
    ]) {
      const p = parse(svg);
      expect(p.texts.some((t) => t.text === CODE)).toBe(false);
      expect(p.top).toBeLessThan(0.15 * p.H);
    }
  });
});

describe('barcodeSvg: Code128 layout', () => {
  it('prints the code above and the value centred under flat bars (no guards)', () => {
    const p = parse(svgFor('SKU-NOT-EAN', { widthMm: 60 }));
    const value = p.texts.find((t) => t.text === 'SKU-NOT-EAN');
    expect(value).toBeDefined();
    expect(value!.x).toBeCloseTo(p.W / 2, 2);
    expect(value!.y).toBeGreaterThan(p.normalBottom);
    expect(p.texts.find((t) => t.text === CODE)!.y).toBeLessThan(p.top);
    expect(new Set(p.bars.map((b) => (b.y + b.h).toFixed(3))).size).toBe(1);
  });
});

describe('barcodeSvg: nothing to draw', () => {
  it('is null for an empty value and for one Code128 cannot encode', () => {
    expect(barcodeSvg({ value: '', code: CODE, showCode: true, widthMm: 40, heightMm: 22 })).toBeNull();
    expect(barcodeSvg({ value: '   ', code: CODE, showCode: true, widthMm: 40, heightMm: 22 })).toBeNull();
    expect(barcodeSvg({ value: 'ä€', code: CODE, showCode: true, widthMm: 40, heightMm: 22 })).toBeNull();
  });
});

describe('svgDataUrl', () => {
  it('wraps the SVG as a data: URL that decodes back to the same markup', () => {
    const svg = svgFor(VALID_EAN13);
    const url = svgDataUrl(svg);
    expect(url).toMatch(/^data:image\/svg\+xml;charset=utf-8,/);
    expect(decodeURIComponent(url.slice(url.indexOf(',') + 1))).toBe(svg);
  });
});
