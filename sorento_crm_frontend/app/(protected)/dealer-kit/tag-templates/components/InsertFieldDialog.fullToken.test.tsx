/**
 * TAG-TEMPLATE-DUPLICATE item 3 (owner 6 Nov): the Insert field list showed tokens cut off
 * ("{{pr", "{{product."). Every token is now shown whole, on its own line under the label, and
 * wraps rather than truncating; the row's tooltip carries the full token too.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { InsertFieldDialog } from './InsertFieldDialog';

function open() {
  render(
    <InsertFieldDialog
      open
      value=""
      data={null}
      specKeys={[]}
      onCancel={vi.fn()}
      onDone={vi.fn()}
    />,
  );
}

const CLIPPING = /\b(truncate|text-ellipsis|text-clip|overflow-hidden|whitespace-nowrap)\b/;

describe('InsertFieldDialog full tokens', () => {
  it('renders the longest token whole, wrapping, with no ellipsis or clip', () => {
    open();
    const token = screen
      .getAllByTestId('merge-field-token')
      .find((el) => el.textContent === '{{product.price_tag_description}}');
    expect(token).toBeDefined();
    expect(token!.className).not.toMatch(CLIPPING);
    expect(token!.className).toMatch(/break-all/);
    // The row (and the label beside it) never clips the token either.
    const row = token!.closest('button')!;
    expect(row.className).not.toMatch(CLIPPING);
    expect(row).toHaveAttribute('title', '{{product.price_tag_description}}');
    // jsdom has no stylesheet, so the class list above is the rendered truth; an inline style
    // must not reintroduce an ellipsis either.
    expect(token!.style.textOverflow).not.toBe('ellipsis');
    expect(token!.style.overflow).not.toBe('hidden');
  });

  it('puts the token on its own line under the label', () => {
    open();
    const token = screen
      .getAllByTestId('merge-field-token')
      .find((el) => el.textContent === '{{product.price_tag_description}}')!;
    const row = token.closest('button')!;
    expect(row.className).toMatch(/flex-col/);
    expect(row).toHaveTextContent('Price tag description');
  });
});
