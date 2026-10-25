/**
 * Text layer layout, shared by the Konva canvas and the print page
 * (PRICETAG-BARCODE-MATCH).
 *
 * The canvas used to let Konva wrap a text layer and the print page let the
 * browser wrap it, at a different font size (0.35 vs 0.3528 mm per pt), a
 * different letter-spacing unit (0.1 mm vs 1 px per unit), a different
 * fallback face and a different bold threshold - so one title broke at
 * different places on the two, and the print page's fixed-height box clipped
 * what the canvas still showed ("SRTWT914SS-GM-").
 *
 * Now `textLayerLines` breaks the lines ONCE, from the layer's own mm, and
 * both surfaces draw exactly those lines with their own wrapping turned off.
 * The rule is the one the canvas already used, Konva's word wrap, so a layout
 * a designer saw on the canvas is the one that prints.
 */

import type { TextLayerProps } from './tag-template-types';
import { paddedBox } from './text-reflow';

/** mm of type per point, on both surfaces. The canvas's own figure (every
 * saved design was laid out against it), not the exact 25.4/72. */
export const TEXT_MM_PER_PT = 0.35;
/** mm per unit of `letterSpacing`, on both surfaces (the canvas's figure). */
export const LETTER_SPACING_MM_PER_UNIT = 0.1;
export const DEFAULT_TEXT_FONT_FAMILY = 'DM Sans, sans-serif';
/** Lines are always broken at the print page's scale (CSS px per mm), never
 * at the canvas zoom, so every zoom and the PDF get the same lines. */
export const LAYOUT_PX_PER_MM = 96 / 25.4;
/** A line must fit with this share of the width to spare, so the canvas at
 * another zoom, or the browser setting a line, never finds it a hair too
 * wide and cuts it again. */
const FIT_HEADROOM = 0.005;
/** A line whose bottom lands within this share of the box's bottom still
 * fits: summed in floating point, three lines of 0.1 make 0.30000000000000004,
 * and a strict compare dropped the last line of a box exactly that tall. */
const HEIGHT_TOLERANCE = 1e-9;
/** Slack on the height the canvas hands Konva, far above `HEIGHT_TOLERANCE`
 * and far below a pixel, so Konva's own height cut (summed in canvas px at the
 * current zoom) never drops a line `wrapTextLines` kept. */
const CANVAS_HEIGHT_SLACK = 1e-6;

/** The height to give the canvas's Konva Text for a box `heightPx` tall. */
export function canvasTextHeight(heightPx: number): number {
  return heightPx * (1 + CANVAS_HEIGHT_SLACK);
}

type TextFaceProps = Pick<
  TextLayerProps,
  'fontFamily' | 'fontSize' | 'fontWeight' | 'italic' | 'letterSpacing'
>;

export interface TextFace {
  fontFamily: string;
  /** Style and weight, as Konva's `fontStyle` and a CSS font shorthand take
   * them: `'500'`, `'italic 700'`. */
  fontStyle: string;
  fontSize_mm: number;
  letterSpacing_mm: number;
}

export function textFace(props: TextFaceProps): TextFace {
  return {
    fontFamily: props.fontFamily || DEFAULT_TEXT_FONT_FAMILY,
    fontStyle: [props.italic ? 'italic' : '', String(props.fontWeight || 400)]
      .filter(Boolean)
      .join(' '),
    fontSize_mm: props.fontSize * TEXT_MM_PER_PT,
    letterSpacing_mm: (props.letterSpacing || 0) * LETTER_SPACING_MM_PER_UNIT,
  };
}

/** Konva's `normalizeFontFamily`: a family name with a space gets quoted. */
function quoteFamilies(family: string): string {
  return family
    .split(',')
    .map((name) => {
      const trimmed = name.trim();
      const quoted = trimmed.includes('"') || trimmed.includes("'");
      return trimmed.includes(' ') && !quoted ? `"${trimmed}"` : trimmed;
    })
    .join(', ');
}

/** The canvas font string for a face at `pxPerMm`, built exactly the way
 * Konva builds its own (`Text._getContextFont`), so both measure alike. */
export function canvasFont(face: TextFace, pxPerMm: number): string {
  return `${face.fontStyle} normal ${face.fontSize_mm * pxPerMm}px ${quoteFamilies(face.fontFamily)}`;
}

