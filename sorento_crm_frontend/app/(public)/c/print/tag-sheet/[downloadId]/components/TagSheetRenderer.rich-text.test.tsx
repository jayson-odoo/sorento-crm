/**
 * PRICETAG-COMBO-FORMAT AC-17: the print page renders the same run model as React spans: bold
 * spans for the six codes, grey spans for the dimensions, no element built from `innerHTML`.
 *
 * Written test-FIRST. Today the whole HTML string prints as one text node.
 */
import { readFileSync } from 'fs';
import path from 'path';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  E1_BOLD_WORDS,
  E1_DIMENSIONS,
  E1_HTML,
  richTextLayer,
  tagSheetDocWith,
} from '@/lib/dealer-kit/rich-text.e1.fixture';
import TagSheetRenderer from './TagSheetRenderer';

const GREY_RGB = 'rgb(107, 114, 128)';
const isBold = (weight: string) => weight === 'bold' || Number(weight) >= 600;

function print(text: string) {
  return render(<TagSheetRenderer doc={tagSheetDocWith(richTextLayer(text))} resolvedData={{}} />);
}

function spans(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>('span')).filter(
    (span) => span.childElementCount === 0 && (span.textContent ?? '').trim() !== '',
  );
}

describe('TagSheetRenderer rich text (AC-17)', () => {
  it('AC-17: E1 prints the six codes as bold spans', () => {
    const { container } = print(E1_HTML);
    for (const word of E1_BOLD_WORDS) {
      const span = spans(container).find((s) => s.textContent!.trim() === word);
      expect(span, word).toBeDefined();
      expect(isBold(span!.style.fontWeight), word).toBe(true);
    }
  });

  it('AC-17: E1 prints the dimensions in grey spans', () => {
    const { container } = print(E1_HTML);
    for (const dimension of E1_DIMENSIONS) {
      const span = spans(container).find((s) => s.textContent!.trim() === dimension);
      expect(span, dimension).toBeDefined();
      expect(span!.style.color).toBe(GREY_RGB);
    }
  });

  it('AC-17: no markup text reaches the page', () => {
    const { container } = print(E1_HTML);
    expect(container.textContent).not.toContain('<p>');
    expect(container.textContent).not.toContain('<strong>');
    expect(container.textContent).not.toContain('style=');
  });

  it('AC-17: an <img onerror> string in a rich description renders as visible text, no img element', () => {
    const { container } = print('<p>&lt;img src=x onerror=alert(1)&gt;</p>');
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('AC-17: the same string as plain text also renders as text (unchanged behaviour)', () => {
    const { container } = print('<img src=x onerror=alert(1)>');
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('AC-17: the renderer builds nothing from innerHTML', () => {
    const source = readFileSync(path.join(__dirname, 'TagSheetRenderer.tsx'), 'utf8');
    expect(source).not.toContain('dangerouslySetInnerHTML');
    expect(source).not.toMatch(/\.innerHTML/);
  });
});
