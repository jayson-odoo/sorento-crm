/**
 * Colour math behind the spectrum picker (S3, D6). Written before the
 * picker: the square and hue bar are just this math painted, so the math
 * has to round-trip and `tagColours` has to agree with the definition in
 * AC-S3-5 before either gets a pixel on screen.
 */
import { describe, expect, it } from 'vitest';

import { hexToHsv, hsvToHex, normaliseHex, tagColours } from './colour';
import type { TagLayer } from './tag-template-types';

describe('normaliseHex', () => {
  it('expands a 3-digit hex to 6 digits, upper-cased', () => {
    expect(normaliseHex('#f00')).toBe('#FF0000');
    expect(normaliseHex('#0af')).toBe('#00AAFF');
  });

  it('upper-cases a 6-digit hex without changing its digits', () => {
    expect(normaliseHex('#b44d2e')).toBe('#B44D2E');
  });

  it('leaves a non-hex value alone', () => {
    expect(normaliseHex('transparent')).toBe('transparent');
    expect(normaliseHex('#ff')).toBe('#ff');
  });
});

describe('hexToHsv / hsvToHex round-trip', () => {
  const cases = [
    '#FF0000',
    '#00FF00',
    '#0000FF',
    '#00FFFF',
    '#FF00FF',
    '#FFFF00',
    '#000000',
    '#FFFFFF',
    '#808080',
  ];

  it.each(cases)('round-trips %s through hsv and back', (hex) => {
    expect(hsvToHex(hexToHsv(hex))).toBe(hex);
  });

  it('reads pure red as hue 0, full saturation, full value', () => {
    expect(hexToHsv('#FF0000')).toEqual({ h: 0, s: 100, v: 100 });
  });

  it('reads black as zero saturation and value regardless of hue', () => {
    const hsv = hexToHsv('#000000');
    expect(hsv.s).toBe(0);
    expect(hsv.v).toBe(0);
  });

  it('a 3-digit hex converts the same as its 6-digit expansion', () => {
    expect(hexToHsv('#f00')).toEqual(hexToHsv('#FF0000'));
  });

  it('an invalid hex reads as black, same as the picker fallback', () => {
    expect(hexToHsv('transparent')).toEqual({ h: 0, s: 0, v: 0 });
  });
});

// ---------------------------------------------------------------------------
// tagColours
// ---------------------------------------------------------------------------

function textLayer(id: string, color: string): TagLayer {
  return {
    id,
    type: 'text',
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
    props: {
      kind: 'text',
      text: 'Hello',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color,
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
    },
  } as TagLayer;
}

function shapeLayer(id: string, fill: string, stroke: string): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'shape', shape: 'rect', fill, stroke, strokeWidth: 1, cornerRadius: 0 },
  } as TagLayer;
}

function priceBadgeLayer(id: string, fill: string, textColor: string): TagLayer {
  return {
    id,
    type: 'price_badge',
    x_mm: 0,
    y_mm: 0,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'price_badge',
      variant: 'promo',
      fill,
      textColor,
      cornerRadius: 2,
      showNett: true,
    },
  } as TagLayer;
}

describe('tagColours', () => {
  it('collects colours from text, shape and price-badge layers', () => {
    const layers = [
      textLayer('t1', '#000000'),
      shapeLayer('s1', '#FF0000', '#999999'),
      priceBadgeLayer('p1', '#D32F2F', '#FFFFFF'),
    ];
    const colours = tagColours(layers);
    expect(colours).toEqual(
      expect.arrayContaining(['#000000', '#FF0000', '#999999', '#D32F2F', '#FFFFFF']),
    );
  });

  it('dedupes, ordering the most-used colour first', () => {
    const layers = [
      textLayer('t1', '#000000'),
      textLayer('t2', '#000000'),
      shapeLayer('s1', '#FF0000', '#000000'),
    ];
    const colours = tagColours(layers);
    expect(colours[0]).toBe('#000000');
    expect(colours).toContain('#FF0000');
    expect(colours.filter((c) => c === '#000000')).toHaveLength(1);
  });

  it('normalises a 3-digit hex before deduping against its 6-digit twin', () => {
    const layers = [textLayer('t1', '#f00'), textLayer('t2', '#FF0000')];
    const colours = tagColours(layers);
    expect(colours).toEqual(['#FF0000']);
  });

  it('drops transparent - a shape with no stroke is not a colour to reuse', () => {
    const layers = [shapeLayer('s1', '#FF0000', 'transparent')];
    expect(tagColours(layers)).toEqual(['#FF0000']);
  });

  it('caps the list at 16 colours', () => {
    const layers = Array.from({ length: 20 }, (_, i) =>
      textLayer(`t${i}`, `#${i.toString(16).padStart(2, '0')}0000`),
    );
    expect(tagColours(layers)).toHaveLength(16);
  });

  it('ignores layer kinds with no colour prop, like images and barcodes', () => {
    const layers = [
      {
        id: 'img1',
        type: 'image',
        x_mm: 0,
        y_mm: 0,
        width_mm: 10,
        height_mm: 10,
        rotation_deg: 0,
        z_index: 1,
        locked: false,
        visible: true,
        slot_binding: null,
        text_override: null,
        props: { kind: 'image', fit: 'cover' },
      } as unknown as TagLayer,
    ];
    expect(tagColours(layers)).toEqual([]);
  });
});
