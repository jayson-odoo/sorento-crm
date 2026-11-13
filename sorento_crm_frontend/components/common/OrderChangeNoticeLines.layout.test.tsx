/**
 * OCN-ORDER-CHANGE-NOTICE rounds 15-16 (crew pass, 1280 px): the line table fits the form card at
 * 1280 (about 853 px of content, measured on browser pass 6) with no sideways scroll, and scrolls
 * inside its own wrapper on a phone (SampleRequestLines' pattern). Each date cell holds
 * "DD/MM/YYYY" beside its calendar button through the shared picker's compact props. jsdom has no
 * layout, so this pins the classes that make it so; the browser pass checks the pixels. (Round 16
 * is a width tweak on round 15's red test, so it was not re-run red first.)
 *
 * Round 18 (crew pass 6848092891, 1280 px): a 64 px Qty column showed 842 as "84" (the input's
 * 12 px side padding and the browser's number spinner left room for two digits). The Qty columns
 * now match Delivered (4.75rem) and every quantity box uses the compact padding the date boxes use;
 * Remark gives up the 24 px, so the columns still add up to 840.
 */
import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OrderChangeNoticeLines, blankOcnLine } from './OrderChangeNoticeLines';

/** The form card's content width at 1280 px with the sidebar open (browser pass 6), less a margin. */
const CARD_AT_1280 = 850;

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

  it('sizes the columns to add up to the min width, Remark taking the rest', () => {
    const { container } = render(<OrderChangeNoticeLines lines={[blankOcnLine()]} onChange={() => {}} />);
    const th = (name: string) =>
      Array.from(container.querySelectorAll('th')).find((h) => h.textContent === name) as HTMLElement;
    const table = container.querySelector('table') as HTMLTableElement;
    expect(minWidthPx(table)).toBe(840);
    expect(th('No.').className).toMatch(/\bw-8\b/);
    expect(remOf(th('Item Code'))).toBe(9.25);
    for (const name of ['Qty before', 'Qty after']) expect(remOf(th(name))).toBe(4.75);
    expect(remOf(th('Delivered'))).toBe(4.75); // the header word DELIVERED fits
    for (const name of ['Date before', 'Date after']) expect(remOf(th(name))).toBe(9.25);
    expect(th('Remark').className).toMatch(/min-w-\[6rem\]/);
    expect(th('Remove').className).toMatch(/\bw-10\b/);
  });

  it('draws the date inputs compact, through the shared picker, so DD/MM/YYYY fits beside the button', () => {
    const { getByLabelText } = render(<OrderChangeNoticeLines lines={[blankOcnLine()]} onChange={() => {}} />);
    for (const name of ['Date before', 'Date after']) {
      const input = getByLabelText(name);
      expect(input.className).toMatch(/\btext-xs\b/);
      expect((input.parentElement as HTMLElement).className).toMatch(/\bgap-1\b/);
    }
  });

  it('draws every quantity box compact so a 4-digit quantity shows whole (842 never reads "84")', () => {
    const { getByLabelText } = render(<OrderChangeNoticeLines lines={[blankOcnLine()]} onChange={() => {}} />);
    for (const name of ['Qty before', 'Qty after', 'Delivered']) {
      const input = getByLabelText(name);
      expect(input.className).toMatch(/\btext-xs\b/);
      expect(input.className).toMatch(/\bpx-2\b/);
    }
  });
});
