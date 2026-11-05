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
import type { RichAlign, RichBlock, RichRun } from './rich-text';
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
): string[];
/** A rich description (parsed blocks): lines of runs, each measured in its own face. */
export function textLayerLines(
  props: TextLayerProps,
  blocks: RichBlock[],
  width_mm: number,
  height_mm: number,
  measureFor?: MeasureFor | null,
): RichLine[];
export function textLayerLines(
  props: TextLayerProps,
  source: string | RichBlock[],
  width_mm: number,
  height_mm: number,
  measure?: MeasureText | MeasureFor | null,
): string[] | RichLine[] {
  if (Array.isArray(source)) {
    return richLayerLines(props, source, width_mm, height_mm, measure as MeasureFor | null | undefined);
  }
  const text = source;
  const face = textFace(props);
  const px = LAYOUT_PX_PER_MM;
  const m = measure === undefined ? canvasMeasure(canvasFont(face, px)) : (measure as MeasureText | null);
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


// ---------------------------------------------------------------------------
// Rich description (PRICETAG-COMBO-FORMAT S3)
// ---------------------------------------------------------------------------

/** A measure for one font string; null where there is no canvas (server render). */
export type MeasureFor = (font: string) => MeasureText | null;

/** Hanging indent of a list item per level, and the indent of a quote, in mm. */
export const LIST_INDENT_MM = 3.5;
export const QUOTE_INDENT_MM = 3;
const MONOSPACE = 'ui-monospace, Menlo, Consolas, monospace';

/** A run placed on its line. Positions are mm from the padded box's top-left. */
export type LayoutRun = RichRun & {
  sizeFactor: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  /** One line box, the same for every run on the line. */
  lineHeight_mm: number;
  align: RichAlign;
  /** Where the line's text starts (the marker hangs to the left of it). */
  indent_mm: number;
  /** The bullet or number of a list item's first line. */
  marker?: boolean;
};
export type RichLine = LayoutRun[];

/** The face a run draws in: the layer's, plus the run's bold / italic / code and its block's
 * size factor. Family and base size are never taken from the description. */
export function runFace(props: TextLayerProps, run: RichRun, sizeFactor: number, blockBold = false): TextFace {
  const baseWeight = props.fontWeight || 400;
  const bold = !!run.bold || blockBold;
  return textFace({
    fontFamily: run.code ? MONOSPACE : props.fontFamily,
    fontSize: props.fontSize * sizeFactor,
    fontWeight: bold ? Math.max(700, baseWeight) : baseWeight,
    italic: !!props.italic || !!run.italic,
    letterSpacing: props.letterSpacing,
  });
}

interface Piece {
  run: number;
  text: string;
  width: number;
}
interface Group {
  space: Piece[];
  words: Piece[];
}

const TOKEN = /\n|[ \t]+|[^\s-]*-|[^\s-]+/g;

export function richLayerLines(
  props: TextLayerProps,
  blocks: RichBlock[],
  width_mm: number,
  height_mm: number,
  measureFor?: MeasureFor | null,
): RichLine[] {
  const px = LAYOUT_PX_PER_MM;
  const box = paddedBox(width_mm, height_mm, props.padding);
  const maxWidth = box.width * px * (1 - FIT_HEADROOM);
  const maxHeight = box.height * px * (1 + HEIGHT_TOLERANCE);
  const fontMeasure = (font: string) => (measureFor === undefined ? canvasMeasure(font) : measureFor?.(font) ?? null);
  const measurable = fontMeasure(canvasFont(textFace(props), px)) !== null;
  const lines: RichLine[] = [];
  let top = 0;

  for (const entry of blocks) {
    const factor = entry.sizeFactor || 1;
    const level = entry.level ?? 1;
    const indentMm = entry.kind === 'li' ? level * LIST_INDENT_MM : entry.kind === 'quote' ? QUOTE_INDENT_MM : 0;
    const indent = indentMm * px;
    const available = Math.max(maxWidth - indent, 1);
    const align: RichAlign = entry.align ?? props.align ?? 'left';
    const runs = entry.runs.length ? entry.runs : [{ text: '' } as RichRun];
    const faces = runs.map((run) => runFace(props, run, factor, entry.bold));
    const widthOf = (pieceText: string, index: number): number => {
      if (!measurable) return 0;
      const face = faces[index];
      const measure = fontMeasure(canvasFont(face, px));
      return (measure ? measure(pieceText) : 0) + face.letterSpacing_mm * px * pieceText.length;
    };

    // Tokens -> groups (a group never breaks inside: words glued across runs, up to a space or hyphen).
    const lineSets: Piece[][] = [];
    let line: Piece[] = [];
    let lineWidth = 0;
    const endLine = () => {
      lineSets.push(line);
      line = [];
      lineWidth = 0;
    };
    const groups: Array<Group | 'break'> = [];
    let space: Piece[] = [];
    let current: Group | null = null;
    const closeGroup = () => {
      if (current) groups.push(current);
      current = null;
    };
    runs.forEach((run, index) => {
      for (const token of run.text.match(TOKEN) ?? []) {
        if (token === '\n') {
          closeGroup();
          space = [];
          groups.push('break');
        } else if (/^[ \t]+$/.test(token)) {
          closeGroup();
          space.push({ run: index, text: token, width: widthOf(token, index) });
        } else {
          if (!current) {
            current = { space, words: [] };
            space = [];
          }
          current.words.push({ run: index, text: token, width: widthOf(token, index) });
          if (token.endsWith('-')) closeGroup();
        }
      }
    });
    closeGroup();

    for (const group of groups) {
      if (group === 'break') {
        endLine();
        continue;
      }
      const groupWidth = group.words.reduce((sum, piece) => sum + piece.width, 0);
      const spaceWidth = lineWidth > 0 ? group.space.reduce((sum, piece) => sum + piece.width, 0) : 0;
      if (measurable && lineWidth > 0 && lineWidth + spaceWidth + groupWidth > available) endLine();
      if (measurable && groupWidth > available && lineWidth === 0) {
        // A word wider than the line: cut it where it overflows.
        for (const piece of group.words) {
          for (const char of Array.from(piece.text)) {
            const charWidth = widthOf(char, piece.run);
            if (lineWidth > 0 && lineWidth + charWidth > available) endLine();
            line.push({ run: piece.run, text: char, width: charWidth });
            lineWidth += charWidth;
          }
        }
        continue;
      }
      if (lineWidth > 0) {
        line.push(...group.space);
        lineWidth += spaceWidth;
      }
      line.push(...group.words);
      lineWidth += groupWidth;
    }
    endLine();

    const lineHeight = props.lineHeight * textFace({ ...props, fontSize: props.fontSize * factor }).fontSize_mm * px;
    for (let at = 0; at < lineSets.length; at += 1) {
      // Always draw the first line; later ones only while they fit the box.
      if (measurable && lines.length > 0 && top + lineHeight > maxHeight) return lines;
      const pieces = lineSets[at];
      const merged: Array<{ run: number; text: string; width: number }> = [];
      for (const piece of pieces) {
        const last = merged[merged.length - 1];
        if (last && last.run === piece.run) {
          last.text += piece.text;
          last.width += piece.width;
        } else merged.push({ ...piece });
      }
      if (merged.length === 0) merged.push({ run: 0, text: '', width: 0 });
      const total = merged.reduce((sum, piece) => sum + piece.width, 0);
      const free = Math.max(box.width * px - indent - total, 0);
      let x = indent + (align === 'center' ? free / 2 : align === 'right' ? free : 0);
      const placed: LayoutRun[] = [];
      if (at === 0 && entry.kind === 'li' && entry.marker) {
        const markerRun: RichRun = { text: entry.marker, bold: entry.bold };
        const markerWidth = widthOf(entry.marker, 0);
        placed.push({
          ...markerRun,
          marker: true,
          sizeFactor: factor,
          x_mm: (indent - LIST_INDENT_MM * px) / px,
          y_mm: top / px,
          width_mm: markerWidth / px,
          lineHeight_mm: lineHeight / px,
          align,
          indent_mm: indentMm,
        });
      }
      for (const piece of merged) {
        const source = runs[piece.run];
        placed.push({
          ...source,
          bold: !!source.bold || !!entry.bold,
          text: piece.text,
          sizeFactor: factor,
          x_mm: x / px,
          y_mm: top / px,
          width_mm: piece.width / px,
          lineHeight_mm: lineHeight / px,
          align,
          indent_mm: indentMm,
        });
        x += piece.width;
      }
      lines.push(placed);
      top += lineHeight;
    }
  }
  return lines;
}
