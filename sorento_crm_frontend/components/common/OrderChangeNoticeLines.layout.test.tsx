/**
 * OCN-ORDER-CHANGE-NOTICE round 15 (crew pass, 1280 px): the line table fits the form card at 1280
 * and scrolls inside its own wrapper on a phone (SampleRequestLines' pattern), and each date
 * column is wide enough for "DD/MM/YYYY" beside its calendar button. jsdom has no layout, so this
 * pins the classes that make it so; the browser pass checks the pixels.
 */
import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OrderChangeNoticeLines, blankOcnLine } from './OrderChangeNoticeLines';

/** The form card's content width at 1280 px with the sidebar open (measured on the browser pass). */
const CARD_AT_1280 = 880;

function minWidthPx(el: Element): number {
  const m = /min-w-\[(\d+)px\]/.exec(el.className);
  return m ? Number(m[1]) : NaN;
}

function remOf(el: Element): number {
  const m = /(?:^|\s)w-\[(\d+(?:\.\d+)?)rem\]/.exec(el.className);
  return m ? Number(m[1]) : NaN;
}

describe('OrderChangeNoticeLines layout', () => {
  for (const readOnly of [false, true]) {
    it(`${readOnly ? 'the read-only' : 'the editable'} table scrolls in its own wrapper and fits the card at 1280`, () => {
      const { container } = render(
        <OrderChangeNoticeLines lines={[blankOcnLine()]} onChange={() => {}} readOnly={readOnly} />,
      );
      const table = container.querySelector('table') as HTMLTableElement;
      const wrapper = table.parentElement as HTMLElement;
      expect(wrapper.className).toMatch(/\boverflow-x-auto\b/);
      expect(minWidthPx(table)).toBeLessThanOrEqual(CARD_AT_1280);
    });
  }

  it('gives each date column room for DD/MM/YYYY beside its calendar button', () => {
    const { container } = render(<OrderChangeNoticeLines lines={[blankOcnLine()]} onChange={() => {}} />);
    const heads = Array.from(container.querySelectorAll('th'));
    for (const name of ['Date before', 'Date after']) {
      const th = heads.find((h) => h.textContent === name) as HTMLElement;
      // input (px-3, ~75 px of text) + 8 px gap + the 34 px button + the cell's 16 px padding
      expect(remOf(th)).toBeGreaterThanOrEqual(10.5);
    }
  });
});
