/**
 * PRICETAG-COMBO-FORMAT fix round 1, R11: print draws a bold run with the same weight as the
 * canvas (`runFace`: the larger of 700 and the layer's own weight). A 900 layer prints its bold
 * words at 900, not at a flat 700; a 300 layer prints them at 700.
 *
 * Written test-FIRST: the print page uses a fixed bold weight today.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { richTextLayer, tagSheetDocWith } from '@/lib/dealer-kit/rich-text.e1.fixture';
import TagSheetRenderer from './TagSheetRenderer';

function weightOf(word: string, baseWeight: number): string {
  const html = `<p><strong>BOLDWORD</strong> plainword</p>`;
  const { container } = render(
    <TagSheetRenderer
      doc={tagSheetDocWith(richTextLayer(html, {}, { fontWeight: baseWeight }))}
      resolvedData={{}}
    />,
  );
  const span = Array.from(container.querySelectorAll<HTMLElement>('span')).find(
    (s) => s.childElementCount === 0 && s.textContent?.trim() === word,
  );
  expect(span, word).toBeDefined();
  return span!.style.fontWeight;
}

describe('print bold weight matches the canvas (R11)', () => {
  it('R11: a bold run on a 900 layer is 900', () => {
    expect(weightOf('BOLDWORD', 900)).toBe('900');
  });

  it('R11: a bold run on a 300 layer is 700', () => {
    expect(weightOf('BOLDWORD', 300)).toBe('700');
  });
});
