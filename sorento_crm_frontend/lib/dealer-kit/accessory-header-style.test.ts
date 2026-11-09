/**
 * PRICETAG-HEADER-DRAG round 2 (owner 9 Nov ~17:00: "I can't further style it like its background,
 * resize it like a normal design component"). The header band can be resized (stored size; the text
 * wraps inside it at its set size), filled (colour or none), rounded and padded. No stored key = today's
 * look, pixel for pixel. All of it is box design, so a linked saved template carries it (Q5).
 */
import { describe, expect, it } from 'vitest';

import { accessoryChrome } from './accessory-box';
import { accessoryDesign, headerResetPatch } from './accessory-card';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from './tag-template-types';

const base = (extra: Partial<AccessoriesLayerProps> = {}): AccessoriesLayerProps =>
  ({ ...defaultAccessoriesProps(), headerText: 'FREE', ...extra }) as AccessoriesLayerProps;

describe('header style keys absent: today\'s look', () => {
  it('on the border: filled with the "behind the header" colour, no wrap, no padding, square', () => {
    const h = accessoryChrome(base({ headerOnBorder: true, headerBackground: '#fafafa' }), 50, 40).header!;
    expect(h.fill).toBe('#fafafa');
    expect(h.wrap).toBe(false);
    expect(h.radius_mm).toBe(0);
    expect(h.padding).toEqual({ top: 0, right: 0, bottom: 0, left: 0 });
  });

  it('inside the frame or moved: no fill', () => {
    expect(accessoryChrome(base({ headerOnBorder: false }), 50, 40).header!.fill).toBeNull();
    expect(accessoryChrome(base({ headerOnBorder: true, headerPos: { x_mm: 2, y_mm: 20 } }), 50, 40).header!.fill).toBeNull();
  });
});

describe('a resized header (position + size stored)', () => {
  const sized = base({
    headerOnBorder: true,
    headerPos: { x_mm: 4, y_mm: 10 },
    headerSize: { width_mm: 20, height_mm: 12 },
  });

  it('draws at its stored size and keeps its set font size (wraps, never shrinks)', () => {
    const h = accessoryChrome({ ...sized, headerText: 'ACCESSORIES INCLUDED FREE GIFT' }, 50, 40).header!;
    expect(h).toMatchObject({ x_mm: 4, y_mm: 10, width_mm: 20, height_mm: 12, moved: true, onBorder: false, wrap: true });
    expect(h.fontSize_pt).toBe(defaultAccessoriesProps().headerFontSize);
    expect(h.text).toEqual({ x_mm: 4, y_mm: 10, width_mm: 20, height_mm: 12 });
  });

  it('stays inside the box: pulled in, and never wider or taller than the box', () => {
    const h = accessoryChrome({ ...sized, headerPos: { x_mm: 45, y_mm: 35 } }, 50, 40).header!;
    expect(h.x_mm).toBe(30);
    expect(h.y_mm).toBe(28);
    const big = accessoryChrome({ ...sized, headerSize: { width_mm: 90, height_mm: 90 } }, 50, 40).header!;
    expect(big.width_mm).toBe(50);
    expect(big.height_mm).toBe(40);
    expect(big.x_mm).toBe(0);
  });
});

describe('background, corner radius, padding', () => {
  it('a set fill wins, also on an unmoved header; Transparent is none', () => {
    expect(accessoryChrome(base({ headerOnBorder: false, headerFill: '#1f4d36' }), 50, 40).header!.fill).toBe('#1f4d36');
    expect(accessoryChrome(base({ headerOnBorder: true, headerFill: 'transparent' }), 50, 40).header!.fill).toBeNull();
  });

  it('radius and padding come through as set', () => {
    const h = accessoryChrome(
      base({
        headerPos: { x_mm: 1, y_mm: 1 },
        headerSize: { width_mm: 20, height_mm: 8 },
        headerRadius_mm: 2,
        headerPadding: { top: 1, right: 2, bottom: 1, left: 2 },
      }),
      50,
      40,
    ).header!;
    expect(h.radius_mm).toBe(2);
    expect(h.padding).toEqual({ top: 1, right: 2, bottom: 1, left: 2 });
  });
});

describe('linked design and Reset', () => {
  it('size and style travel with the saved design (Q5)', () => {
    const d = accessoryDesign(
      base({ headerSize: { width_mm: 20, height_mm: 8 }, headerFill: '#000000', headerRadius_mm: 1, presetId: 'p' }),
    );
    expect(d.headerSize).toEqual({ width_mm: 20, height_mm: 8 });
    expect(d.headerFill).toBe('#000000');
    expect(d.headerRadius_mm).toBe(1);
  });

  it('Reset puts position, size and style back to the default look, keeping the text and show', () => {
    const defaults = defaultAccessoriesProps();
    const patch = headerResetPatch();
    const reset = {
      ...base({
        headerText: 'FREE',
        headerPos: { x_mm: 1, y_mm: 1 },
        headerSize: { width_mm: 9, height_mm: 9 },
        headerFill: '#000',
        headerRadius_mm: 3,
        headerPadding: { top: 1, right: 1, bottom: 1, left: 1 },
        headerFontSize: 20,
        headerColor: '#ff0000',
        headerOnBorder: false,
        headerStyle: { align: 'left', fontWeight: 400 },
      }),
      ...patch,
    } as AccessoriesLayerProps;
    expect(reset.headerText).toBe('FREE');
    expect(JSON.parse(JSON.stringify(reset)).headerPos).toBeUndefined();
    expect(reset.headerSize ?? null).toBeNull();
    expect(reset.headerFill ?? null).toBeNull();
    expect(reset.headerFontSize).toBe(defaults.headerFontSize);
    expect(reset.headerColor).toBe(defaults.headerColor);
    expect(reset.headerOnBorder).toBe(defaults.headerOnBorder);
    expect(reset.headerStyle ?? null).toEqual(defaults.headerStyle ?? null);
    expect(accessoryChrome(reset, 50, 40)).toEqual(accessoryChrome(base(), 50, 40));
  });
});
