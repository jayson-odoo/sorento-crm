/**
 * SAMPLE-REQUEST-V2 crew pass 12 Nov, item 3: at 375 px the Items table put Qty and Remark past
 * the card edge (a fixed 560 px table in a sideways scroller). Below `sm` each line stacks
 * instead: the table has no minimum width there, the column header row is hidden, and Qty and
 * Remark carry their own captions. jsdom has no layout, so this pins the class contract; the
 * cloud browser pass measures the real width.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/app/(auth)/portal/components/AsyncCombobox', () => ({
  AsyncCombobox: ({ ariaLabel }: { ariaLabel: string }) => <input aria-label={ariaLabel} />,
}));

import { SampleRequestLines } from './SampleRequestLines';

function mount() {
  return render(
    <SampleRequestLines
      value={{
        lines: [{ key: 'k1', product_id: '', label: '', qty: '1', remark: '' }],
        board_mounting: false,
        board_label: '',
      }}
      onChange={() => undefined}
      search={async () => []}
      captions={{ no: 'No', item: 'Item code', qty: 'Qty' }}
    />,
  );
}

describe('Sample request lines at phone width (375 px)', () => {
  it('the table has a minimum width only from sm up, so it never runs past the card on a phone', () => {
    mount();
    const table = screen.getByRole('table');
    const classes = table.className.split(/\s+/);
    expect(classes).not.toContain('min-w-[560px]');
    expect(classes).toContain('sm:min-w-[560px]');
  });

  it('the column header row is hidden below sm, and each line is a stacked grid there', () => {
    mount();
    const head = screen.getByRole('table').querySelector('thead') as HTMLElement;
    expect(head.className).toMatch(/(^|\s)max-sm:hidden(\s|$)/);
    const line = screen.getByTestId('sample-request-line');
    expect(line.className).toMatch(/(^|\s)max-sm:grid(\s|$)/);
  });

  it('Qty and Remark keep a visible caption on a phone, where the header row is hidden', () => {
    mount();
    const line = screen.getByTestId('sample-request-line');
    const captions = Array.from(line.querySelectorAll('[data-narrow-caption]')).map((el) => el.textContent);
    expect(captions).toEqual(['Qty', 'Remark']);
    for (const el of Array.from(line.querySelectorAll('[data-narrow-caption]'))) {
      expect((el as HTMLElement).className).toMatch(/(^|\s)sm:hidden(\s|$)/);
    }
  });
});
