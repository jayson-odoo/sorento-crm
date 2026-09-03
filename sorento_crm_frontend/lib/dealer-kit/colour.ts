/**
 * Pure colour math behind the spectrum picker (S3, D6): hex <-> HSV so a
 * saturation/value square and a hue bar can drive the same hex a designer
 * types, and a helper that reads back what colours are already on the
 * current tag so "This tag" doesn't need a colour list of its own.
 */
import type { TagLayer } from './tag-template-types';

export interface Hsv {
  /** 0-360. */
  h: number;
  /** 0-100. */
  s: number;
  /** 0-100. */
  v: number;
}

const HEX3 = /^#([0-9a-fA-F]{3})$/;
const HEX6 = /^#([0-9a-fA-F]{6})$/;

/**
 * `#rgb` -> `#RRGGBB`; a 6-digit hex is only uppercased. Anything else
 * (including `transparent`, or a half-typed box) is returned unchanged so a
 * caller can tell "not a hex" from "a hex I normalised".
 */
export function normaliseHex(input: string): string {
  const trimmed = input.trim();
  const three = HEX3.exec(trimmed);
  if (three) {
    const [r, g, b] = three[1].split('');
    return `#${r}${r}${g}${g}${b}${b}`.toUpperCase();
  }
  if (HEX6.test(trimmed)) return trimmed.toUpperCase();
  return trimmed;
}

/** An invalid or non-hex value (e.g. `transparent`) reads as black, same as the old native-input fallback. */
function toRgb(hex: string): { r: number; g: number; b: number } {
  const normalised = normaliseHex(hex);
  const clean = HEX6.test(normalised) ? normalised : '#000000';
  return {
    r: parseInt(clean.slice(1, 3), 16),
    g: parseInt(clean.slice(3, 5), 16),
    b: parseInt(clean.slice(5, 7), 16),
  };
}

export function hexToHsv(hex: string): Hsv {
  const { r, g, b } = toRgb(hex);
  const rN = r / 255;
  const gN = g / 255;
  const bN = b / 255;
  const max = Math.max(rN, gN, bN);
  const min = Math.min(rN, gN, bN);
  const d = max - min;

  let h = 0;
  if (d !== 0) {
    if (max === rN) h = ((gN - bN) / d) % 6;
    else if (max === gN) h = (bN - rN) / d + 2;
    else h = (rN - gN) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }

  const s = max === 0 ? 0 : d / max;
  return { h: Math.round(h), s: Math.round(s * 100), v: Math.round(max * 100) };
}

export function hsvToHex({ h, s, v }: Hsv): string {
  const sN = s / 100;
  const vN = v / 100;
  const c = vN * sN;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = vN - c;

  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];

  const toByte = (n: number) =>
    Math.round((n + m) * 255)
      .toString(16)
      .padStart(2, '0')
      .toUpperCase();
  return `#${toByte(r)}${toByte(g)}${toByte(b)}`;
}

/**
 * The colours already on this tag (AC-S3-5): text colour, shape fill/stroke,
 * price-badge fill/text. `transparent` is a shape's "no stroke", not a
 * colour anybody wants to reuse, so it is dropped rather than shown as a
 * swatch. Deduped by normalised hex, most-used first, capped at 16 - a tag
 * has a handful of colours in practice, so the cap only ever bites on a
 * pathological document.
 */
export function tagColours(layers: TagLayer[]): string[] {
  const counts = new Map<string, number>();

  const record = (raw: string | undefined) => {
    if (!raw || raw === 'transparent') return;
    const hex = normaliseHex(raw);
    if (!HEX6.test(hex)) return;
    counts.set(hex, (counts.get(hex) ?? 0) + 1);
  };

  for (const layer of layers) {
    if (layer.props.kind === 'text') {
      record(layer.props.color);
    } else if (layer.props.kind === 'shape') {
      record(layer.props.fill);
      record(layer.props.stroke);
    } else if (layer.props.kind === 'price_badge') {
      record(layer.props.fill);
      record(layer.props.textColor);
    }
  }

  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 16)
    .map(([hex]) => hex);
}