/** Width of a string in px, letter spacing NOT included. */
export type MeasureText = (text: string) => number;

let measureContext: CanvasRenderingContext2D | null | undefined;

/** A measure on a 2D canvas context, or null where there is no canvas
 * (server render). */
export function canvasMeasure(font: string): MeasureText | null {
  if (measureContext === undefined) {
    measureContext =
      typeof document === 'undefined'
        ? null
        : document.createElement('canvas').getContext('2d');
  }
  const context = measureContext;
  if (!context) return null;
  return (text) => {
    context.font = font;
    return context.measureText(text).width;
  };
}

export interface WrapBox {
  maxWidth: number;
  maxHeight: number;
  /** One line's height, in the same unit as the widths. */
  lineHeight: number;
  letterSpacing: number;
  /** Share of `maxWidth` a line must leave free. Default 0. */
  headroom?: number;
}

/**
 * Konva 10's `wrap: 'word'` (`Text._setTextData`, no ellipsis), as a pure
 * function: per hard line, the longest prefix that fits, pulled back to the
 * last space or hyphen in it (or cut before the next character when that is
 * one), trimmed; the first line always draws, and lines stop once the next one
 * would overflow the height. Characters are code points (Konva also merges
 * emoji sequences; a price tag has none).
 */
export function wrapTextLines(text: string, box: WrapBox, measure: MeasureText): string[] {
  const width = (s: string) => measure(s) + box.letterSpacing * s.length;
  const maxWidth = box.maxWidth * (1 - (box.headroom ?? 0));
  const maxHeight = box.maxHeight * (1 + HEIGHT_TOLERANCE);
  const lines: string[] = [];
  let height = 0;

  for (const paragraph of text.split('\n')) {
    let line = paragraph;
    if (width(line) > maxWidth) {
      while (line.length > 0) {
        const chars = Array.from(line);
        let low = 0;
        let high = chars.length;
        let match = '';
        let matchWidth = 0;
        while (low < high) {
          const mid = (low + high) >>> 1;
          const candidate = chars.slice(0, mid + 1).join('');
          const candidateWidth = width(candidate);
          if (candidateWidth <= maxWidth) {
            low = mid + 1;
            match = candidate;
            matchWidth = candidateWidth;
          } else {
            high = mid;
          }
        }
        if (!match) break;

        const matchChars = Array.from(match);
        const next = chars[matchChars.length];
        const wrapIndex =
          (next === ' ' || next === '-') && matchWidth <= maxWidth
            ? matchChars.length
            : Math.max(matchChars.lastIndexOf(' '), matchChars.lastIndexOf('-')) + 1;
        if (wrapIndex > 0) {
          low = wrapIndex;
          match = chars.slice(0, low).join('');
        }
        lines.push(match.trimEnd());
        height += box.lineHeight;
        if (height + box.lineHeight > maxHeight) return lines;

        line = chars.slice(low).join('').trimStart();
        if (line.length > 0 && width(line) <= maxWidth) {
          lines.push(line);
          height += box.lineHeight;
          break;
        }
      }
    } else {
      lines.push(line);
      height += box.lineHeight;
    }
    if (height + box.lineHeight > maxHeight) break;
  }
  return lines;
}

/**
 * The lines a text layer draws, on the canvas and on the print page alike:
 * broken inside the layer's padded box, in its own face, at
 * `LAYOUT_PX_PER_MM`. `measure` is for tests; without a canvas (server
 * render) the text is returned as its hard lines.
 */
export function textLayerLines(
  props: TextLayerProps,
  text: string,
  width_mm: number,
  height_mm: number,
  measure?: MeasureText | null,
): string[] {
  const face = textFace(props);
  const px = LAYOUT_PX_PER_MM;
  const m = measure === undefined ? canvasMeasure(canvasFont(face, px)) : measure;
  if (!m) return text.split('\n');
  const box = paddedBox(width_mm, height_mm, props.padding);
  return wrapTextLines(
    text,
    {
      maxWidth: box.width * px,
      maxHeight: box.height * px,
      lineHeight: props.lineHeight * face.fontSize_mm * px,
      letterSpacing: face.letterSpacing_mm * px,
      headroom: FIT_HEADROOM,
    },
    m,
  );
}
