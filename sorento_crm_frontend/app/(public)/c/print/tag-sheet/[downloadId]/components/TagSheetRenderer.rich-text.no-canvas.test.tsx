/**
 * MAIN-RED-TAGSHEET: the AC-17 escaped `<img onerror>` description, printed where there is NO
 * canvas to measure with (jsdom without the optional `canvas` package: crew's census machine).
 *
 * Main went red there with `'<imgsrc=xonerror=alert(1)>'`: the rich layout dropped every space
 * when it could not measure. Here `getContext` returns null for the whole file, so the case runs
 * the same on every machine, with or without `canvas` installed.
 *
 * The security half of AC-17 is asserted again: no img element, no handler attribute.
 */
import { render } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

import { richTextLayer, tagSheetDocWith } from '@/lib/dealer-kit/rich-text.e1.fixture';
import TagSheetRenderer from './TagSheetRenderer';

let getContext: ReturnType<typeof vi.spyOn>;

beforeAll(() => {
  // Before the first render: text-layout caches the context on its first measure.
  getContext = vi
    .spyOn(HTMLCanvasElement.prototype, 'getContext')
    .mockReturnValue(null as unknown as ReturnType<HTMLCanvasElement['getContext']>);
});

afterAll(() => {
  getContext.mockRestore();
});

function print(text: string) {
  return render(<TagSheetRenderer doc={tagSheetDocWith(richTextLayer(text))} resolvedData={{}} />);
}

describe('TagSheetRenderer rich text with no canvas (MAIN-RED-TAGSHEET)', () => {
  it('an escaped <img onerror> in a rich description prints as text with its spaces, no img element', () => {
    const { container } = print('<p>&lt;img src=x onerror=alert(1)&gt;</p>');
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('a bold code followed by plain words keeps the space between them', () => {
    const { container } = print('<p><strong>SRTBF11416</strong> (CABINET) 600 x 400</p>');
    expect(container.textContent).toContain('SRTBF11416 (CABINET) 600 x 400');
  });
});
