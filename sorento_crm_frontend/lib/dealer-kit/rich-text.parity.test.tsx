/**
 * PRICETAG-COMBO-FORMAT AC-18: for the same tag data the canvas and the print page draw the same
 * runs (text and face per run), for E1 and for a description that uses every toolbar item.
 *
 * Written test-FIRST (today both draw the raw HTML string, so the run lists are empty or equal
 * only by accident; the missing parser fails the import first).
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
          data-font-style={String(props.fontStyle ?? '')}
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

import TagSheetRenderer from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';
import {
  E1_HTML,
  EVERY_ITEM_HTML,
  richTextLayer,
  tagSheetDocWith,
} from './rich-text.e1.fixture';

interface DrawnRun {
  text: string;
  bold: boolean;
  colour: string;
}

const boldOf = (value: string) => value === 'bold' || /\b[6-9]00\b/.test(value) || Number(value) >= 600;

function hexToRgb(value: string): string {
  const match = /^#([0-9a-f]{6})$/i.exec(value);
  if (!match) return value;
  const n = parseInt(match[1], 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

function canvasRuns(html: string): DrawnRun[] {
  const { container } = render(<KonvaTagLayer layer={richTextLayer(html)} scale={3} />);
  return Array.from(container.querySelectorAll<HTMLElement>('[data-konva="text"]'))
    .filter((node) => node.dataset.text!.trim() !== '')
    .map((node) => ({
      text: node.dataset.text!.trim(),
      bold: boldOf(node.dataset.fontStyle!),
      colour: hexToRgb(node.dataset.fill!),
    }));
}

function printRuns(html: string): DrawnRun[] {
  const { container } = render(
    <TagSheetRenderer doc={tagSheetDocWith(richTextLayer(html))} resolvedData={{}} />,
  );
  return Array.from(container.querySelectorAll<HTMLElement>('span'))
    .filter((span) => span.childElementCount === 0 && (span.textContent ?? '').trim() !== '')
    .map((span) => ({
      text: span.textContent!.trim(),
      bold: boldOf(span.style.fontWeight),
      colour: span.style.color,
    }));
}

describe('canvas and print draw the same runs (AC-18)', () => {
  for (const [label, html] of [
    ['E1', E1_HTML],
    ['a description using every toolbar item', EVERY_ITEM_HTML],
  ] as const) {
    it(`AC-18: ${label}`, () => {
      const canvas = canvasRuns(html);
      const print = printRuns(html);
      expect(canvas.length).toBeGreaterThan(0);
      expect(print.map((run) => [run.text, run.bold])).toEqual(canvas.map((run) => [run.text, run.bold]));
      // A run with its own colour has it on both surfaces.
      const grey = (runs: DrawnRun[]) => runs.filter((run) => run.colour === 'rgb(107, 114, 128)').map((r) => r.text);
      expect(grey(print)).toEqual(grey(canvas));
    });
  }
});
